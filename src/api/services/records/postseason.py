# src/api/services/records/postseason.py
"""
Postseason records, worked out from the playoff box scores on each visit
(a few dozen games a year): single games, a whole series, a postseason
career, and titles. Backstory playoffs have results but no box scores, so
only titles reach back before the league started; the rest start empty.

Series rate stats (AVG, OBP, SLG, OPS, ERA, WHIP) are a top ten, not a
record: a .600 series is common. They need 3.1 PA or 1 inning per game of
the series, and a tie goes to the one who played more.
"""

from __future__ import annotations

from collections import defaultdict

from src.api.services.career import ROUND_OF_SERIES
from src.api.services.records import seasons
from src.api.services.records.core import Card, card
from src.api.services.records.defs import GAME_STATS

TOP = 60
SERIES_FLOORS = {"H": 12, "HR": 5, "2B": 5, "3B": 3, "R": 9, "RBI": 14, "SB": 5,
                 "BB": 8, "K": 12, "PK": 25}  # fmt: skip
SERIES_COLS = [
    "bat_ab", "bat_hits", "bat_doubles", "bat_triples", "bat_home_runs", "bat_rbi",
    "bat_runs", "bat_walks", "bat_strike_outs", "bat_hbp", "bat_sac_flys",
    "bat_stolen_bases", "pitch_outs", "pitch_strike_outs", "pitch_hits",
    "pitch_walks", "pitch_earned_runs", "pitch_win",
]  # fmt: skip


def _team(r) -> str:
    return f"{r['city']} {r['mascot']}" if r.get("city") else ""


def game_cards(conn, league_id: str, my_team_id, team_id=None) -> list[Card]:
    out = []
    for s in GAME_STATS:
        rows = conn.execute(
            f"""SELECT pgs.player_id, pgs.team_id, g.id AS game_id, g.game_date,
                       g.innings_played, s.year, sr.name AS series, pgs.{s.column} AS v,
                       p.first_name, p.last_name, t.city, t.mascot, o.city AS opp_city
                FROM player_game_stats pgs
                JOIN games g ON g.id = pgs.game_id
                JOIN series sr ON sr.id = g.series_id
                JOIN league_seasons ls ON ls.season_id = g.season_id
                JOIN seasons s ON s.id = g.season_id
                JOIN players p ON p.id = pgs.player_id
                LEFT JOIN teams t ON t.id = pgs.team_id
                LEFT JOIN teams o ON o.id = pgs.opponent_team_id
                WHERE ls.league_id = %s AND pgs.{s.column} > 0
                  AND (%s::text IS NULL OR pgs.team_id = %s)
                ORDER BY pgs.{s.column} DESC, g.game_date LIMIT %s""",
            (league_id, team_id, team_id, TOP),
        ).fetchall()
        perfs = [
            {
                "value": r["v"],
                "shown": str(r["v"]),
                "order": r["game_date"],
                "player_id": r["player_id"],
                "name": f"{r['first_name']} {r['last_name']}",
                "team": "" if team_id else _team(r),
                "detail": f"{r['year']} {_round(r['series'])} vs {r['opp_city']}",
                "is_mine": not team_id and r["team_id"] == my_team_id,
            }
            for r in rows
        ]
        out.append(card(f"pgame-{s.key}", s.label, perfs))
    return out


def _round(name: str) -> str:
    return ROUND_OF_SERIES.get(name, name)


def _series_lines(conn, league_id: str, team_id=None) -> list[dict]:
    cols = ", ".join(f"SUM(COALESCE(pgs.{c}, 0)) AS {c}" for c in SERIES_COLS)
    rows = conn.execute(
        f"""SELECT pgs.player_id, pgs.team_id, g.series_id, sr.name AS series, s.year,
                   MIN(g.game_date) AS first_date, COUNT(*) AS games,
                   MAX(pgs.opponent_team_id) AS opp, {cols},
                   MAX(p.first_name) AS first_name, MAX(p.last_name) AS last_name,
                   MAX(t.city) AS city, MAX(t.mascot) AS mascot, MAX(o.city) AS opp_city
            FROM player_game_stats pgs
            JOIN games g ON g.id = pgs.game_id
            JOIN series sr ON sr.id = g.series_id
            JOIN league_seasons ls ON ls.season_id = g.season_id
            JOIN seasons s ON s.id = g.season_id
            JOIN players p ON p.id = pgs.player_id
            LEFT JOIN teams t ON t.id = pgs.team_id
            LEFT JOIN teams o ON o.id = pgs.opponent_team_id
            WHERE ls.league_id = %s AND (%s::text IS NULL OR pgs.team_id = %s)
            GROUP BY pgs.player_id, pgs.team_id, g.series_id, sr.name, s.year""",
        (league_id, team_id, team_id),
    ).fetchall()
    games = {
        r["series_id"]: r["n"]
        for r in conn.execute(
            """SELECT g.series_id, COUNT(*) AS n FROM games g
               JOIN league_seasons ls ON ls.season_id = g.season_id
               WHERE ls.league_id = %s AND g.series_id IS NOT NULL AND g.completed = 1
               GROUP BY g.series_id""",
            (league_id,),
        ).fetchall()
    }
    out = []
    for r in rows:
        d = dict(r)
        d["series_games"] = games.get(r["series_id"], r["games"])
        out.append(d)
    return out


