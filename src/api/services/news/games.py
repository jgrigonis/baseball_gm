# src/api/services/news/games.py
"""
Stories from the days just played (after ``since``, through ``through``):
winning and losing streaks, big games, season and career milestones, and
long injuries.
"""

from __future__ import annotations

from src.api.services.news.names import Names, possessive
from src.db.repositories.news_repo import NewsRepository

WIN_STREAKS = (7, 10, 15, 20)
LOSING_STREAKS = (8, 12, 16)

# (column in player_season_stats, thresholds, how the story says it)
SEASON_MILESTONES = (
    ("bat_home_runs", (30, 40, 50, 60), "home runs"),
    ("bat_hits", (200,), "hits"),
    ("bat_stolen_bases", (50,), "stolen bases"),
    ("pitch_wins", (20,), "wins"),
    ("pitch_strike_outs", (250, 300), "strikeouts"),
    ("pitch_saves", (40,), "saves"),
)
CAREER_MILESTONES = (
    ("bat_home_runs", (100, 200, 300, 400, 500, 600, 700), "career home runs"),
    ("bat_hits", (1000, 1500, 2000, 2500, 3000, 3500, 4000), "career hits"),
    ("pitch_wins", (100, 150, 200, 250, 300), "career wins"),
    ("pitch_strike_outs", (1000, 1500, 2000, 2500, 3000, 4000), "career strikeouts"),
    ("pitch_saves", (200, 300, 400), "career saves"),
)

# player_game_stats names a few columns in the singular.
_GAME_COLUMN = {"pitch_wins": "pitch_win", "pitch_saves": "pitch_save"}

# An injury this long (days) makes the news.
LONG_INJURY_DAYS = 30


def write(conn, names: Names, league_id: str, season_id: str, since, through) -> None:
    news = NewsRepository(conn)
    _streaks(conn, news, names, league_id, season_id, since)
    _big_games(conn, news, names, league_id, season_id, since, through)
    _milestones(conn, news, names, league_id, season_id, since, through)
    _injuries(conn, news, names, league_id, season_id, since, through)


def _after(since) -> str:
    return since or ""


# ── Streaks ───────────────────────────────────────────────────────────────────


def _streaks(conn, news, names, league_id, season_id, since) -> None:
    rows = conn.execute(
        """SELECT tgs.team_id, tgs.win, g.game_date, g.id
           FROM games g JOIN team_game_stats tgs ON tgs.game_id = g.id
           WHERE g.season_id = %s AND g.series_id IS NULL AND g.completed = 1
           ORDER BY tgs.team_id, g.game_date, g.id""",
        (season_id,),
    ).fetchall()
    run: dict[str, tuple[int, int, str]] = {}  # team -> (win 1/0, length, start)
    for r in rows:
        team, won = r["team_id"], r["win"]
        prev = run.get(team)
        if prev and prev[0] == won:
            length, start = prev[1] + 1, prev[2]
        else:
            length, start = 1, r["game_date"]
        run[team] = (won, length, start)
        if r["game_date"] <= _after(since):
            continue
        marks = WIN_STREAKS if won else LOSING_STREAKS
        if length not in marks:
            continue
        gm = names.gm_name(names.gm_of(team))
        if won:
            headline = f"{names.team(team)} win {length} straight"
            if gm:
                headline += f" under {gm}"
            body = (
                f"The {names.full_team(team)} haven't lost since {_day(start)}."
                if length < 10
                else f"The {names.full_team(team)} are the hottest team in the league,"
                f" unbeaten since {_day(start)}."
            )
        else:
            headline = f"{names.team(team)} drop {length} in a row"
            body = f"The {names.full_team(team)} haven't won since {_day(start)}."
            if gm:
                body += f" The pressure is on {gm}."
        news.add(
            league_id, season_id, r["game_date"], "streak",
            f"streak:{team}:{start}:{length}",
            headline, body,
            weight=3 if length >= 10 else 2,
            team_ids=[team], gm_ids=names.gm_ids(team),
        )  # fmt: skip


def _day(iso: str) -> str:
    from datetime import date

    d = date.fromisoformat(iso)
    return f"{d.strftime('%B')} {d.day}"


# ── Big games ─────────────────────────────────────────────────────────────────


