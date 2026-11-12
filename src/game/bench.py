# src/game/bench.py
"""
In-game bench moves: pinch hitters and pinch runners.

Before each plate appearance late in a close game, the batting team's manager
looks down his bench for a better bat against the pitcher on the mound. A bench
hitter goes in when his bat (after the platoon edge, his fatigue and the GM's
view of his season) beats the man due up by enough for the spot. The bigger
the spot (later inning, runners in scoring position), the smaller the edge he
needs.

A pinch hitter stays in the game: he takes over the replaced hitter's batting
slot and his position in the field, so a weak glove counts against him
(a share of what the position's glove is worth that shrinks as the innings
run out). The man he replaced is out of the game for good.

Pinch runners: before a plate appearance from the 7th on, a slow runner whose
run would tie the game or put his team ahead is run for by a faster bench
player, when the jump in speed and baserunning (RUN_WEIGHTS) beats MIN_RUN_EDGE
for the spot. The runner takes over the batting slot and position too, so the
bat and glove he gives up count against him, less as the innings run out.

Who's on the bench (TeamInGame.bench_players): hitters on today's roster who
aren't in the lineup, aren't hurt and haven't been taken out. A bench hitter
needs MIN_ENERGY to bat, and the last catcher on the bench is kept for an
emergency until the ninth.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.player.player_constants import TIRED_THRESHOLD
from src.player.player_evaluator import LEFT_HAND_CAPPED_POSITIONS
from src.team.lineup_optimizer import DEFENSE_IMPORTANCE, LineupOptimizer

if TYPE_CHECKING:
    from src.game.game import Game
    from src.player.player_in_game import PlayerInGame
    from src.team.team_in_game import TeamInGame

# Pinch hitting starts in this inning.
FIRST_INNING = 7
# The batting team must be within this many runs ahead (a tie is 0)...
MAX_LEAD = 1
# ...or this many behind, with the tying run no further away than on deck.
MAX_DEFICIT = 4
# Rating points of offense a pinch hitter must add in an ordinary late spot
# (the 7th, nobody in scoring position). PLATOON_PENALTY (7) is the same-side
# edge, so a platoon swap needs a bench bat close to the regular's.
MIN_GAIN = 6.0
# How much bigger a spot is, which shrinks the edge needed.
INNING_LEVERAGE = {7: 1.0, 8: 1.2}
LATE_LEVERAGE = 1.45  # 9th and extra innings
RISP_LEVERAGE = 1.25  # a runner on second or third
# Share of a position's glove value a pinch hitter's weaker glove costs, by
# inning: the fewer innings left to play in the field, the less it matters.
DEFENSE_COST_SHARE = {7: 0.35, 8: 0.25}
LATE_DEFENSE_COST_SHARE = 0.15  # 9th and extra innings
# A bench hitter this tired doesn't bat.
MIN_ENERGY = TIRED_THRESHOLD


def leverage(game: Game) -> float:
    """How big the coming plate appearance is for the batting team, 0 when
    it's not a pinch hitting spot at all."""
    inning = game.inning.number
    if inning < FIRST_INNING:
        return 0.0
    if game.inning.top:
        diff = game.score.away - game.score.home
    else:
        diff = game.score.home - game.score.away
    if diff > MAX_LEAD:
        return 0.0
    runners = game.bases.number_of_baserunners
    if diff < 0 and (-diff > MAX_DEFICIT or -diff > runners + 2):
        return 0.0
    lev = INNING_LEVERAGE.get(inning, LATE_LEVERAGE)
    occupied = game.bases.occupied_map()
    if 2 in occupied or 3 in occupied:
        lev *= RISP_LEVERAGE
    return lev


def bat_value(team: TeamInGame, player: PlayerInGame, vs_hand: str | None) -> float:
    """A hitter's bat against this pitcher's hand, as the manager sees it."""
    value = player.ratings.get("overall_offense", 0)
    value -= LineupOptimizer.matchup(player, vs_hand)
    return value + getattr(team, "form", {}).get(player.id, 0.0)


def defense_cost(
    team: TeamInGame,
    batter: PlayerInGame,
    sub: PlayerInGame,
    position: str | None,
    inning: int = 7,
) -> float | None:
    """What the pinch hitter's glove gives up at the batter's position for
    the rest of the game; None if he can't play there."""
    if not position or position == "dh":
        return 0.0
    if position in LEFT_HAND_CAPPED_POSITIONS and (sub.throws or "R").upper() == "L":
        return None
    drop = batter.ratings.get(position, 0) - sub.ratings.get(position, 0)
    weight = DEFENSE_IMPORTANCE.get(position, 0.5) * getattr(
        team, "defense_weight", 1.0
    )
    share = DEFENSE_COST_SHARE.get(inning, LATE_DEFENSE_COST_SHARE)
    return max(0.0, drop) * weight * share


