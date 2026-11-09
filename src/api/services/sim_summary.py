# src/api/services/sim_summary.py
"""
What the line under the sim buttons says about the GM's own team after each
day: how it did that day, its record, where it stands in its division (or the
league), the playoff race late in the season, and the day's biggest story
about the team from the news feed.

The page adds up the day results over a run, so a run of any length reads
"✓ 4 days · 3-1 (42-31) · 1st in East by 2.5 · Ortiz hits three home runs".

Clinched and eliminated are worked out from the extreme cases, so they're
never wrong, only sometimes a day or two late: clinched when the team still
makes the field after losing every game left while every other team wins all
of theirs; eliminated when it misses even after winning out while every other
team loses out.
"""

from __future__ import annotations

from src.api.services.news.names import plain
from src.db.repositories.standings_repo import StandingsRepository
from src.league import divisions

PLAYOFF_TEAMS = 8

# The playoff race joins the line once the team has this many games left.
LATE_GAMES = 20


def my_day(
    db, league_id: str, season_id: str | None, team_id: str | None, game_date
) -> dict:
    """The GM's team after the day played on ``game_date``; {} when there's
    nothing to say (no team, no season)."""
    if not team_id or not season_id:
        return {}
    records = StandingsRepository(db).get_records(league_id, season_id)
    if not any(r["team_id"] == team_id for r in records):
        return {}
    left = _games_left(db, season_id)
    confs = divisions.load(db, league_id)
    teams = _ranked(db, season_id, records)
    out = {
        **_day_result(db, season_id, team_id, game_date),
        **standing(teams, team_id, confs),
        "games_left": left.get(team_id, 0),
    }
    race = playoff_race(teams, team_id, confs, left)
    if race:
        out["race"] = race
    story = _story(db, league_id, season_id, team_id, game_date)
    if story:
        out["story"] = story
    return out


# ── Standing ──────────────────────────────────────────────────────────────────


def standing(teams: list[dict], team_id: str, confs) -> dict:
    """{"wins", "losses", "standing"}: "1st in East by 2.5", "3rd in East,
    4 back", "Tied for 1st in East", or without divisions "2nd, 1.5 back"."""
    me = next(t for t in teams if t["team_id"] == team_id)
    group, name = teams, ""
    for conf in confs:
        for div in conf.divisions:
            if team_id in div.team_ids:
                group = [t for t in teams if t["team_id"] in div.team_ids]
                name = div.name
    where = f" in {name}" if name else ""
    leader = group[0]
    place = group.index(me) + 1
    if me is leader:
        lead = _gb(group[1], me) if len(group) > 1 else 0
        text = f"1st{where} by {_games(lead)}" if lead > 0 else f"Tied for 1st{where}"
    else:
        back = _gb(me, leader)
        text = (
            f"Tied for 1st{where}"
            if back == 0
            else f"{_ordinal(place)}{where}, {_games(back)} back"
        )
    return {"wins": me["wins"], "losses": me["losses"], "standing": text}


# ── Playoff race ──────────────────────────────────────────────────────────────


def playoff_race(
    teams: list[dict], team_id: str, confs, left: dict[str, int]
) -> str | None:
    """ "Clinched the East", "Clinched a playoff spot" or "Eliminated" when
    the numbers say so; late in the season otherwise "In a playoff spot by
    2" or "2 back of a playoff spot". None early on."""
    if len(teams) < PLAYOFF_TEAMS:
        return None
    mine = left.get(team_id, 0)
    status = clinch_status(teams, team_id, confs, left)
    if status == "division":
        name = _division_name(confs, team_id)
        # "Clinched the East", "Clinched North America East"
        return f"Clinched {name}" if " " in name else f"Clinched the {name}"
    if status == "spot":
        return "Clinched a playoff spot"
    if status == "out":
        return "Eliminated"
    if mine > LATE_GAMES:
        return None
    # How far in or out, against the other teams chasing the same spots.
    pool_ids = _conference_of(confs, team_id) or [t["team_id"] for t in teams]
    pool = [t for t in teams if t["team_id"] in pool_ids]
    field = _field_ids(teams, confs)
    me = next(t for t in teams if t["team_id"] == team_id)
    if team_id in field:
        chasers = [t for t in pool if t["team_id"] not in field]
        if not chasers:
            return None
        lead = _gb(chasers[0], me)
        return (
            f"In a playoff spot by {_games(lead)}"
            if lead > 0
            else "Tied for a playoff spot"
        )
    holders = [t for t in pool if t["team_id"] in field]
    if not holders:
        return None
    back = _gb(me, holders[-1])
    return (
        f"{_games(back)} back of a playoff spot"
        if back > 0
        else "Tied for a playoff spot"
    )


def clinch_status(
    teams: list[dict], team_id: str, confs, left: dict[str, int]
) -> str | None:
    """ "division" (clinched its division), "spot" (clinched a playoff spot),
    "out" (eliminated) or None (still to be decided)."""
    if len(teams) < PLAYOFF_TEAMS:
        return None
    worst = _final(teams, team_id, left, me_best=False)
    div_ids = _division_of(confs, team_id)
    if div_ids and _first_in(worst, div_ids) == team_id:
        return "division"
    if team_id in _field_ids(worst, confs):
        return "spot"
    if team_id not in _field_ids(_final(teams, team_id, left, me_best=True), confs):
        return "out"
    return None


