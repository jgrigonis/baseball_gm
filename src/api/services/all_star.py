# src/api/services/all_star.py
#
# All-Star voting in a league (src/league/all_star.py has the rules).
#
# The ballot opens all_star.VOTING_DAYS before the All-Star break. A GM's
# ballot starts out filled in with the stat-based picks; they change what
# they like and save it, as often as they like until it closes. After the
# games of the last day before the break the votes are counted: a person's
# saved ballot, or the stat-based one if they never saved, and a ballot for
# each AI team, cast by its GM's persona. The 64 players voted in are the
# All-Stars and get a star by their name.
#
# The All-Star Game. The GMs of the two best teams when the votes are
# counted are its captains: captain 1, the better record, is the home side
# and picks first in a snake draft of the 64. An AI captain picks as soon as
# it's his turn; a person picks on the All-Star tab, or lets the scouts
# finish for him. If the last wildcard spot was a tie on points and captain
# 2 is a person, he picks who gets it before the draft starts; an AI captain
# leaves it to the stats (all_star.select_pool).
#
# An All-Star who's hurt keeps the honor but sits out: he isn't on the
# draft board and doesn't play. The healthy player at his position with the
# most votes is named a reserve in his place (all_star.reserves). Hurt goes
# by the league's injury date (InjuryRepository.current_date), which stays
# the first day of the break until play resumes, so the tab, the draft and
# the game all agree on who's out.
#
# The game is played on the break (all_star.game_date), when the sim reaches
# the first game day after it. Any picks still to make, and an unbroken tie,
# are made for the captains then. It's an exhibition: nobody gets tired or
# hurt, every pitcher comes out after all_star.PITCHER_OUTS_CAP outs, and
# the lines are kept in all_star_game_stats, apart from the season's.
#
# Every sim stops the day the ballot opens, after the votes are counted and
# after the game, so a GM doesn't play straight past any of them.
#
# The Rookie Game (src/api/services/rookie_game.py) is run the same way: its
# draft and game are these functions with event="rookie", which keeps them
# in its own tables (AllStarRepository) with its own draft needs.

from __future__ import annotations

from datetime import date
import logging
import random

from src.db.repositories.all_star_repo import AllStarRepository
from src.db.repositories.games_repo import GameRepository
from src.db.repositories.hr_derby_repo import HRDerbyRepository
from src.db.repositories.gm_repo import GMRepository
from src.db.repositories.injury_repo import InjuryRepository
from src.db.repositories.persona_repo import PersonaRepository
from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.player_season_stats_repo import PlayerSeasonStatsRepository
from src.db.repositories.standings_repo import StandingsRepository
from src.db.repositories.team_repo import TeamRepository
from src.game.game import Game
from src.league import all_star, hr_derby, rookie_game
from src.team.manager_profile import ManagerProfile
from src.team.team_in_game import TeamInGame
from src.team.team_record import TeamRecord

log = logging.getLogger(__name__)


def window(conn, season_id: str | None) -> all_star.Window | None:
    if not season_id:
        return None
    return all_star.window(AllStarRepository(conn).game_dates(season_id))


def phase(conn, season_id: str | None) -> str:
    """Where this season's All-Stars are: "none" (no break, or the break
    went by without a vote), "upcoming", "open" (the ballot), "done" (voted
    in, the game still to come) or "played"."""
    w = window(conn, season_id)
    if not w:
        return "none"
    repo = AllStarRepository(conn)
    if repo.has_all_stars(season_id):
        g = repo.game(season_id)
        return "played" if g and g["state"] == "played" else "done"
    row = GameRepository(conn).get_next_unplayed_date(season_id)
    today = row["game_date"] if row else None
    if today is None or today > w.closes:
        return "none"
    return "open" if today >= w.opens else "upcoming"


def candidates(conn, league_id: str, season_id: str) -> list[dict]:
    """Everyone on the ballot, scored (all_star.add_features)."""
    games = PlayerSeasonStatsRepository(conn).get_max_games_played(season_id)
    players = AllStarRepository(conn).candidates(league_id, season_id)
    return all_star.add_features(all_star.on_ballot(players, games))


