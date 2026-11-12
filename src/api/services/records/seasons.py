# src/api/services/records/seasons.py
"""
Season and career records from player_season_stats (regular season only).

Backstory seasons have real season lines, so a new league's book starts
full. A season still being played counts for the counting stats (marked
active) but not the rate stats, which need a finished season so a hot April
never sits in the book. Rate stats use the Leaders tab's MLB qualifiers
(src/stats/qualifiers.py) against that season's team games; careers need
3,000 PA or 1,000 IP (2,000 and 600 with one club).

With ``team_id`` (franchise records) only his seasons with that club count,
and a season split between clubs is two lines; for the league, a split
season is added up into one.
"""

from __future__ import annotations

from src.api.services.records.core import Card, card, rate2, rate3
from src.stats import formulas, glossary, qualifiers as q

# (key, column, label)
BAT_COUNTS = [
    ("HR", "bat_home_runs", "Home runs"),
    ("H", "bat_hits", "Hits"),
    ("2B", "bat_doubles", "Doubles"),
    ("3B", "bat_triples", "Triples"),
    ("R", "bat_runs", "Runs"),
    ("RBI", "bat_rbi", "RBI"),
    ("SB", "bat_stolen_bases", "Stolen bases"),
    ("BB", "bat_walks", "Walks"),
    ("K", "bat_strike_outs", "Strikeouts (batting)"),
]
PIT_COUNTS = [
    ("W", "pitch_wins", "Wins"),
    ("SV", "pitch_saves", "Saves"),
    ("K", "pitch_strike_outs", "Strikeouts (pitching)"),
    ("IP", "pitch_outs", "Innings pitched"),
]
BAT_RATES = [
    ("AVG", "Batting average"),
    ("OBP", "On-base percentage"),
    ("SLG", "Slugging percentage"),
    ("OPS", "OPS"),
]
PIT_RATES = [("ERA", "ERA"), ("WHIP", "WHIP")]

STAT_COLS = sorted(
    {c for _, c, _ in BAT_COUNTS + PIT_COUNTS}
    | {
        "bat_ab", "bat_walks", "bat_hbp", "bat_sac_flys", "bat_hits",
        "bat_doubles", "bat_triples", "bat_home_runs", "bat_games_played",
        "pitch_outs", "pitch_earned_runs", "pitch_hits", "pitch_walks",
        "pitch_games_played",
    }
)  # fmt: skip

CAREER_PA, CAREER_OUTS = 3000, 3000
CLUB_CAREER_PA, CLUB_CAREER_OUTS = 2000, 1800


def load(conn, league_id: str, team_id: str | None = None) -> list[dict]:
    """Every regular-season line in the league, oldest first: one per
    player, season and club."""
    cols = ", ".join(f"pss.{c}" for c in STAT_COLS)
    rows = conn.execute(
        f"""SELECT pss.player_id, pss.season_id, pss.team_id, s.year,
                   p.first_name, p.last_name, t.city, t.mascot, {cols}
            FROM player_season_stats pss
            JOIN league_seasons ls ON ls.season_id = pss.season_id
            JOIN seasons s ON s.id = pss.season_id
            JOIN players p ON p.id = pss.player_id
            LEFT JOIN teams t ON t.id = pss.team_id
            WHERE ls.league_id = %s AND NOT pss.is_postseason
              AND (%s::text IS NULL OR pss.team_id = %s)
            ORDER BY s.year, pss.player_id""",
        (league_id, team_id, team_id),
    ).fetchall()
    return [dict(r) for r in rows]


def season_info(conn, league_id: str) -> dict[str, dict]:
    """{season_id: {"year", "team_games", "finished"}} for every season with
    regular-season games: team_games is the most any club has played."""
    rows = conn.execute(
        """SELECT g.season_id, s.year,
                  COUNT(*) FILTER (WHERE g.completed = 1) AS played,
                  COUNT(*) FILTER (WHERE g.completed IS DISTINCT FROM 1) AS left_to_play
           FROM games g
           JOIN league_seasons ls ON ls.season_id = g.season_id
           JOIN seasons s ON s.id = g.season_id
           WHERE ls.league_id = %s AND g.series_id IS NULL
           GROUP BY g.season_id, s.year""",
        (league_id,),
    ).fetchall()
    per_team = conn.execute(
        """SELECT g.season_id, MAX(n) AS team_games FROM (
               SELECT g.season_id, tgs.team_id, COUNT(*) AS n
               FROM games g
               JOIN league_seasons ls ON ls.season_id = g.season_id
               JOIN team_game_stats tgs ON tgs.game_id = g.id
               WHERE ls.league_id = %s AND g.series_id IS NULL AND g.completed = 1
               GROUP BY g.season_id, tgs.team_id) g
           GROUP BY g.season_id""",
        (league_id,),
    ).fetchall()
    games = {r["season_id"]: int(r["team_games"]) for r in per_team}
    return {
        r["season_id"]: {
            "year": r["year"],
            "team_games": games.get(r["season_id"], 0),
            "finished": r["played"] > 0 and r["left_to_play"] == 0,
        }
        for r in rows
    }