def series_cards(
    conn, league_id: str, my_team_id, team_id=None
) -> dict[str, list[Card]]:
    lines = _series_lines(conn, league_id, team_id)

    def perf(ln, value, shown):
        return {
            "value": value,
            "shown": shown,
            "order": ln["first_date"],
            "player_id": ln["player_id"],
            "name": f"{ln['first_name']} {ln['last_name']}",
            "team": "" if team_id else _team(ln),
            "detail": f"{ln['year']} {_round(ln['series'])} vs {ln['opp_city']}"
            f" ({ln['series_games']} g)",
            "is_mine": not team_id and ln["team_id"] == my_team_id,
        }

    floor = (lambda v: None) if team_id else (lambda v: v)
    counts = []
    for s in GAME_STATS:
        col = s.column
        perfs = [perf(ln, ln[col], str(ln[col])) for ln in lines if ln[col] > 0]
        counts.append(
            card(f"series-{s.key}", s.label, perfs, floor=floor(SERIES_FLOORS[s.key]),
                 note="Best-of-5 and best-of-7 together")
        )  # fmt: skip
    wins = [
        perf(ln, ln["pitch_win"], str(ln["pitch_win"]))
        for ln in lines
        if ln["pitch_win"]
    ]
    counts.append(card("series-W", "Wins", wins))

    rates = []
    for key, label in seasons.BAT_RATES:
        perfs = []
        for ln in lines:
            if seasons.pa(ln) < 3.1 * ln["series_games"] or not ln["bat_ab"]:
                continue
            v = seasons.rate(key, ln)
            p = perf(ln, round(v, 4), seasons.show_rate(key, v))
            p["order"] = f"{-seasons.pa(ln):06d}"
            perfs.append(p)
        c = card(f"series-{key}", label, perfs, size=10, listing=True,
                 note="3.1 PA a game of the series")  # fmt: skip
        rates.append(c)
    for key, label in seasons.PIT_RATES:
        perfs = []
        for ln in lines:
            if ln["pitch_outs"] < 3 * ln["series_games"]:
                continue
            v = seasons.rate(key, ln)
            p = perf(ln, round(v, 4), seasons.show_rate(key, v))
            p["order"] = f"{-ln['pitch_outs']:06d}"  # more innings first
            perfs.append(p)
        c = card(f"series-{key}", label, perfs, lower=True, size=10, listing=True,
                 note="1 inning a game of the series")  # fmt: skip
        rates.append(c)
    return {"counts": counts, "rates": rates}


