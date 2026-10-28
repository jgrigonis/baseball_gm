# src/api/services/trades.py
#
# Proposing and carrying out trades (see plans/trades.md).
#
# A GM offers players to an AI team, which answers at once (see
# src/league/trades/ai_evaluator.py). Trades between human GMs come later.
#
# Rules checked on every offer:
#   - the league trades (Blitz; not Speed Blitz, not Long Form yet) and the
#     window is open: from the end of the draft until deadline day's games
#   - 1 to MAX_PER_SIDE players a side, each owned by the side giving him up
#   - no player goes back to a team that traded him away this season
#   - an AI team that turned down MAX_REJECTIONS_A_DAY offers from a team
#     today won't hear another until tomorrow
#
# A trade runs under the league lock, so it can't overlap a sim, and counts
# from the next game. Traded players arrive in the organization (minors),
# never on the 40-man, so a trade can't push a roster over 40. A team left
# under 25 has the best of its organization called up before its next game
# (src/team/roster_limits.py), unless the GM does it first.

from __future__ import annotations

from datetime import date

from src.db.locks import LeagueBusy, league_lock
from src.db.repositories.games_repo import GameRepository
from src.db.repositories.gm_repo import GMRepository
from src.db.repositories.injury_repo import InjuryRepository
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.db.repositories.season_repo import SeasonRepository
from src.db.repositories.standings_repo import StandingsRepository
from src.db.repositories.team_repo import TeamRepository
from src.db.repositories.trade_repo import TradeRepository
from src.league import trade_deadline
from src.league.rotation_seeder import seed_ai_rotations
from src.league.trades import ai_evaluator
from src.league.trades.ai_evaluator import Asset
from src.team.roster_assigner import RosterAssigner
from src.team.roster_limits import playing_count

MAX_PER_SIDE = 5
MAX_REJECTIONS_A_DAY = 3

# Statuses a player can be traded from.
TRADEABLE = ("26man", "40man", "minors")

# Stances, once STANCE_MIN_GAMES are played: a team in the playoff picture
# (top PLAYOFF_SPOTS, or within CONTENDER_GB games of the last spot) buys for
# now, and one more than SELLER_GB back sells. Everyone else is neutral.
PLAYOFF_SPOTS = 8
CONTENDER_GB = 5
SELLER_GB = 10
STANCE_MIN_GAMES = 20


class TradeError(ValueError):
    """An offer that breaks a rule. The message is shown to the GM."""


def propose(
    conn,
    league_id: str,
    gm: dict,
    to_team_id: str,
    give_ids: list[str],
    get_ids: list[str],
) -> dict:
    """Offer give_ids from the GM's team for get_ids from to_team_id. The AI
    answers at once; an accepted trade is carried out before returning.
    Returns {"accepted", "reason", "offer_id", "playing_count"}."""
    try:
        with league_lock(conn, league_id):
            return _propose(conn, league_id, gm, to_team_id, give_ids, get_ids)
    except LeagueBusy:
        raise TradeError("Games are being played. Try again in a moment.")