def _big_games(conn, news, names, league_id, season_id, since, through) -> None:
    rows = conn.execute(
        """SELECT pgs.game_id, pgs.player_id, pgs.team_id, pgs.opponent_team_id,
                  g.game_date, g.series_id IS NOT NULL AS playoff,
                  COALESCE(pgs.bat_hits, 0) AS h, COALESCE(pgs.bat_doubles, 0) AS d,
                  COALESCE(pgs.bat_triples, 0) AS t, COALESCE(pgs.bat_home_runs, 0) AS hr,
                  COALESCE(pgs.bat_rbi, 0) AS rbi,
                  COALESCE(pgs.pitch_no_hitter, 0) AS no_hitter,
                  COALESCE(pgs.pitch_strike_outs, 0) AS k
           FROM player_game_stats pgs JOIN games g ON g.id = pgs.game_id
           WHERE g.season_id = %s AND g.completed = 1
             AND g.game_date > %s AND g.game_date <= %s
             AND (pgs.bat_home_runs >= 3 OR pgs.pitch_no_hitter = 1
                  OR pgs.pitch_strike_outs >= 15 OR pgs.bat_hits >= 5
                  OR pgs.bat_rbi >= 8
                  OR (pgs.bat_doubles >= 1 AND pgs.bat_triples >= 1 AND pgs.bat_home_runs >= 1
                      AND pgs.bat_hits - pgs.bat_doubles - pgs.bat_triples - pgs.bat_home_runs >= 1))""",
        (season_id, _after(since), through),
    ).fetchall()
    names.load_players(r["player_id"] for r in rows)
    for r in rows:
        pid, team, opp = r["player_id"], r["team_id"], r["opponent_team_id"]
        who = names.player(pid)
        singles = r["h"] - r["d"] - r["t"] - r["hr"]
        if r["no_hitter"]:
            kind, weight = "no_hitter", 3
            headline = f"{who} throws a no-hitter"
            body = f"{who} held the {names.team(opp)} without a hit, striking out {r['k']}."
        elif r["d"] and r["t"] and r["hr"] and singles:
            kind, weight = "cycle", 3
            headline = f"{who} hits for the cycle"
            body = f"Single, double, triple and home run against the {names.team(opp)}."
        elif r["hr"] >= 3:
            kind, weight = "big_game", 2
            word = {3: "three", 4: "four"}.get(r["hr"], str(r["hr"]))
            headline = f"{who} hits {word} home runs"
            body = f"{who} drove in {r['rbi']} against the {names.team(opp)}."
        elif r["k"] >= 15:
            kind, weight = "big_game", 2
            headline = f"{who} strikes out {r['k']}"
            body = f"A dominant start against the {names.team(opp)}."
        elif r["rbi"] >= 8:
            kind, weight = "big_game", 2
            headline = f"{who} drives in {r['rbi']}"
            body = f"{who} had {r['h']} hits against the {names.team(opp)}."
        else:
            kind, weight = "big_game", 1
            headline = f"{who} gets {r['h']} hits"
            body = f"A big day at the plate against the {names.team(opp)}."
        how, credit = names.origin(pid, team)
        body = f"{body} {_credit_line(who, team, names, how)}".strip()
        if r["playoff"]:
            headline += " in the playoffs"
            weight = min(3, weight + 1)
        news.add(
            league_id, season_id, r["game_date"], kind,
            f"{kind}:{r['game_id']}:{pid}",
            headline, body, weight=weight,
            team_ids=[team, opp], player_ids=[pid],
            gm_ids=names.gm_ids(team) + credit,
        )  # fmt: skip


def _credit_line(who: str, team: str, names: Names, how: str) -> str:
    """ "Ruiz was drafted by Josh in 2027 (round 3)." """
    return f"{who.split(' ')[-1]} was {how}." if how else ""


# ── Milestones ────────────────────────────────────────────────────────────────


def _milestones(conn, news, names, league_id, season_id, since, through) -> None:
    cols = sorted({c for c, _, _ in SEASON_MILESTONES + CAREER_MILESTONES})
    window = {
        r["player_id"]: r
        for r in conn.execute(
            f"""SELECT pgs.player_id,
                       {", ".join(f"SUM(COALESCE(pgs.{_GAME_COLUMN.get(c, c)}, 0)) AS {c}" for c in cols)},
                       MAX(g.game_date) AS last_date,
                       (ARRAY_AGG(pgs.team_id ORDER BY g.game_date DESC))[1] AS team_id
                FROM player_game_stats pgs JOIN games g ON g.id = pgs.game_id
                WHERE g.season_id = %s AND g.completed = 1 AND g.series_id IS NULL
                  AND g.game_date > %s AND g.game_date <= %s
                GROUP BY pgs.player_id""",
            (season_id, _after(since), through),
        ).fetchall()
        if any(r[c] for c in cols)
    }
    if not window:
        return
    ids = list(window)
    season = {
        r["player_id"]: r
        for r in conn.execute(
            f"""SELECT player_id, {", ".join(f"SUM({c}) AS {c}" for c in cols)}
                FROM player_season_stats
                WHERE season_id = %s AND NOT is_postseason AND player_id = ANY(%s)
                GROUP BY player_id""",
            (season_id, ids),
        ).fetchall()
    }
    career = {
        r["player_id"]: r
        for r in conn.execute(
            f"""SELECT player_id, {", ".join(f"SUM({c}) AS {c}" for c in cols)}
                FROM player_season_stats
                WHERE NOT is_postseason AND player_id = ANY(%s)
                GROUP BY player_id""",
            (ids,),
        ).fetchall()
    }
    names.load_players(ids)
    crossed = []  # (pid, scope, col, mark, label, before)
    for pid, w in window.items():
        for totals, marks, scope in (
            (season.get(pid), SEASON_MILESTONES, "season"),
            (career.get(pid), CAREER_MILESTONES, "career"),
        ):
            if not totals:
                continue
            for col, thresholds, label in marks:
                now = totals[col] or 0
                before = now - (w[col] or 0)
                for mark in thresholds:
                    if before < mark <= now:
                        crossed.append((pid, scope, col, mark, label, before))
    if not crossed:
        return
    days = _daily(conn, season_id, since, through, {c[0] for c in crossed})
    for pid, scope, col, mark, label, before in crossed:
        # The day he got there: walk his games in the window from where he
        # stood before it.
        on, team, total = window[pid]["last_date"], window[pid]["team_id"], before
        for d in days.get(pid, []):
            total += d[col] or 0
            if total >= mark:
                on, team = d["game_date"], d["team_id"]
                break
        _milestone(
            news, names, league_id, season_id, on, team, pid, scope, col, mark, label
        )


