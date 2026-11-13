# src/api/services/records/watch.py
"""
Record watch: who's chasing a record right now, for the top of the Records
tab while a season is on.

  pace      players on pace (after 40 team games) to pass a season record
  streak    streaks still going within 5 games of the league record
  career    active players within 10% of a career record
"""

from __future__ import annotations

from src.api.services.records import defs, feats, seasons
from src.api.services.records.news import marks

MIN_GAMES = 40
STREAK_GAP = 5
CAREER_SHARE = 0.9
SHOW = 8


def watch(conn, league_id: str, season_id: str | None, my_team_id) -> list[dict]:
    if not season_id:
        return []
    info = seasons.season_info(conn, league_id)
    s = info.get(season_id)
    if not s or s["finished"]:
        return []
    out: list[dict] = []
    length = (
        conn.execute(
            """SELECT MAX(n) AS n FROM (
               SELECT COUNT(*) AS n FROM games g
               CROSS JOIN LATERAL (VALUES (g.home_team_id), (g.away_team_id)) t(team_id)
               WHERE g.season_id = %s AND g.series_id IS NULL GROUP BY t.team_id) x""",
            (season_id,),
        ).fetchone()["n"]
        or 0
    )
    played = s["team_games"]
    rows = seasons.load(conn, league_id)
    lines = seasons.season_lines(rows, split=False)
    counts = seasons.BAT_COUNTS + seasons.PIT_COUNTS
    if played >= MIN_GAMES and length:
        for key, col, label in counts:
            record = max(
                (ln[col] for ln in lines if ln["season_id"] != season_id), default=0
            )
            if not record:
                continue
            for ln in lines:
                if ln["season_id"] != season_id or not ln[col]:
                    continue
                pace = ln[col] * length / played
                if pace > record:
                    out.append(_row(ln, "pace", label, seasons.show_count(key, ln[col]),
                                    f"on pace for {seasons.show_count(key, round(pace))}",
                                    seasons.show_count(key, record), my_team_id,
                                    pace / record))  # fmt: skip
    best = marks(conn, league_id, "streak")
    for f in feats.load(conn, league_id, "streak"):
        if not f["active"]:
            continue
        rec = best.get(f["stat"], (0, ""))[0]
        if rec and f["key"] != best[f["stat"]][1] and f["value"] >= rec - STREAK_GAP:
            stat = defs.STREAK_BY_KEY[f["stat"]]
            name = (
                f"{f['first_name']} {f['last_name']}" if f["player_id"]
                else f"{f['city']} {f['mascot']}"
            )  # fmt: skip
            out.append({
                "kind": "streak", "label": stat.label, "player_id": f["player_id"],
                "name": name, "now": f"{f['value']} games",
                "how": "still going", "record": str(rec),
                "is_mine": f["team_id"] == my_team_id, "score": f["value"] / rec + 1,
            })  # fmt: skip
    careers = seasons.career_lines(rows, season_id)
    for key, col, label in counts:
        ordered = sorted(careers, key=lambda c: -c[col])
        if len(ordered) < 2 or not ordered[0][col]:
            continue
        top = ordered[0]
        for c in ordered[1:6]:
            if c["active"] and c[col] >= CAREER_SHARE * top[col]:
                gap = top[col] - c[col]
                out.append(_row(c, "career", f"Career {label.lower()}",
                                seasons.show_count(key, c[col]),
                                f"{seasons.show_count(key, gap + 1)} to pass {top['name']}",
                                seasons.show_count(key, top[col]), my_team_id,
                                c[col] / top[col]))  # fmt: skip
    out.sort(key=lambda r: -r["score"])
    return out[:SHOW]


def _row(ln, kind, label, now, how, record, my_team_id, score) -> dict:
    return {
        "kind": kind,
        "label": label,
        "player_id": ln["player_id"],
        "name": ln["name"],
        "now": now,
        "how": how,
        "record": record,
        "is_mine": bool(my_team_id) and my_team_id in ln["team_ids"],
        "score": score,
    }