def _available(game: Game, team: TeamInGame) -> list[PlayerInGame]:
    """Bench players fresh enough to go in. The last catcher on the bench is
    kept for an emergency until the ninth."""
    bench = [p for p in team.bench_players if _rested_enough(game, p)]
    if game.inning.number < 9:
        catchers = [p for p in bench if _is_catcher(p)]
        if len(catchers) == 1:
            bench.remove(catchers[0])
    return sorted(bench, key=lambda p: p.id)


def _rested_enough(game: Game, player: PlayerInGame) -> bool:
    energy = game._live_energy(player)
    return energy is None or energy >= MIN_ENERGY


def _is_catcher(player: PlayerInGame) -> bool:
    return (player.record.position or "").lower() == "c"


def pinch_hitter(game: Game) -> PlayerInGame | None:
    """The bench hitter who should bat for the man due up, or None."""
    lev = leverage(game)
    if not lev:
        return None
    team = game.bat_team
    slot = game.current_batter
    pitcher = game.current_pitcher
    if slot is None or pitcher is None:
        return None
    batter = slot.player
    bench = _available(game, team)
    hand = (pitcher.throws or "R").upper()
    need = MIN_GAIN / lev
    base = bat_value(team, batter, hand)
    position = batter.current_position or slot.position
    best, best_edge = None, need
    for p in bench:
        cost = defense_cost(team, batter, p, position, game.inning.number)
        if cost is None:
            continue
        edge = bat_value(team, p, hand) - base - cost
        if edge >= best_edge:
            best, best_edge = p, edge
    return best


# How a runner's legs are judged: speed most, then baserunning smarts.
RUN_WEIGHTS = {"speed": 0.65, "base_running": 0.35}
# Skill points of running a pinch runner must add in an ordinary late spot.
MIN_RUN_EDGE = 18.0
# Share of the bat a pinch runner gives up (rating points of overall
# offense) that counts against him, by inning: his slot may bat again.
BAT_COST_SHARE = {7: 0.5, 8: 0.35}
LATE_BAT_COST_SHARE = 0.2  # 9th and extra innings


def run_value(player: PlayerInGame) -> float:
    """How good a runner he is, on the 0-100 skill scale."""
    return sum(player.skills.get(k, 50) * w for k, w in RUN_WEIGHTS.items())


def _run_matters(game: Game, base: int) -> bool:
    """Would the runner on this base tie the game or put his team ahead if he
    scored (counting the runners ahead of him)?"""
    if game.inning.top:
        diff = game.score.away - game.score.home
    else:
        diff = game.score.home - game.score.away
    ahead = sum(1 for b in game.bases.occupied_map() if b > base)
    return diff + ahead + 1 in (0, 1)


def pinch_runners(game: Game) -> list[tuple[int, PlayerInGame, PlayerInGame]]:
    """The pinch runners the batting team should send in now, as (base,
    runner, sub), lead runner first."""
    inning = game.inning.number
    if inning < FIRST_INNING:
        return []
    team = game.bat_team
    pitcher = game.current_pitcher
    hand = (pitcher.throws or "R").upper() if pitcher else None
    lev = INNING_LEVERAGE.get(inning, LATE_LEVERAGE)
    need = MIN_RUN_EDGE / lev
    bat_share = BAT_COST_SHARE.get(inning, LATE_BAT_COST_SHARE)
    bench = _available(game, team)
    moves = []
    for base, runner in sorted(game.bases.occupied_map().items(), reverse=True):
        if not bench or not _run_matters(game, base):
            continue
        slot = next((s for s in team.lineup if s.player is runner), None)
        if slot is None:
            continue
        position = runner.current_position or slot.position
        best, best_edge = None, need
        for p in bench:
            glove = defense_cost(team, runner, p, position, inning)
            if glove is None:
                continue
            bat = max(0.0, bat_value(team, runner, hand) - bat_value(team, p, hand))
            edge = run_value(p) - run_value(runner) - glove - bat * bat_share
            if edge >= best_edge:
                best, best_edge = p, edge
        if best is not None:
            moves.append((base, runner, best))
            bench.remove(best)
    return moves
