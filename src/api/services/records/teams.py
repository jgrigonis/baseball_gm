# src/api/services/records/teams.py
"""
Team records: a club's season (wins, runs, run differential, home runs,
steals) and its single games (runs, margin, innings, a big inning).

They read the games table, which backstory seasons fill with real final
and line scores, so these start full in any league with a backstory.
Regular season only; the postseason has its own section.
"""

from __future__ import annotations

from src.api.services.records.core import Card, card

TOP = 60  # games pulled per single-game record, plenty for ties and a top 5

# Backstory games are scored half-inning by half-inning from team strength,
# which gets game totals right but gives far too many huge innings and very
# long games, so those two records only count games really played, and
# start from a league mark.
PLAYED_ONLY = "Games played since the league started"
INNING_FLOOR = 7
LONGEST_FLOOR = 12


def season_lines(conn, league_id: str) -> list[dict]:
    rows = conn.execute(
        """SELECT g.season_id, s.year, tgs.team_id, t.city, t.mascot,
                  SUM(tgs.win) AS w, SUM(tgs.loss) AS l, SUM(tgs.runs) AS rs,
                  SUM(o.runs) AS ra
           FROM games g
           JOIN league_seasons ls ON ls.season_id = g.season_id
           JOIN seasons s ON s.id = g.season_id
           JOIN team_game_stats tgs ON tgs.game_id = g.id
           JOIN team_game_stats o ON o.game_id = g.id AND o.team_id <> tgs.team_id
           JOIN teams t ON t.id = tgs.team_id
           WHERE ls.league_id = %s AND g.series_id IS NULL AND g.completed = 1
           GROUP BY g.season_id, s.year, tgs.team_id, t.city, t.mascot""",
        (league_id,),
    ).fetchall()
    bats = conn.execute(
        """SELECT pss.season_id, pss.team_id, SUM(pss.bat_home_runs) AS hr,
                  SUM(pss.bat_stolen_bases) AS sb
           FROM player_season_stats pss
           JOIN league_seasons ls ON ls.season_id = pss.season_id
           WHERE ls.league_id = %s AND NOT pss.is_postseason
           GROUP BY pss.season_id, pss.team_id""",
        (league_id,),
    ).fetchall()
    extra = {(b["season_id"], b["team_id"]): b for b in bats}
    out = []
    for r in rows:
        b = extra.get((r["season_id"], r["team_id"])) or {}
        out.append(
            {
                **dict(r),
                "hr": int(b.get("hr") or 0),
                "sb": int(b.get("sb") or 0),
                "rs": int(r["rs"] or 0),
                "ra": int(r["ra"] or 0),
                "w": int(r["w"] or 0),
                "l": int(r["l"] or 0),
            }
        )
    return out


def season_cards(
    lines: list[dict], info: dict[str, dict], my_team_id, team_id=None
) -> list[Card]:
    if team_id:
        lines = [ln for ln in lines if ln["team_id"] == team_id]
    done = [ln for ln in lines if info.get(ln["season_id"], {}).get("finished")]

    def perf(ln, value, shown):
        s = info.get(ln["season_id"]) or {}
        return {
            "value": value,
            "shown": shown,
            "order": f"{ln['year']:05d}",
            "team_id": ln["team_id"],
            "name": f"{ln['city']} {ln['mascot']}",
            "team": f"{ln['w']}-{ln['l']}",
            "detail": str(ln["year"]),
            "active": not s.get("finished", True),
            "is_mine": not team_id and ln["team_id"] == my_team_id,
        }

    def diff(ln):
        d = ln["rs"] - ln["ra"]
        return f"{d:+d}"

    return [
        card("team-wins", "Most wins", [perf(ln, ln["w"], str(ln["w"])) for ln in lines]),
        card("team-fewest-wins", "Fewest wins", [perf(ln, ln["w"], str(ln["w"])) for ln in done],
             lower=True, note="Finished seasons"),
        card("team-runs", "Most runs scored", [perf(ln, ln["rs"], str(ln["rs"])) for ln in lines]),
        card("team-fewest-ra", "Fewest runs allowed", [perf(ln, ln["ra"], str(ln["ra"])) for ln in done],
             lower=True, note="Finished seasons"),
        card("team-best-diff", "Best run differential",
             [perf(ln, ln["rs"] - ln["ra"], diff(ln)) for ln in lines]),
        card("team-worst-diff", "Worst run differential",
             [perf(ln, ln["rs"] - ln["ra"], diff(ln)) for ln in done], lower=True,
             note="Finished seasons"),
        card("team-hr", "Most home runs", [perf(ln, ln["hr"], str(ln["hr"])) for ln in lines]),
        card("team-sb", "Most stolen bases", [perf(ln, ln["sb"], str(ln["sb"])) for ln in lines]),
    ]  # fmt: skip