def submit(conn, league_id: str, season_id: str, team_id: str, raw: dict) -> dict:
    """Save a GM's ballot. Raises ValueError when the ballot isn't open."""
    if phase(conn, season_id) != "open":
        raise ValueError("All-Star voting isn't open.")
    ballot = all_star.clean_ballot(raw, candidates(conn, league_id, season_id))
    AllStarRepository(conn).save_ballot(season_id, team_id, ballot)
    return ballot


def count_votes(
    conn, league_id: str, season_id: str, rng: random.Random | None = None
) -> list[dict]:
    """Close the ballot: cast the ballots nobody saved, count every team's
    and save the All-Stars. Does nothing if they're already picked."""
    repo = AllStarRepository(conn)
    if repo.has_all_stars(season_id):
        return []
    rng = rng or random.Random()
    cands = candidates(conn, league_id, season_id)
    saved = repo.ballots(season_id)
    people = GMRepository(conn).get_human_team_ids(league_id)
    dials = PersonaRepository(conn).ai_dials(league_id)
    teams = TeamRepository(conn).get_teams_in_league_season(league_id, season_id)
    ballots = []
    for team in teams:
        tid = team["id"]
        if tid in saved:
            ballots.append(saved[tid])
            continue
        if tid in people:
            b = all_star.ballot(cands)
        else:
            b = all_star.ballot(cands, dials.get(tid), tid, rng)
        repo.save_ballot(season_id, tid, b)
        ballots.append(b)
    pts = all_star.tally(ballots)
    pool = all_star.select_pool(cands, pts)
    tied = all_star.last_spot_tie(cands, pts, pool)
    captains = _captains(conn, season_id)
    if tied and captains and captains[1] in people:
        pool = pool[:-1]  # captain 2 picks who gets it
    else:
        tied = []  # the stats settled it
    repo.save_all_stars(season_id, pool)
    name_reserves(conn, league_id, season_id, cands, pts)
    if captains:
        w = window(conn, season_id)
        repo.create_game(season_id, *captains, all_star.game_date(w), tied)
        draft(conn, league_id, season_id)
    # The rookies are picked once the All-Stars are known.
    from src.api.services import rookie_game as rookies

    rookies.select(conn, league_id, season_id)
    return pool


def _captains(conn, season_id: str) -> list[str] | None:
    """The two best teams' ids, the better first, or None before there's a
    standings to go by."""
    try:
        top = StandingsRepository(conn).get_top_n(season_id, 2)
    except ValueError:
        return None
    return [r["team_id"] for r in top]


# ── The captains ─────────────────────────────────────────────────────────────


def _hurt(conn, league_id: str, player_ids) -> set[str]:
    """Which of these players are hurt, as of the league's injury date."""
    return InjuryRepository(conn, league_id).get_injured_ids(list(player_ids), None)


def stars_with_injuries(
    conn, league_id: str, season_id: str, event: str = "all_star"
) -> list[dict]:
    """The season's All-Stars (AllStarRepository.all_stars), each with
    "hurt": whether he's out of the draft and the game."""
    stars = AllStarRepository(conn, event).all_stars(season_id)
    hurt = _hurt(conn, league_id, [r["player_id"] for r in stars])
    for r in stars:
        r["hurt"] = r["player_id"] in hurt
    return stars


def _board(stars: list[dict]) -> list[dict]:
    """The All-Stars in the draft: the healthy ones, and anyone already
    picked."""
    return [r for r in stars if not r["hurt"] or r["side"]]


def name_reserves(
    conn,
    league_id: str,
    season_id: str,
    cands: list[dict] | None = None,
    pts: dict | None = None,
) -> list[dict]:
    """Name a reserve for every hurt All-Star who doesn't have one yet."""
    repo = AllStarRepository(conn)
    stars = stars_with_injuries(conn, league_id, season_id)
    hurt = {r["player_id"] for r in stars if r["hurt"]}
    if not hurt:
        return []
    if cands is None:
        cands = candidates(conn, league_id, season_id)
    if pts is None:
        pts = all_star.tally(repo.ballots(season_id).values())
    hurt |= _hurt(conn, league_id, [c["player_id"] for c in cands])
    rows = all_star.reserves(cands, pts, stars, hurt)
    repo.save_all_stars(season_id, rows)
    return rows