def career_cards(conn, league_id: str, my_team_id, team_id=None) -> list[Card]:
    rows = conn.execute(
        """SELECT pss.player_id, pss.team_id, s.year, p.first_name, p.last_name,
                  t.city, t.mascot,
                  pss.bat_home_runs, pss.bat_hits, pss.bat_rbi, pss.bat_runs,
                  pss.bat_stolen_bases, pss.pitch_wins, pss.pitch_saves,
                  pss.pitch_strike_outs, pss.pitch_outs
           FROM player_season_stats pss
           JOIN league_seasons ls ON ls.season_id = pss.season_id
           JOIN seasons s ON s.id = pss.season_id
           JOIN players p ON p.id = pss.player_id
           LEFT JOIN teams t ON t.id = pss.team_id
           WHERE ls.league_id = %s AND pss.is_postseason
             AND (%s::text IS NULL OR pss.team_id = %s)""",
        (league_id, team_id, team_id),
    ).fetchall()
    tot: dict[str, dict] = {}
    for r in rows:
        t = tot.setdefault(r["player_id"], {"first": r["year"], "last": r["year"],
                                            "teams": [], "team_ids": [], **dict(r)})  # fmt: skip
        if t is not None and t.get("_seen"):
            for c in ("bat_home_runs", "bat_hits", "bat_rbi", "bat_runs",
                      "bat_stolen_bases", "pitch_wins", "pitch_saves",
                      "pitch_strike_outs", "pitch_outs"):  # fmt: skip
                t[c] += r[c] or 0
        t["_seen"] = True
        t["first"], t["last"] = min(t["first"], r["year"]), max(t["last"], r["year"])
        if r["team_id"] not in t["team_ids"]:
            t["team_ids"].append(r["team_id"])
            t["teams"].append(_team(r))
    lines = list(tot.values())
    titles = _player_titles(conn, league_id, team_id)

    def perf(ln, value, shown):
        span = (
            f"{ln['first']}–{ln['last']}"
            if ln["first"] != ln["last"]
            else str(ln["first"])
        )
        return {
            "value": value,
            "shown": shown,
            "order": f"{ln['last']:05d}",
            "player_id": ln["player_id"],
            "name": f"{ln['first_name']} {ln['last_name']}",
            "team": "" if team_id else ln["teams"][-1],
            "detail": span,
            "is_mine": not team_id and my_team_id in ln["team_ids"],
        }

    defs = [
        ("HR", "bat_home_runs", "Home runs"), ("H", "bat_hits", "Hits"),
        ("RBI", "bat_rbi", "RBI"), ("R", "bat_runs", "Runs"),
        ("SB", "bat_stolen_bases", "Stolen bases"), ("W", "pitch_wins", "Wins"),
        ("SV", "pitch_saves", "Saves"), ("K", "pitch_strike_outs", "Strikeouts (pitching)"),
        ("IP", "pitch_outs", "Innings pitched"),
    ]  # fmt: skip
    cards = [
        card(f"pcareer-{k}", label,
             [perf(ln, ln[c] or 0, seasons.show_count(k, ln[c] or 0)) for ln in lines if ln[c]])
        for k, c, label in defs
    ]  # fmt: skip
    cards.insert(0, card("pcareer-titles", "Titles won", [
        perf(ln, titles[ln["player_id"]], str(titles[ln["player_id"]]))
        for ln in lines if titles.get(ln["player_id"])
    ], note="Championships, playing in that postseason"))  # fmt: skip
    return cards


def champions(conn, league_id: str) -> dict[str, str]:
    """{season_id: champion team_id} for every season with a Finals winner,
    backstory included."""
    rows = conn.execute(
        """SELECT sr.season_id, g.winner_id, COUNT(*) AS w FROM series sr
           JOIN league_seasons ls ON ls.season_id = sr.season_id
           JOIN games g ON g.series_id = sr.id AND g.completed = 1
           WHERE ls.league_id = %s AND sr.name = 'Finals'
           GROUP BY sr.season_id, g.winner_id""",
        (league_id,),
    ).fetchall()
    out: dict[str, str] = {}
    for r in rows:
        if r["w"] >= 4:
            out[r["season_id"]] = r["winner_id"]
    return out


def _player_titles(conn, league_id: str, team_id=None) -> dict[str, int]:
    champs = champions(conn, league_id)
    if not champs:
        return {}
    rows = conn.execute(
        """SELECT DISTINCT player_id, season_id, team_id FROM player_season_stats
           WHERE is_postseason AND season_id = ANY(%s)""",
        (list(champs),),
    ).fetchall()
    out: dict[str, int] = defaultdict(int)
    for r in rows:
        if champs.get(r["season_id"]) == r["team_id"] and (
            not team_id or r["team_id"] == team_id
        ):
            out[r["player_id"]] += 1
    return out


def team_title_cards(conn, league_id: str, my_team_id, team_id=None) -> list[Card]:
    champs = champions(conn, league_id)
    years = {
        r["id"]: r["year"]
        for r in conn.execute(
            "SELECT id, year FROM seasons WHERE id = ANY(%s)", (list(champs),)
        ).fetchall()
    }
    by_team: dict[str, list[int]] = defaultdict(list)
    for sid, tid in champs.items():
        by_team[tid].append(years[sid])
    names = {
        r["id"]: f"{r['city']} {r['mascot']}"
        for r in conn.execute(
            "SELECT id, city, mascot FROM teams WHERE id = ANY(%s)", (list(by_team),)
        ).fetchall()
    }
    perfs = [
        {
            "value": len(ys),
            "shown": str(len(ys)),
            "order": f"{min(ys):05d}",
            "team_id": tid,
            "name": names.get(tid, "?"),
            "team": "",
            "detail": ", ".join(str(y) for y in sorted(ys)[-4:])
            + (" …" if len(ys) > 4 else ""),
            "is_mine": tid == my_team_id,
        }
        for tid, ys in by_team.items()
        if not team_id or tid == team_id
    ]
    return [card("titles", "Most titles", perfs, note="Backstory titles count")]