def _propose(conn, league_id, gm, to_team_id, give_ids, get_ids) -> dict:
    league = LeagueRepository(conn).get_by_id(league_id)
    season_id = SeasonRepository(conn).get_current_id_for_league(league_id)
    window = trade_deadline.window(conn, dict(league), season_id)
    if not window["enabled"]:
        raise TradeError("This league doesn't have trades.")
    if not window["open"]:
        raise TradeError("The trade window is closed.")

    my_team_id = gm["team_id"]
    team_repo = TeamRepository(conn)
    if to_team_id == my_team_id:
        raise TradeError("Pick another team to trade with.")
    if not team_repo.is_in_league(to_team_id, league_id, season_id):
        raise TradeError("That team isn't in this league.")
    if GMRepository(conn).get_human_gm_for_team(league_id, to_team_id):
        raise TradeError("Trades with other GMs are coming soon.")

    give_ids, get_ids = _dedupe(give_ids), _dedupe(get_ids)
    if not give_ids or not get_ids:
        raise TradeError("Each side has to give up at least one player.")
    if len(give_ids) > MAX_PER_SIDE or len(get_ids) > MAX_PER_SIDE:
        raise TradeError(f"At most {MAX_PER_SIDE} players a side.")

    player_repo = PlayerRepository(conn)
    status_repo = PlayerStatusRepository(conn)
    names = {}
    for side, ids in ((my_team_id, give_ids), (to_team_id, get_ids)):
        owned = player_repo.get_player_ids_from_team_players(side)
        for pid in ids:
            if pid not in owned:
                raise TradeError("A player in the offer isn't on that team any more.")
            if status_repo.get_status(pid) not in TRADEABLE:
                raise TradeError("A player in the offer can't be traded.")
            p = player_repo.look_up(pid)
            names[pid] = p.name if p else pid

    trade_repo = TradeRepository(conn)
    former = trade_repo.former_teams(season_id, give_ids + get_ids)
    for pid in give_ids:
        if to_team_id in former.get(pid, ()):
            raise TradeError(
                f"{names[pid]} can't go back to the {team_repo.get_name(to_team_id)} this season."
            )
    for pid in get_ids:
        if my_team_id in former.get(pid, ()):
            raise TradeError(f"{names[pid]} can't come back to you this season.")

    today = _league_date(conn, season_id)
    if (
        trade_repo.rejections_today(league_id, my_team_id, to_team_id, today)
        >= MAX_REJECTIONS_A_DAY
    ):
        raise TradeError(
            f"The {team_repo.get_name(to_team_id)} aren't taking any more calls today."
        )

    offer_id = trade_repo.create_offer(
        league_id,
        season_id,
        my_team_id,
        to_team_id,
        gm.get("id"),
        today,
        [(pid, my_team_id) for pid in give_ids]
        + [(pid, to_team_id) for pid in get_ids],
    )
    verdict = ai_answer(
        conn, league_id, season_id, to_team_id, my_team_id, get_ids, give_ids, today
    )
    if not verdict.accept:
        trade_repo.decide(offer_id, "rejected", verdict.reason)
        conn.commit()
        return {
            "accepted": False,
            "reason": verdict.reason,
            "offer_id": offer_id,
        }

    trade_repo.decide(offer_id, "accepted", verdict.reason)
    execute(
        conn,
        league_id,
        season_id,
        {my_team_id: give_ids, to_team_id: get_ids},
        _next_game_date(conn, season_id),
    )
    conn.commit()
    return {
        "accepted": True,
        "reason": verdict.reason,
        "offer_id": offer_id,
        "arrived": [names[pid] for pid in get_ids],
        "playing_count": playing_count(conn, my_team_id),
    }


def ai_answer(
    conn,
    league_id: str,
    season_id: str,
    ai_team_id: str,
    other_team_id: str,
    giving: list[str],
    getting: list[str],
    today: str,
) -> ai_evaluator.Verdict:
    """The AI team's answer to giving `giving` for `getting`."""
    injuries = InjuryRepository(conn, league_id)
    roster = _assets(conn, ai_team_id, injuries.get_team_injuries(ai_team_id, today))
    theirs = _assets(
        conn, other_team_id, injuries.get_team_injuries(other_team_id, today)
    )
    by_id = {a.id: a for a in roster + theirs}
    return ai_evaluator.evaluate(
        roster=roster,
        giving=[by_id[pid] for pid in giving],
        getting=[by_id[pid] for pid in getting],
        stance=stance(conn, league_id, season_id, ai_team_id),
        days_left=_days_left(conn, season_id, today),
        margin_share=ai_evaluator.margin(ai_team_id, other_team_id, today),
    )


def execute(
    conn,
    league_id: str,
    season_id: str,
    sides: dict[str, list[str]],
    effective_date: str,
) -> None:
    """Move each team's players in `sides` ({team_id: player_ids it gives
    up}) to the other team. Two teams only."""
    (team_a, give_a), (team_b, give_b) = sides.items()
    team_repo = TeamRepository(conn)
    status_repo = PlayerStatusRepository(conn)
    since = date.fromisoformat(effective_date)
    for from_team, to_team, ids in ((team_a, team_b, give_a), (team_b, team_a, give_b)):
        for pid in ids:
            team_repo.remove_player(from_team, pid)
            team_repo.add_player(to_team, pid)
            status_repo.set_status(pid, "minors", since=since)
        _clear_roles(conn, from_team, season_id, ids, effective_date)

    gm_repo = GMRepository(conn)
    for team_id in (team_a, team_b):
        if not gm_repo.get_human_gm_for_team(league_id, team_id):
            _replan_ai_team(conn, league_id, season_id, team_id, effective_date)