def _people(conn, league_id: str) -> set[str]:
    return GMRepository(conn).get_human_team_ids(league_id)


def turn(g: dict | None, stars: list[dict]) -> str | None:
    """The team id of the captain who's up: captain 2 while there's a tie to
    break, then whoever has the next pick. None once the draft is done."""
    if not g or g["state"] == "played":
        return None
    if g["state"] == "tie":
        return g["captain2_team_id"]
    made = sum(1 for r in stars if r["side"])
    if made >= len(stars):
        return None
    side = all_star.side_to_pick(made + 1)
    return g[f"captain{side}_team_id"]


def my_turn(conn, league_id: str, season_id: str | None, team_id) -> bool:
    """Whether this team's GM, a person, has a pick to make in the All-Star
    or the Rookie Game draft."""
    if not season_id or not team_id:
        return False
    for event in EVENTS:
        g = AllStarRepository(conn, event).game(season_id)
        if not g or g["state"] == "played":
            continue
        stars = _board(stars_with_injuries(conn, league_id, season_id, event))
        if turn(g, stars) == team_id:
            return True
    return False


EVENTS = ("all_star", "rookie")


def person_drafting(conn, league_id: str, season_id: str | None) -> bool:
    """Whether a person has picks to make in the All-Star or the Rookie Game
    draft (or the tie to break). AI picks are made as soon as it's their
    turn, so whenever a draft isn't finished it's waiting on a person. The
    ready-check gives that period the Lineup Window, not the Decision
    Window: 30-odd picks take longer than one decision."""
    if not season_id:
        return False
    people = _people(conn, league_id)
    for event in EVENTS:
        g = AllStarRepository(conn, event).game(season_id)
        if not g or g["state"] == "played":
            continue
        stars = _board(stars_with_injuries(conn, league_id, season_id, event))
        if turn(g, stars) in people:
            return True
    return False


def _needs(event: str) -> dict[str, int]:
    """What an AI captain fills first in this event's draft."""
    return rookie_game.SIDE_NEEDS if event == "rookie" else all_star.SIDE_NEEDS


def _add_tied(conn, league_id: str, season_id: str, player_id: str) -> None:
    """Put one of the players tied for the last spot in the pool."""
    cands = {c["player_id"]: c for c in candidates(conn, league_id, season_id)}
    repo = AllStarRepository(conn)
    c = cands.get(player_id)
    if not c:
        return
    pts = all_star.tally(repo.ballots(season_id).values())
    repo.save_all_stars(
        season_id,
        [
            {
                "player_id": player_id,
                "team_id": c["team_id"],
                "slot": c["slot"],
                "points": pts.get(player_id, 0),
                "wildcard": True,
                "score": all_star.score(c),
            }
        ],
    )


def break_tie(conn, league_id: str, season_id: str, team_id: str, player_id: str):
    """Captain 2 picks who gets the last spot. Raises ValueError if it isn't
    his to pick."""
    repo = AllStarRepository(conn)
    g = repo.game(season_id)
    if not g or g["state"] != "tie":
        raise ValueError("There's no tie to break.")
    if team_id != g["captain2_team_id"]:
        raise ValueError("Only the second captain breaks the tie.")
    if player_id not in g["tied_ids"]:
        raise ValueError("That player isn't in the tie.")
    _add_tied(conn, league_id, season_id, player_id)
    repo.set_state(season_id, "draft")
    name_reserves(conn, league_id, season_id)
    draft(conn, league_id, season_id)