# ── Single games ──────────────────────────────────────────────────────────────


def game_cards(
    conn, league_id: str, my_team_id, team_id=None, playoffs=False
) -> list[Card]:
    """Single-game team records. ``playoffs`` for the postseason's."""
    series = "IS NOT NULL" if playoffs else "IS NULL"
    frm = """
        FROM games g
        JOIN league_seasons ls ON ls.season_id = g.season_id
        JOIN seasons s ON s.id = g.season_id
        CROSS JOIN LATERAL (VALUES
            (g.home_team_id, g.away_team_id, g.home_score, g.away_score, 'home'),
            (g.away_team_id, g.home_team_id, g.away_score, g.home_score, 'away')
        ) side(team_id, opp_id, runs, opp_runs, side)
        JOIN teams t ON t.id = side.team_id
        JOIN teams o ON o.id = side.opp_id"""
    where = f"""
        WHERE ls.league_id = %(league)s AND g.series_id {series} AND g.completed = 1
          AND (%(team)s::text IS NULL OR side.team_id = %(team)s)"""
    base = frm + where
    cols = """g.id AS game_id, g.game_date, s.year, side.team_id, t.city, t.mascot,
              o.city AS opp_city, side.runs, side.opp_runs, g.innings_played"""
    args = {"league": league_id, "team": team_id, "top": TOP}

    runs = conn.execute(
        f"SELECT {cols} {base} ORDER BY side.runs DESC, g.game_date LIMIT %(top)s", args
    ).fetchall()
    margin = conn.execute(
        f"""SELECT {cols} {base} AND side.runs > side.opp_runs
            ORDER BY side.runs - side.opp_runs DESC, g.game_date LIMIT %(top)s""",
        args,
    ).fetchall()
    # A game is one record for its length, whichever side; with a club, its own.
    longest = conn.execute(
        f"""SELECT {cols} {base} AND (side.side = 'home' OR %(team)s::text IS NOT NULL)
              AND NOT s.is_backstory
            ORDER BY g.innings_played DESC NULLS LAST, g.game_date LIMIT %(top)s""",
        args,
    ).fetchall()
    inning = conn.execute(
        f"""SELECT {cols}, inn.n AS inning, inn.r AS inning_runs {frm}
            CROSS JOIN LATERAL (
                SELECT ord AS n, CASE WHEN x ~ '^[0-9]+$' THEN x::int ELSE 0 END AS r
                FROM jsonb_array_elements_text(g.line_score -> side.side)
                     WITH ORDINALITY AS e(x, ord)
            ) inn
            {where} AND NOT s.is_backstory
            ORDER BY inn.r DESC, g.game_date LIMIT %(top)s""",
        args,
    ).fetchall()

    def floor(v):
        # A club's own book starts empty; the league's starts at a mark.
        return None if team_id else v

    def perf(r, value, shown, detail):
        return {
            "value": value,
            "shown": shown,
            "order": r["game_date"],
            "team_id": r["team_id"],
            "game_id": r["game_id"],
            "name": f"{r['city']} {r['mascot']}",
            "team": detail,
            "detail": str(r["year"]),
            "is_mine": not team_id and r["team_id"] == my_team_id,
        }

    def score(r):
        return f"{r['runs']}-{r['opp_runs']} vs {r['opp_city']}"

    def inn(r):
        return f", {r['innings_played']} inn" if (r["innings_played"] or 9) > 9 else ""

    long_games = [
        perf(r, r["innings_played"] or 9, f"{r['innings_played']} inn", score(r))
        for r in longest
        if (r["innings_played"] or 9) > 9
    ]
    big_innings = [
        perf(r, r["inning_runs"], str(r["inning_runs"]),
             f"{_ordinal(r['inning'])} inning vs {r['opp_city']}")
        for r in inning
        if r["inning_runs"]
    ]  # fmt: skip
    return [
        card("tgame-runs", "Most runs in a game",
             [perf(r, r["runs"], str(r["runs"]), score(r) + inn(r)) for r in runs]),
        card("tgame-margin", "Biggest win",
             [perf(r, r["runs"] - r["opp_runs"], f"+{r['runs'] - r['opp_runs']}", score(r))
              for r in margin]),
        card("tgame-innings", "Longest game", long_games, floor=floor(LONGEST_FLOOR),
             floor_shown=f"{LONGEST_FLOOR} inn", note=PLAYED_ONLY),
        card("tgame-inning", "Most runs in an inning", big_innings,
             floor=floor(INNING_FLOOR), note=PLAYED_ONLY),
    ]  # fmt: skip


def _ordinal(n: int) -> str:
    n = int(n)
    suffix = (
        "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    )
    return f"{n}{suffix}"
