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
# Every sim stops the day the ballot opens and after the votes are counted,
# so a GM doesn't play straight past either.

from __future__ import annotations

import random

from src.db.repositories.all_star_repo import AllStarRepository
from src.db.repositories.games_repo import GameRepository
from src.db.repositories.gm_repo import GMRepository
from src.db.repositories.persona_repo import PersonaRepository
from src.db.repositories.player_season_stats_repo import PlayerSeasonStatsRepository
from src.db.repositories.team_repo import TeamRepository
from src.league import all_star


def window(conn, season_id: str | None) -> all_star.Window | None:
    if not season_id:
        return None
    return all_star.window(AllStarRepository(conn).game_dates(season_id))


def phase(conn, season_id: str | None) -> str:
    """Where this season's vote is: "none" (no break, or the break went by
    without one), "upcoming", "open" or "done"."""
    w = window(conn, season_id)
    if not w:
        return "none"
    if AllStarRepository(conn).has_all_stars(season_id):
        return "done"
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
    pool = all_star.select_pool(cands, all_star.tally(ballots))
    repo.save_all_stars(season_id, pool)
    return pool


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
                    **_team(c),
                }
                for c in at
            ]
        ctx.update(
            ballot={s: list(ballot.get(s) or []) for s in all_star.SLOTS},
            options=options,
            saved=saved is not None,
            voted=repo.voted_count(season_id),
            teams=len(
                TeamRepository(conn).get_teams_in_league_season(league_id, season_id)
            ),
        )
    elif p == "done":
        stars = AllStarRepository(conn).all_stars(season_id)
        ctx["by_slot"] = {
            s: [r for r in stars if r["slot"] == s and not r["wildcard"]]
            for s in all_star.SLOTS
        }
        ctx["wildcards"] = [r for r in stars if r["wildcard"]]
        ctx["my_count"] = sum(1 for r in stars if r["team_id"] == team_id)
        ctx["total"] = len(stars)
    return ctx


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