def draft(
    conn,
    league_id: str,
    season_id: str,
    everyone: bool = False,
    event: str = "all_star",
) -> int:
    """Make the picks of the captains who don't pick for themselves: AI
    captains, people who left it to the scouts (auto_draft), or everyone.
    Stops at a person's turn. Returns how many picks it made."""
    repo = AllStarRepository(conn, event)
    g = repo.game(season_id)
    if not g or g["state"] != "draft":
        return 0
    people = _people(conn, league_id)
    auto = {g[f"captain{s}_team_id"] for s in (1, 2) if g[f"auto{s}"]}
    stars = _board(stars_with_injuries(conn, league_id, season_id, event))
    made = sum(1 for r in stars if r["side"])
    n = 0
    while made < len(stars):
        side = all_star.side_to_pick(made + 1)
        team = g[f"captain{side}_team_id"]
        if team in people and team not in auto and not everyone:
            break
        available = [r for r in stars if not r["side"]]
        mine = [r for r in stars if r["side"] == side]
        r = all_star.ai_pick(available, mine, _needs(event))
        made += 1
        n += 1
        repo.add_pick(season_id, r["player_id"], side, made)
        r["side"], r["pick"] = side, made
    return n


def auto_draft(
    conn,
    league_id: str,
    season_id: str,
    team_id: str,
    _player_id=None,
    event: str = "all_star",
):
    """A captain leaves the rest of his picks to the scouts. Raises
    ValueError if he isn't a captain."""
    repo = AllStarRepository(conn, event)
    g = repo.game(season_id)
    side = next((s for s in (1, 2) if g and g[f"captain{s}_team_id"] == team_id), None)
    if not side or g["state"] == "played":
        raise ValueError(f"You aren't {A_TITLE[event]} captain.")
    repo.set_auto(season_id, side)
    draft(conn, league_id, season_id, event=event)


def pick(
    conn,
    league_id: str,
    season_id: str,
    team_id: str,
    player_id: str,
    event: str = "all_star",
):
    """A person's pick in the draft; the AI captain's picks that follow are
    made straight away. Raises ValueError if it isn't his pick to make."""
    repo = AllStarRepository(conn, event)
    g = repo.game(season_id)
    if not g or g["state"] != "draft":
        raise ValueError(f"The {TITLES[event]} draft isn't on.")
    stars = _board(stars_with_injuries(conn, league_id, season_id, event))
    if turn(g, stars) != team_id:
        raise ValueError("It isn't your pick.")
    r = next((r for r in stars if r["player_id"] == player_id), None)
    if not r or r["side"]:
        raise ValueError("That player isn't available.")
    made = sum(1 for r in stars if r["side"])
    repo.add_pick(season_id, player_id, all_star.side_to_pick(made + 1), made + 1)
    draft(conn, league_id, season_id, event=event)


TITLES = {"all_star": "All-Star", "rookie": "Rookie Game"}
A_TITLE = {"all_star": "an All-Star", "rookie": "a Rookie Game"}
MASCOTS = {"all_star": "All-Stars", "rookie": "Rookies"}


# ── The game ─────────────────────────────────────────────────────────────────


def game_due(conn, season_id: str, game_date: str) -> bool:
    """Whether the All-Star Game is to be played before this day's games:
    it's the first day after the break and the game hasn't been played."""
    w = window(conn, season_id)
    if not w or game_date != w.resumes:
        return False
    repo = AllStarRepository(conn)
    if not repo.has_all_stars(season_id):
        return False
    g = repo.game(season_id)
    return not g or g["state"] != "played"


def game_day(conn, season_id: str, next_date: str) -> str | None:
    """The date of the All-Star weekend's first unplayed event when the
    weekend is the next thing to play (the next games are the first after
    the break and the All-Star Game hasn't been played), so the league's date
    shows the weekend, not the day play resumes. The weekend runs in order:
    the Rookie Game, then the Home Run Derby, then the All-Star Game."""
    if not game_due(conn, season_id, next_date):
        return None
    w = window(conn, season_id)
    rookie = AllStarRepository(conn, "rookie").game(season_id)
    if rookie and rookie["state"] != "played":
        return rookie["game_date"]
    if not HRDerbyRepository(conn).played(season_id):
        return hr_derby.derby_date(w)
    g = AllStarRepository(conn).game(season_id)
    if g:
        return g["game_date"]
    return all_star.game_date(w)