# ── Lines ─────────────────────────────────────────────────────────────────────


def _team(r: dict) -> str:
    return f"{r['city']} {r['mascot']}" if r.get("city") else ""


def season_lines(rows: list[dict], split: bool) -> list[dict]:
    """One line per player-season; with ``split`` one per club as well."""
    out: dict[tuple, dict] = {}
    for r in rows:
        key = (r["player_id"], r["season_id"]) + ((r["team_id"],) if split else ())
        line = out.get(key)
        if line is None:
            line = out[key] = {
                "player_id": r["player_id"],
                "season_id": r["season_id"],
                "year": r["year"],
                "name": f"{r['first_name']} {r['last_name']}",
                "team_ids": [],
                "teams": [],
                **{c: 0 for c in STAT_COLS},
            }
        if r["team_id"] not in line["team_ids"]:
            line["team_ids"].append(r["team_id"])
            line["teams"].append(_team(r))
        for c in STAT_COLS:
            line[c] += int(r[c] or 0)
    return list(out.values())


def career_lines(rows: list[dict], current_season: str | None) -> list[dict]:
    out: dict[str, dict] = {}
    for r in rows:
        line = out.get(r["player_id"])
        if line is None:
            line = out[r["player_id"]] = {
                "player_id": r["player_id"],
                "name": f"{r['first_name']} {r['last_name']}",
                "first": r["year"],
                "last": r["year"],
                "team_ids": [],
                "teams": [],
                "active": False,
                **{c: 0 for c in STAT_COLS},
            }
        line["last"] = max(line["last"], r["year"])
        line["first"] = min(line["first"], r["year"])
        if r["team_id"] not in line["team_ids"]:
            line["team_ids"].append(r["team_id"])
            line["teams"].append(_team(r))
        if current_season and r["season_id"] == current_season:
            line["active"] = True
        for c in STAT_COLS:
            line[c] += int(r[c] or 0)
    return list(out.values())


# ── Values ────────────────────────────────────────────────────────────────────


def pa(line: dict) -> int:
    return q.plate_appearances(line)


def rate(key: str, line: dict) -> float:
    if key == "AVG":
        return formulas.batting_average(line["bat_hits"], line["bat_ab"])
    if key in ("OBP", "SLG", "OPS"):
        obp = formulas.on_base_pct(
            line["bat_hits"], line["bat_walks"], line["bat_hbp"],
            line["bat_ab"], line["bat_sac_flys"],
        )  # fmt: skip
        tb = formulas.total_bases(
            line["bat_hits"], line["bat_doubles"], line["bat_triples"],
            line["bat_home_runs"],
        )  # fmt: skip
        slg = formulas.slugging_pct(tb, line["bat_ab"])
        return {"OBP": obp, "SLG": slg, "OPS": obp + slg}[key]
    if key == "ERA":
        return formulas.era(line["pitch_earned_runs"], line["pitch_outs"])
    if key == "WHIP":
        return formulas.whip(
            line["pitch_hits"], line["pitch_walks"], line["pitch_outs"]
        )
    raise KeyError(key)


def show_count(key: str, v: int) -> str:
    return formulas.ip_str(v) if key == "IP" else str(v)


def show_rate(key: str, v: float) -> str:
    return rate2(v) if key in ("ERA", "WHIP") else rate3(v)


# ── Cards ─────────────────────────────────────────────────────────────────────