def clinch_marks(
    db, league_id: str, season_id: str, teams: list[dict]
) -> dict[str, str]:
    """{team_id: "division" | "spot" | "out"} for the standings page's
    markers, from ``teams`` (records, any order); undecided teams are left
    out."""
    if len(teams) < PLAYOFF_TEAMS:
        return {}
    ranked = _ranked(db, season_id, teams)
    confs = divisions.load(db, league_id)
    left = _games_left(db, season_id)
    out = {}
    for t in ranked:
        status = clinch_status(ranked, t["team_id"], confs, left)
        if status:
            out[t["team_id"]] = status
    return out


def _final(teams, team_id, left, me_best: bool) -> list[dict]:
    """Every team's final record in one extreme: the GM's team wins out and
    everyone else loses out (me_best), or the other way round. ``teams`` is
    in standings order, tiebreakers applied. A tie with a team is settled by
    that order once neither has a game left (head-to-head and runs are
    final); before then it goes against the GM's team in its worst case and
    to it in its best."""
    order = {t["team_id"]: i for i, t in enumerate(teams)}
    mine_done = left.get(team_id, 0) == 0
    rows = []
    for t in teams:
        n = left.get(t["team_id"], 0)
        mine = t["team_id"] == team_id
        wins_out = mine == me_best
        rows.append(
            {
                **t,
                "wins": t["wins"] + (n if wins_out else 0),
                "losses": t["losses"] + (0 if wins_out else n),
            }
        )
    # Undecided ties put the GM's team at the front (best) or back (worst).
    edge = -1 if me_best else len(teams)

    def key(r):
        played = r["wins"] + r["losses"]
        pct = r["wins"] / played if played else 0.0
        tid = r["team_id"]
        if tid == team_id:
            return (-pct, order[tid] if mine_done else edge)
        if mine_done and left.get(tid, 0) > 0:
            # Its tie with the GM's team isn't settled yet.
            return (-pct, len(teams) if me_best else -1)
        return (-pct, order[tid])

    return sorted(rows, key=key)


def _field_ids(ranked: list[dict], confs) -> set[str]:
    """The teams that would make the playoffs with these standings."""
    order = divisions.playoff_order(confs, ranked) if confs else None
    field = order or ranked[:PLAYOFF_TEAMS]
    return {t["team_id"] for t in field}


def _first_in(ranked: list[dict], ids: list[str]) -> str | None:
    return next((t["team_id"] for t in ranked if t["team_id"] in ids), None)


def _division_of(confs, team_id) -> list[str]:
    for conf in confs:
        for div in conf.divisions:
            if team_id in div.team_ids:
                return div.team_ids
    return []


def _division_name(confs, team_id) -> str:
    for conf in confs:
        for div in conf.divisions:
            if team_id in div.team_ids:
                return div.name
    return ""


def _conference_of(confs, team_id) -> list[str]:
    for conf in confs:
        if team_id in conf.team_ids:
            return conf.team_ids
    return []


# ── Helpers ───────────────────────────────────────────────────────────────────


def _gb(behind: dict, ahead: dict) -> float:
    """How many games ``behind`` trails ``ahead``."""
    return ((ahead["wins"] - behind["wins"]) + (behind["losses"] - ahead["losses"])) / 2


def _games(n: float) -> str:
    return str(int(n)) if n == int(n) else f"{n:.1f}"


def _ordinal(n: int) -> str:
    suffix = (
        "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    )
    return f"{n}{suffix}"


def _ranked(db, season_id: str, records: list[dict]) -> list[dict]:
    rows = [
        {
            **r,
            "win_pct": r["wins"] / (r["wins"] + r["losses"])
            if r["wins"] + r["losses"]
            else 0.0,
        }
        for r in records
    ]
    return StandingsRepository(db).sort(season_id, rows)


def _games_left(db, season_id: str) -> dict[str, int]:
    """Each team's unplayed regular season games."""
    rows = db.execute(
        """SELECT team_id, COUNT(*) AS n FROM (
             SELECT home_team_id AS team_id FROM games
              WHERE season_id = %s AND completed = 0 AND series_id IS NULL
             UNION ALL
             SELECT away_team_id FROM games
              WHERE season_id = %s AND completed = 0 AND series_id IS NULL
           ) g GROUP BY team_id""",
        (season_id, season_id),
    ).fetchall()
    return {r["team_id"]: r["n"] for r in rows}


def _day_result(db, season_id, team_id, game_date) -> dict:
    """{"day_wins", "day_losses"}: the team's games on that day."""
    if not game_date:
        return {"day_wins": 0, "day_losses": 0}
    row = db.execute(
        """SELECT COALESCE(SUM(tgs.win), 0) AS w, COALESCE(SUM(tgs.loss), 0) AS l
           FROM team_game_stats tgs JOIN games g ON g.id = tgs.game_id
           WHERE g.season_id = %s AND g.game_date = %s AND g.completed = 1
             AND g.series_id IS NULL AND tgs.team_id = %s""",
        (season_id, game_date, team_id),
    ).fetchone()
    return {"day_wins": int(row["w"]), "day_losses": int(row["l"])}


def _story(db, league_id, season_id, team_id, game_date) -> dict | None:
    """The day's biggest news story led by the team (a big game, milestone,
    streak or long injury of its own, not one against it)."""
    if not game_date:
        return None
    row = db.execute(
        """SELECT headline, weight FROM league_news
           WHERE league_id = %s AND season_id = %s AND news_date = %s
             AND team_ids[1] = %s
           ORDER BY weight DESC, id DESC LIMIT 1""",
        (league_id, season_id, game_date, team_id),
    ).fetchone()
    return (
        {"headline": plain(row["headline"]), "weight": row["weight"]} if row else None
    )