def play_game(
    conn,
    league_id: str,
    season_id: str,
    rng: random.Random | None = None,
    event: str = "all_star",
) -> dict | None:
    """Finish the draft and play the All-Star Game (or with event="rookie",
    the Rookie Game), saving the score, every player's line and the MVP.
    Returns the result, or None if there's no game to play."""
    repo = AllStarRepository(conn, event)
    g = repo.game(season_id)
    if not g and event != "all_star":
        return None
    if not g:
        # The votes were counted before there was a game to pick for.
        captains = _captains(conn, season_id)
        if not captains:
            return None
        w = window(conn, season_id)
        repo.create_game(season_id, *captains, all_star.game_date(w), [])
        g = repo.game(season_id)
    if g["state"] == "played":
        return None
    if g["state"] == "tie":
        # Captain 2 never picked: the stats decide, as for an AI captain.
        _add_tied(conn, league_id, season_id, g["tied_ids"][0])
        repo.set_state(season_id, "draft")
    if event == "all_star":
        name_reserves(conn, league_id, season_id)
    draft(conn, league_id, season_id, everyone=True, event=event)

    rng = rng or random.Random()
    stars = stars_with_injuries(conn, league_id, season_id, event)
    injured = {r["player_id"] for r in stars if r["hurt"]}
    players = PlayerRepository(conn)
    gms = GMRepository(conn)
    sides: dict[int, TeamInGame] = {}
    starting: dict[int, dict[str, tuple[int, str]]] = {}
    for side in (1, 2):
        team_id = g[f"captain{side}_team_id"]
        mine = [r for r in stars if r["side"] == side and not r["hurt"]]
        records = [players.look_up(r["player_id"]) for r in mine]
        team = TeamInGame(
            TeamRecord(
                id=team_id,
                city=g[f"city{side}"],
                mascot=MASCOTS[event],
                players=tuple(p for p in records if p),
            )
        )
        team.profile = ManagerProfile.from_row(gms.get_team_profile(team_id, league_id))
        sides[side] = team
    game = Game(
        sides[1],
        sides[2],
        rng=rng,
        game_date=date.fromisoformat(g["game_date"]),
        injured_ids=injured,
        injuries_enabled=False,
        max_pitcher_outs=all_star.PITCHER_OUTS_CAP,
    )
    for side, team in sides.items():
        team.set_lineup(
            starting_pitcher_id=_starter(stars, side, injured),
            dh=True,
            injured_ids=injured,
            style=team.profile.lineup_style,
        )
        starting[side] = {
            s.player.id: (i, s.position) for i, s in enumerate(team.lineup, 1)
        }
    result = game.play()

    lines = []
    for side, team in sides.items():
        order: dict[str, int] = {}
        for a in game.pitcher_appearances:
            if a.team_id == team.record.id and a.pitcher.id not in order:
                order[a.pitcher.id] = len(order) + 1
        for p in team.players:
            played = p.game_stats.batting.plate_appearances
            if p.id in starting[side] or p.id in order or played:
                lines.append(_game_line(p, side, starting[side].get(p.id), order))
    score1, score2 = result.home_score, result.away_score
    winner = 1 if score1 > score2 else 2
    mvp = all_star.mvp(lines, winner)
    line_score = {"1": list(result.home_innings), "2": list(result.away_innings)}
    repo.save_lines(season_id, lines)
    repo.save_result(season_id, score1, score2, result.innings_played, line_score, mvp)
    return {
        "score1": score1,
        "score2": score2,
        "innings": result.innings_played,
        "mvp_player_id": mvp,
    }


def _starter(stars: list[dict], side: int, injured: set) -> str | None:
    """The side's starting pitcher: its pitcher with the most votes."""
    arms = [
        r
        for r in stars
        if r["side"] == side and r["slot"] == "p" and r["player_id"] not in injured
    ]
    if not arms:
        return None
    return max(arms, key=lambda r: (r["points"], r["score"]))["player_id"]