def _perf(
    line: dict, value, shown: str, my_team_id, order, detail: str, club=None
) -> dict:
    """A line as a performance. With ``club`` (franchise records) every line
    is that club's, so there's no team to show or to pick out."""
    teams = [t for t in line["teams"] if t]
    if club:
        teams, my_team_id = [], None
    return {
        "value": value,
        "shown": shown,
        "order": order,
        "player_id": line["player_id"],
        "name": line["name"],
        "team": teams[0] if len(teams) == 1 else f"{len(teams)} teams" if teams else "",
        "detail": detail,
        "active": line.get("active", False),
        "is_mine": bool(my_team_id) and my_team_id in line["team_ids"],
    }


def season_cards(
    rows: list[dict], info: dict[str, dict], my_team_id, team_id=None
) -> dict[str, list[Card]]:
    """{"batting": [...], "pitching": [...]} season record cards."""
    lines = season_lines(rows, split=bool(team_id))
    for ln in lines:
        s = info.get(ln["season_id"])
        ln["active"] = bool(s) and not s["finished"]

    def perf(ln, value, shown):
        # Ties go to the earlier season; within one, the order is the name.
        return _perf(
            ln, value, shown, my_team_id, f"{ln['year']:05d}", str(ln["year"]), team_id
        )

    def counts(defs):
        return [
            card(
                f"season-{key}-{col}",
                label,
                [
                    perf(ln, ln[col], show_count(key, ln[col]))
                    for ln in lines
                    if ln[col] > 0
                ],
                tip=_tip(key, col),
            )
            for key, col, label in defs
        ]

    def rates(defs, pitching: bool):
        out = []
        for key, label in defs:
            perfs = []
            for ln in lines:
                s = info.get(ln["season_id"])
                if not s or not s["finished"] or not s["team_games"]:
                    continue
                if pitching:
                    if ln["pitch_outs"] < q.min_outs(s["team_games"]):
                        continue
                elif pa(ln) < q.min_pa(s["team_games"]):
                    continue
                v = rate(key, ln)
                perfs.append(perf(ln, round(v, 4), show_rate(key, v)))
            note = (
                "1 inning a team game"
                if pitching
                else "3.1 plate appearances a team game"
            )
            out.append(
                card(f"season-{key}", label, perfs, lower=pitching,
                     tip=_tip(key, "pitch" if pitching else "bat"), note=note)
            )  # fmt: skip
        return out

    return {
        "batting": counts(BAT_COUNTS) + rates(BAT_RATES, pitching=False),
        "pitching": counts(PIT_COUNTS) + rates(PIT_RATES, pitching=True),
    }


def career_cards(
    rows: list[dict], current_season: str | None, my_team_id, team_id=None
) -> dict[str, list[Card]]:
    lines = career_lines(rows, current_season)
    need_pa = CLUB_CAREER_PA if team_id else CAREER_PA
    need_outs = CLUB_CAREER_OUTS if team_id else CAREER_OUTS

    def perf(ln, value, shown):
        span = (
            f"{ln['first']}–{ln['last']}"
            if ln["first"] != ln["last"]
            else str(ln["first"])
        )
        p = _perf(ln, value, shown, my_team_id, f"{ln['last']:05d}", span, team_id)
        p["live_label"] = "active"
        if not team_id and len(ln["teams"]) > 1:
            p["team"] = ln["teams"][-1]
        return p

    def counts(defs):
        return [
            card(
                f"career-{key}-{col}",
                label,
                [
                    perf(ln, ln[col], show_count(key, ln[col]))
                    for ln in lines
                    if ln[col] > 0
                ],
                tip=_tip(key, col),
            )
            for key, col, label in defs
        ]

    def rates(defs, pitching: bool):
        out = []
        for key, label in defs:
            perfs = [
                perf(ln, round(rate(key, ln), 4), show_rate(key, rate(key, ln)))
                for ln in lines
                if (ln["pitch_outs"] >= need_outs if pitching else pa(ln) >= need_pa)
            ]
            note = (
                f"{need_outs // 3:,} innings"
                if pitching
                else f"{need_pa:,} plate appearances"
            )
            out.append(
                card(f"career-{key}", label, perfs, lower=pitching,
                     tip=_tip(key, "pitch" if pitching else "bat"), note=note)
            )  # fmt: skip
        return out

    return {
        "batting": counts(BAT_COUNTS) + rates(BAT_RATES, pitching=False),
        "pitching": counts(PIT_COUNTS) + rates(PIT_RATES, pitching=True),
    }


def _tip(key: str, col: str) -> str:
    book = glossary.PIT if col.startswith("pitch") else glossary.BAT
    return book.get(key, "")
