# src/api/services/hr_derby.py
#
# The Home Run Derby in a league (src/league/hr_derby.py has the rules). The
# field is the top home run hitters when the votes for the All-Stars are
# counted, the healthy ones; nobody plays during the break, so it holds
# until the derby. It's played on the break, just before the All-Star Game,
# when the sim reaches the first day after it (sim_next.sim_next_day).

from __future__ import annotations

import random

from src.api.services import all_star
from src.db.repositories.all_star_repo import AllStarRepository
from src.db.repositories.hr_derby_repo import HRDerbyRepository
from src.league import hr_derby


def field(conn, league_id: str, season_id: str) -> list[dict]:
    """The derby's field, seeded, from this season's home runs."""
    hitters = AllStarRepository(conn).candidates(league_id, season_id)
    hurt = all_star._hurt(conn, league_id, [h["player_id"] for h in hitters])
    return hr_derby.field(hitters, hurt)


def play(
    conn, league_id: str, season_id: str, rng: random.Random | None = None
) -> list[dict]:
    """Play the season's derby and save it. Returns its lines, or [] if it
    was played already or there's no field."""
    repo = HRDerbyRepository(conn)
    if repo.played(season_id):
        return []
    entrants = field(conn, league_id, season_id)
    if not entrants:
        return []
    lines = hr_derby.run(entrants, rng or random.Random())
    team = {h["player_id"]: h["team_id"] for h in entrants}
    for r in lines:
        r["team_id"] = team[r["player_id"]]
    repo.save(season_id, lines)
    return lines


def tab_context(conn, league_id: str, season_id: str) -> dict:
    """The derby on the All-Star tab: the field before it's played, the
    bracket round by round after."""
    w = all_star.window(conn, season_id)
    if not w:
        return {}
    ctx = {
        "derby_date": hr_derby.derby_date(w),
        "derby_outs": hr_derby.OUTS_PER_ROUND,
    }
    results = HRDerbyRepository(conn).results(season_id)
    if not results:
        ctx["derby_field"] = field(conn, league_id, season_id)
        return ctx
    rounds = []
    for rnd in sorted({r["round"] for r in results}):
        lines = [r for r in results if r["round"] == rnd]
        matches = []
        for m in sorted({r["match"] for r in lines}):
            pair = sorted(
                (r for r in lines if r["match"] == m), key=lambda r: r["seed"]
            )
            matches.append(pair)
        rounds.append({"name": hr_derby.round_name(len(lines)), "matches": matches})
    final = rounds[-1]["matches"][0]
    ctx["derby_rounds"] = rounds
    ctx["derby_champion"] = next(r for r in final if r["won"])
    ctx["derby_longest"] = max(results, key=lambda r: r["longest"])
    return ctx


def career(conn, player_id: str) -> list[dict]:
    """A player's derbies for his career page: the year, how far he got,
    his home runs and his longest."""
    out = []
    for r in HRDerbyRepository(conn).career(player_id):
        left = r["field"] >> (r["rounds"] - 1)
        reached = "Champion" if r["champion"] else hr_derby.round_name(left)
        out.append({**r, "reached": reached})
    return out