def _game_line(p, side: int, start: tuple | None, pitch_order: dict) -> dict:
    """A player's line in the game, as all_star_game_stats keeps it."""
    b = p.game_stats.batting
    k = p.game_stats.pitching
    return {
        "player_id": p.id,
        "side": side,
        "position": start[1] if start else ("p" if p.id in pitch_order else None),
        "batting_order": start[0] if start else None,
        "bat_ab": b.at_bats,
        "bat_runs": b.runs,
        "bat_hits": b.hits,
        "bat_doubles": b.doubles,
        "bat_triples": b.triples,
        "bat_home_runs": b.home_runs,
        "bat_rbi": b.rbi,
        "bat_walks": b.walks,
        "bat_strike_outs": b.strike_outs,
        "bat_stolen_bases": b.sb,
        "pitch_order": pitch_order.get(p.id),
        "pitch_outs": k.outs,
        "pitch_hits": k.hits,
        "pitch_runs": k.runs,
        "pitch_earned_runs": k.earned_runs,
        "pitch_walks": k.walks,
        "pitch_strike_outs": k.strike_outs,
        "pitch_home_runs": k.home_runs,
        "pitch_win": bool(k.win),
        "pitch_loss": bool(k.loss),
        "pitch_save": bool(k.save),
    }


def after_day(conn, league_id: str, season_id: str, game_date: str) -> dict:
    """After a day's games: whether the ballot just opened, and count the
    votes if that was the last day before the break. Returns
    {"all_star_voting": bool, "all_stars": bool}."""
    w = window(conn, season_id)
    out = {"all_star_voting": False, "all_stars": False}
    if not w or AllStarRepository(conn).has_all_stars(season_id):
        return out
    if game_date == w.closes:
        count_votes(conn, league_id, season_id)
        out["all_stars"] = True
    elif game_date < w.opens and phase(conn, season_id) == "open":
        out["all_star_voting"] = True
    return out


def _team(c: dict) -> dict:
    return {"city": c["city"], "mascot": c["mascot"]}


def tab_context(conn, league_id: str, season_id: str | None, team_id) -> dict:
    """What the All-Star tab shows: the ballot while it's open (this team's
    saved picks, or the stat-based ones), the All-Stars once it's closed."""
    p = phase(conn, season_id)
    w = window(conn, season_id)
    ctx = {
        "as_phase": p,
        "as_window": w,
        "slots": all_star.SLOTS,
        "slot_labels": all_star.SLOT_LABELS,
        "ballot_size": all_star.BALLOT,
        "quota": all_star.QUOTA,
        "voting_days": all_star.VOTING_DAYS,
    }
    if p == "open":
        repo = AllStarRepository(conn)
        cands = candidates(conn, league_id, season_id)
        saved = repo.ballot(season_id, team_id) if team_id else None
        ballot = saved or all_star.ballot(cands)
        neutral = {c["player_id"]: all_star.score(c) for c in cands}
        options = {}
        for slot in all_star.SLOTS:
            at = sorted(
                (c for c in cands if c["slot"] == slot),
                key=lambda c: -neutral[c["player_id"]],
            )
            options[slot] = [
                {
                    "id": c["player_id"],
                    "name": c["name"],
                    "line": _line(c),
                    "stats": _full_stats(c),
                    **_team(c),
                }
                for c in at
            ]
        ctx.update(
            ballot={s: list(ballot.get(s) or []) for s in all_star.SLOTS},
            options=options,
            stat_heads={"bat": BAT_HEADS, "pitch": PITCH_HEADS},
            saved=saved is not None,
            voted=repo.voted_count(season_id),
            teams=len(
                TeamRepository(conn).get_teams_in_league_season(league_id, season_id)
            ),
        )
    elif p in ("done", "played"):
        repo = AllStarRepository(conn)
        stars = stars_with_injuries(conn, league_id, season_id)
        voted = [r for r in stars if not r["replaces"]]
        names = {r["player_id"]: r["name"] for r in stars}
        ctx["by_slot"] = {
            s: [r for r in voted if r["slot"] == s and not r["wildcard"]]
            for s in all_star.SLOTS
        }
        ctx["wildcards"] = [r for r in voted if r["wildcard"]]
        ctx["reserves"] = [
            {**r, "for_name": names.get(r["replaces"], "")}
            for r in stars
            if r["replaces"]
        ]
        ctx["my_count"] = sum(1 for r in stars if r["team_id"] == team_id)
        ctx["total"] = len(voted)
        g = repo.game(season_id)
        if g:
            ctx["asg"] = game_context(conn, league_id, season_id, team_id, g, stars)
    return ctx


