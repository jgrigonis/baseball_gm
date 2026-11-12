# src/api/services/records/news.py
"""
News when a record falls: a single game or a streak (play.py tells us as
it reads the games), a season or career total passing the record, and at
the end of the regular season the rate-stat records.

Every story has a key, so it's written once. A league needs a few seasons
of history (backstory counts) before season and career totals make news,
or a new league's first leaders would all be "records".
"""

from __future__ import annotations

from src.api.services.news.names import Names
from src.api.services.records import defs, seasons
from src.db.repositories.news_repo import NewsRepository

MIN_SEASONS = 3  # seasons of history before season and career records are news


def has_backstory(conn, league_id: str) -> bool:
    row = conn.execute(
        """SELECT 1 FROM league_seasons ls JOIN seasons s ON s.id = ls.season_id
           WHERE ls.league_id = %s AND s.is_backstory LIMIT 1""",
        (league_id,),
    ).fetchone()
    return row is not None


def marks(conn, league_id: str, kind: str) -> dict[str, tuple[int, str]]:
    """The league record for each stat as (value, key of the feat holding
    it). Without a backstory the league mark (the floor) counts."""
    out: dict[str, tuple[int, str]] = {}
    for r in conn.execute(
        """SELECT DISTINCT ON (stat) stat, value, key FROM record_feats
           WHERE league_id = %s AND kind = %s
           ORDER BY stat, value DESC, on_date""",
        (league_id, kind),
    ).fetchall():
        out[r["stat"]] = (r["value"], r["key"])
    if not has_backstory(conn, league_id):
        stats = defs.GAME_STATS if kind == "game" else defs.STREAKS
        for s in stats:
            if s.key not in out or out[s.key][0] < s.floor:
                out[s.key] = (s.floor, "floor")
    return out


def _season_word(stat: str) -> str:
    return {"twin": "winning streak", "tloss": "losing streak"}.get(stat, "")


def broken(conn, league_id: str, season_id: str, events: list[tuple]) -> None:
    """Stories for single games and streaks that set a league record."""
    if not events:
        return
    names = Names(conn, league_id)
    names.load_players(f["player_id"] for _, _, f, _ in events if f["player_id"])
    repo = NewsRepository(conn)
    for kind, stat, f, before in events:
        pid, team = f["player_id"], f["team_id"]
        if kind == "game":
            s = defs.GAME_BY_KEY[stat]
            label = s.label.lower().replace(" (batting)", "").replace(" (pitching)", "")
            tie = f["value"] == before
            who = names.player(pid)
            headline = (
                f"{who} ties the league record with {f['value']} {label}"
                if tie
                else f"{who} sets a league record with {f['value']} {label}"
            )
            body = (
                f"{f['value']} {label} in one game against the "
                f"{names.team(f['opp_team_id'])}. "
                + (
                    f"The old mark was {before}."
                    if not tie
                    else "Only the best games in league history get there."
                )
            )
            pids = [pid]
        else:
            s = defs.STREAK_BY_KEY[stat]
            if s.team:
                who = names.full_team(team)
                headline = f"The {who} set a league record: {f['value']} straight " + (
                    "wins" if stat == "twin" else "losses"
                )
                pids = []
            else:
                who = names.player(pid)
                headline = (
                    f"{who}'s {s.label.lower()} reaches a record {f['value']} games"
                )
                pids = [pid]
            body = f"The old league record was {before}." + (
                " It's still going." if f["active"] else ""
            )
        repo.add(
            league_id, season_id, f["on_date"], "record", f"rec:{f['key']}",
            headline, body, weight=3, team_ids=[team] if team else [],
            player_ids=pids, gm_ids=names.gm_ids(team),
        )  # fmt: skip


# ── Season and career totals ──────────────────────────────────────────────────


def _history_seasons(info: dict, season_id: str) -> int:
    year = info.get(season_id, {}).get("year")
    return sum(1 for s in info.values() if year is not None and s["year"] < year)