def _daily(conn, season_id, since, through, player_ids) -> dict[str, list[dict]]:
    """Each player's game lines in the window, in order."""
    cols = sorted({c for c, _, _ in SEASON_MILESTONES + CAREER_MILESTONES})
    rows = conn.execute(
        f"""SELECT pgs.player_id, pgs.team_id, g.game_date,
                   {", ".join(f"COALESCE(pgs.{_GAME_COLUMN.get(c, c)}, 0) AS {c}" for c in cols)}
            FROM player_game_stats pgs JOIN games g ON g.id = pgs.game_id
            WHERE g.season_id = %s AND g.completed = 1 AND g.series_id IS NULL
              AND g.game_date > %s AND g.game_date <= %s AND pgs.player_id = ANY(%s)
            ORDER BY g.game_date, g.id""",
        (season_id, _after(since), through, list(player_ids)),
    ).fetchall()
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["player_id"], []).append(r)
    return out


# The first mark of each career milestone is a note; these and up are big news.
_BIG_CAREER = {
    "bat_home_runs": 400, "bat_hits": 2500, "pitch_wins": 200,
    "pitch_strike_outs": 2500, "pitch_saves": 300,
}  # fmt: skip


def _milestone(
    news, names, league_id, season_id, on, team, pid, scope, col, mark, label
):
    who = names.player(pid)
    last = who.split(" ")[-1]
    headline = f"{who} reaches {mark:,} {label}"
    if scope == "season":
        body = f"A big year for {possessive('the ' + names.full_team(team))} {last}."
        weight = 2
    else:
        body = f"A career milestone for {possessive('the ' + names.full_team(team))} {last}."
        first = next(t for c, t, _ in CAREER_MILESTONES if c == col)[0]
        weight = 3 if mark >= _BIG_CAREER[col] else 1 if mark == first else 2
    how, credit = names.origin(pid, team)
    if how:
        body += f" {last} was {how}."
    news.add(
        league_id, season_id, on, "milestone",
        f"milestone:{scope}:{pid}:{col}:{mark}" + (f":{season_id}" if scope == "season" else ""),
        headline, body, weight=weight,
        team_ids=[team], player_ids=[pid], gm_ids=names.gm_ids(team) + credit,
    )  # fmt: skip


# ── Injuries ──────────────────────────────────────────────────────────────────


def _injuries(conn, news, names, league_id, season_id, since, through) -> None:
    rows = conn.execute(
        """SELECT l.id, l.player_id, l.team_id, l.injury_date, l.games_missed,
                  l.activity, p.position,
                  EXISTS (SELECT 1 FROM all_stars a
                          WHERE a.player_id = l.player_id) AS all_star
           FROM player_injury_log l JOIN players p ON p.id = l.player_id
           WHERE l.season_id = %s AND l.injury_date > %s AND l.injury_date <= %s
             AND l.games_missed >= %s AND l.team_id IS NOT NULL
             AND l.team_id IN (SELECT team_id FROM league_season_teams
                               WHERE league_id = %s AND season_id = %s)""",
        (season_id, _after(since), through, LONG_INJURY_DAYS, league_id, season_id),
    ).fetchall()
    names.load_players(r["player_id"] for r in rows)
    for r in rows:
        pid, team, days = r["player_id"], r["team_id"], r["games_missed"]
        who = names.player(pid)
        span = _span(days)
        headline = f"{names.team(team)} lose {who} for {span}"
        body = f"{who}"
        if r["position"]:
            body += f" ({r['position'].upper()})"
        body += " is out"
        if r["activity"]:
            body += f" after getting hurt {_activity(r['activity'])}"
        body += "."
        gm = names.gm_name(names.gm_of(team))
        if gm:
            body += f" {possessive(gm)} depth will be tested."
        news.add(
            league_id, season_id, r["injury_date"], "injury", f"injury:{r['id']}",
            headline, body,
            weight=3 if r["all_star"] and days >= 60 else 2 if r["all_star"] or days >= 60 else 1,
            team_ids=[team], player_ids=[pid], gm_ids=names.gm_ids(team),
        )  # fmt: skip


def _span(days: int) -> str:
    if days >= 120:
        return "the season"
    if days >= 56:
        return f"{round(days / 30)} months"
    return f"{round(days / 7)} weeks"


def _activity(activity: str) -> str:
    a = activity.strip().lower().replace("_", " ")
    return a if a.startswith(("on ", "while ", "in ", "at ")) else f"while {a}"