def game_context(
    conn, league_id, season_id, team_id, g, stars, event: str = "all_star"
) -> dict:
    """The All-Star Game part of the tab (or with event="rookie", the Rookie
    Game's): the tie and the draft before it's played, the line score and
    box score after. The game's partial reads it as `x`."""
    captains = {1: g["captain1_team_id"], 2: g["captain2_team_id"]}
    out = [r for r in stars if r["hurt"] and not r["side"]]
    stars = _board(stars)
    up = turn(g, stars)
    ctx = {
        "game": g,
        "event": event,
        "path": "" if event == "all_star" else "/rookie",
        "captains": captains,
        "my_side": next((s for s, t in captains.items() if t == team_id), None),
        "up_side": next((s for s, t in captains.items() if t == up), None),
        "my_turn": bool(team_id) and up == team_id,
        "people": _people(conn, league_id),
        "sides": {
            s: sorted((r for r in stars if r["side"] == s), key=lambda r: r["pick"])
            for s in (1, 2)
        },
        "picks_made": sum(1 for r in stars if r["side"]),
        "draft_total": len(stars),
        "out_hurt": out,
        "pitcher_outs_cap": all_star.PITCHER_OUTS_CAP,
    }
    if g["state"] == "tie":
        cands = {c["player_id"]: c for c in candidates(conn, league_id, season_id)}
        pts = all_star.tally(AllStarRepository(conn).ballots(season_id).values())
        hurt = _hurt(conn, league_id, g["tied_ids"])
        ctx["tied"] = [
            {
                "player_id": pid,
                "hurt": pid in hurt,
                "name": cands[pid]["name"],
                "slot": cands[pid]["slot"],
                "line": _line(cands[pid]),
                "points": pts.get(pid, 0),
                **_team(cands[pid]),
            }
            for pid in g["tied_ids"]
            if pid in cands
        ]
    elif g["state"] == "draft":
        left = sorted(
            (r for r in stars if not r["side"]),
            key=lambda r: (-r["points"], -r["score"]),
        )
        ctx["available"] = {
            s: [r for r in left if r["slot"] == s] for s in all_star.SLOTS
        }
    else:
        lines = AllStarRepository(conn, event).lines(season_id)
        ctx["batting"] = {
            s: [r for r in lines if r["side"] == s and r["batting_order"]]
            for s in (1, 2)
        }
        ctx["pitching"] = {
            s: sorted(
                (r for r in lines if r["side"] == s and r["pitch_order"]),
                key=lambda r: r["pitch_order"],
            )
            for s in (1, 2)
        }
        innings = max(9, g["innings"] or 9)
        ls = g["line_score"] or {}
        ctx["innings"] = list(range(1, innings + 1))
        ctx["line_score"] = {
            s: _inning_runs(
                ls.get(str(s), []), innings, s == 1 and g["score1"] > g["score2"]
            )
            for s in (1, 2)
        }
        ctx["hits"] = {
            s: sum(r["bat_hits"] for r in lines if r["side"] == s) for s in (1, 2)
        }
        mvp = next((r for r in lines if r["player_id"] == g["mvp_player_id"]), None)
        ctx["mvp"] = mvp
        ctx["mvp_line"] = all_star.line_text(mvp) if mvp else ""
    return ctx