def _clear_roles(conn, team_id, season_id, player_ids, effective_date) -> None:
    """Take traded players out of the old team's rotation, bullpen and saved
    lineup, from the next game on."""
    conn.execute(
        """UPDATE team_rotations SET end_date = %s
           WHERE team_id = %s AND season_id = %s AND end_date IS NULL
             AND player_id = ANY(%s)""",
        (effective_date, team_id, season_id, player_ids),
    )
    conn.execute(
        """UPDATE bullpen_roles SET end_date = %s
           WHERE team_id = %s AND season_id = %s AND end_date IS NULL
             AND player_id = ANY(%s)""",
        (effective_date, team_id, season_id, player_ids),
    )
    conn.execute(
        """DELETE FROM gm_lineup_preferences
           WHERE player_id = ANY(%s)
             AND gm_id IN (SELECT id FROM gms WHERE team_id = %s)""",
        (player_ids, team_id),
    )


def _replan_ai_team(conn, league_id, season_id, team_id, effective_date) -> None:
    """An AI team re-picks its 40-man and its rotation and bullpen."""
    players = PlayerRepository(conn).get_players_by_team(team_id)
    if players:
        PlayerStatusRepository(conn).bulk_set(RosterAssigner().assign(players))
    seed_ai_rotations(
        conn,
        season_id,
        {team_id},
        statuses=["26man", "40man"],
        effective_date=effective_date,
        league_id=league_id,
    )


def stance(conn, league_id: str, season_id: str, team_id: str) -> str:
    """contender, seller or neutral, from the standings."""
    rows = StandingsRepository(conn).get_records(league_id, season_id)
    me = next((r for r in rows if r["team_id"] == team_id), None)
    if not me:
        return "neutral"
    played = me["wins"] + me["losses"]
    if played < STANCE_MIN_GAMES or len(rows) <= PLAYOFF_SPOTS:
        return "neutral"
    ranked = sorted(rows, key=lambda r: r["losses"] - r["wins"])
    last_spot = ranked[PLAYOFF_SPOTS - 1]
    games_back = (
        (last_spot["wins"] - me["wins"]) + (me["losses"] - last_spot["losses"])
    ) / 2
    if ranked.index(me) < PLAYOFF_SPOTS or games_back <= CONTENDER_GB:
        return "contender"
    if games_back > SELLER_GB:
        return "seller"
    return "neutral"


def _assets(conn, team_id: str, injuries: dict[str, int]) -> list[Asset]:
    return [
        Asset.from_record(p, injuries.get(p.id, 0))
        for p in PlayerRepository(conn).get_players_by_team(team_id)
    ]


def _league_date(conn, season_id: str) -> str:
    """Today in the league: the last day played, or opening day before any
    games. Offers are dated with it (deadline day's trades read as deadline
    day)."""
    last = trade_deadline.last_played_date(conn, season_id)
    return last or _next_game_date(conn, season_id)


def _next_game_date(conn, season_id: str) -> str:
    """The first day a trade counts from: the next day with games."""
    row = GameRepository(conn).get_next_unplayed_date(season_id)
    if row:
        return row["game_date"]
    return trade_deadline.last_played_date(conn, season_id) or date.today().isoformat()


def _days_left(conn, season_id: str, today: str) -> int:
    row = conn.execute(
        """SELECT MAX(game_date) AS d FROM games
           WHERE season_id = %s AND series_id IS NULL""",
        (season_id,),
    ).fetchone()
    if not row or not row["d"]:
        return 1
    return max(1, (date.fromisoformat(row["d"]) - date.fromisoformat(today)).days + 1)


def _dedupe(ids: list[str]) -> list[str]:
    return list(dict.fromkeys(ids))