def season_progress(
    conn, league_id: str, season_id: str, since: str, until: str
) -> None:
    """News for a season or career total that passed the record in the
    games after ``since`` through ``until``."""
    info = seasons.season_info(conn, league_id)
    if _history_seasons(info, season_id) < MIN_SEASONS:
        return
    counts = seasons.BAT_COUNTS + seasons.PIT_COUNTS
    window = {
        r["player_id"]: r
        for r in conn.execute(
            f"""SELECT pgs.player_id, MAX(g.game_date) AS last_date,
                       {", ".join(f"SUM(COALESCE(pgs.{_game_col(c)}, 0)) AS {c}" for _, c, _ in counts)}
                FROM player_game_stats pgs JOIN games g ON g.id = pgs.game_id
                WHERE g.season_id = %s AND g.completed = 1 AND g.series_id IS NULL
                  AND g.game_date > %s AND g.game_date <= %s
                GROUP BY pgs.player_id""",
            (season_id, since, until),
        ).fetchall()
    }
    if not window:
        return
    rows = seasons.load(conn, league_id)
    lines = seasons.season_lines(rows, split=False)
    careers = seasons.career_lines(rows, season_id)
    names = Names(conn, league_id)
    repo = NewsRepository(conn)
    for key, col, label in counts:
        prior = max(
            (ln[col] for ln in lines if ln["season_id"] != season_id), default=0
        )
        for ln in lines:
            w = window.get(ln["player_id"])
            if ln["season_id"] != season_id or not w or not prior:
                continue
            if ln[col] - w[col] <= prior < ln[col]:
                _total_story(repo, names, league_id, season_id, w, ln, key, col,
                             label, prior, "season")  # fmt: skip
        for ln in careers:
            w = window.get(ln["player_id"])
            if not w:
                continue
            others = max(
                (c[col] for c in careers if c["player_id"] != ln["player_id"]),
                default=0,
            )
            if others and ln[col] - w[col] <= others < ln[col]:
                _total_story(repo, names, league_id, season_id, w, ln, key, col,
                             label, others, "career")  # fmt: skip


def _game_col(col: str) -> str:
    # Season columns and game columns differ only for pitcher counts.
    return {
        "pitch_wins": "pitch_win",
        "pitch_saves": "pitch_save",
    }.get(col, col)


def _total_story(
    repo, names, league_id, season_id, w, ln, key, col, label, prior, scope
):
    pid = ln["player_id"]
    names.load_players([pid])
    shown = seasons.show_count(key, ln[col])
    old = seasons.show_count(key, prior)
    what = label.lower().replace(" (batting)", "").replace(" (pitching)", "")
    team = (ln["team_ids"] or [None])[-1]
    if scope == "season":
        headline = f"{names.player(pid)} sets the single-season record for {what}"
        body = f"He's at {shown}, past the old mark of {old}, with games still to play."
    else:
        headline = f"{names.player(pid)} becomes the league's career leader in {what}"
        body = f"{shown} and counting, past the old record of {old}."
    repo.add(
        league_id, season_id, w["last_date"], "record",
        f"rec:tot:{scope}:{key}:{col}:{pid}" + (f":{season_id}" if scope == "season" else ""),
        headline, body, weight=3, team_ids=[team] if team else [], player_ids=[pid],
        gm_ids=names.gm_ids(team),
    )  # fmt: skip


def season_over(conn, league_id: str, season_id: str, on: str | None) -> None:
    """At the end of the regular season: rate-stat records set this year."""
    info = seasons.season_info(conn, league_id)
    if _history_seasons(info, season_id) < MIN_SEASONS or not on:
        return
    rows = seasons.load(conn, league_id)
    cards = seasons.season_cards(rows, info, None)
    year = info[season_id]["year"]
    names = Names(conn, league_id)
    repo = NewsRepository(conn)
    for c in cards["batting"] + cards["pitching"]:
        if not c.note or not c.holders:  # rate cards carry their qualifier
            continue
        top = c.holders[0]
        if top["detail"] != str(year) or len(c.holders) > 1:
            continue
        before = next((r for r in c.rows if r["detail"] != str(year)), None)
        if not before:
            continue
        pid = top["player_id"]
        names.load_players([pid])
        repo.add(
            league_id, season_id, on, "record",
            f"rec:rate:{c.key}:{season_id}",
            f"{names.player(pid)} sets the league record: {top['shown']} {c.label}",
            f"The best qualified season ever. The old mark was {before['shown']}.",
            weight=3, player_ids=[pid],
        )  # fmt: skip