def _inning_runs(runs: list, innings: int, home_won: bool) -> list:
    """A side's runs by inning for the line score, 0 for an inning it batted
    and didn't score, and an X for the home side's unplayed last half."""
    out = [runs[i] if i < len(runs) else 0 for i in range(innings)]
    if home_won and not out[-1]:  # no walk-off: ahead after the top half
        out[-1] = "X"
    return out


def _line(c: dict) -> str:
    """A short stat line for the ballot's player lists."""
    if c["slot"] == "p":
        ip = c["pitch_outs"] / 3
        era = 27 * c["pitch_earned_runs"] / c["pitch_outs"] if c["pitch_outs"] else 0
        tail = f", {c['pitch_saves']} SV" if c["pitch_saves"] else ""
        return (
            f"{c['pitch_wins']} W, {era:.2f} ERA, {c['pitch_strike_outs']} K, "
            f"{ip:.0f} IP{tail}"
        )
    avg = c["bat_hits"] / c["bat_ab"] if c["bat_ab"] else 0
    return (
        f"{avg:.3f}".lstrip("0")
        + f", {c['bat_home_runs']} HR, {c['bat_rbi']} RBI, {c['bat_stolen_bases']} SB"
    )


# The ballot's full list at a position: every column the GM might weigh.
BAT_HEADS = (
    "G",
    "AB",
    "R",
    "H",
    "2B",
    "3B",
    "HR",
    "RBI",
    "BB",
    "SO",
    "SB",
    "AVG",
    "OBP",
    "SLG",
    "OPS",
)
PITCH_HEADS = ("G", "GS", "W", "L", "SV", "IP", "H", "HR", "BB", "SO", "ERA", "WHIP")


def _rate(x: float) -> str:
    return f"{x:.3f}".lstrip("0") if x < 1 else f"{x:.3f}"


def _full_stats(c: dict) -> list[tuple[str, float]]:
    """The ballot list's stat columns for a candidate, in the order of
    BAT_HEADS or PITCH_HEADS: (what it shows, what it sorts by)."""
    g = c.get
    if c["slot"] == "p":
        outs = g("pitch_outs", 0)
        ip = f"{outs // 3}.{outs % 3}"
        era = 27 * g("pitch_earned_runs", 0) / outs if outs else 0.0
        whip = 3 * (g("pitch_walks", 0) + g("pitch_hits", 0)) / outs if outs else 0.0
        cols = [
            g(k, 0)
            for k in (
                "pitch_games_played",
                "pitch_games_started",
                "pitch_wins",
                "pitch_losses",
                "pitch_saves",
            )
        ]
        out = [(str(v), v) for v in cols]
        out.append((ip, outs / 3))
        out += [
            (str(g(k, 0)), g(k, 0))
            for k in (
                "pitch_hits",
                "pitch_home_runs",
                "pitch_walks",
                "pitch_strike_outs",
            )
        ]
        out += [(f"{era:.2f}", era), (f"{whip:.2f}", whip)]
        return out
    ab, h = g("bat_ab", 0), g("bat_hits", 0)
    bb, hbp, sf = g("bat_walks", 0), g("bat_hbp", 0), g("bat_sac_flys", 0)
    d, t, hr = g("bat_doubles", 0), g("bat_triples", 0), g("bat_home_runs", 0)
    avg = h / ab if ab else 0.0
    obp_den = ab + bb + hbp + sf
    obp = (h + bb + hbp) / obp_den if obp_den else 0.0
    slg = (h + d + 2 * t + 3 * hr) / ab if ab else 0.0
    counts = [
        g("bat_games_played", 0),
        ab,
        g("bat_runs", 0),
        h,
        d,
        t,
        hr,
        g("bat_rbi", 0),
        bb,
        g("bat_strike_outs", 0),
        g("bat_stolen_bases", 0),
    ]
    out = [(str(v), v) for v in counts]
    out += [(_rate(v), v) for v in (avg, obp, slg, obp + slg)]
    return out
