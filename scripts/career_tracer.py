#!/usr/bin/env python3
# scripts/career_tracer.py
"""
Trace a player's full career: skills, ratings, caps, and season stats.

Usage:
    python career_trace.py "Frank Davenport"
    python career_trace.py "Frank Davenport" --dir team_files --db leagues/league.db
    python career_trace.py --id 6908bd40ff3b60c97d6b2c7822698c61

Output: a text report suitable for pasting into analysis.
"""

import argparse
import csv
import sys
from pathlib import Path

from src.db.connection import get_connection
from src.player.skill_map import SKILL_MAP, SKILL_ABBREVIATIONS

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SKILL_ABBRS = [
    ("durability", "DU"),
    ("contact", "CT"),
    ("power", "PO"),
    ("eye", "EY"),
    ("speed", "SP"),
    ("base_running", "BR"),
    ("bunting", "BU"),
    ("clutch", "CL"),
    ("catching", "CA"),
    ("infield", "IF"),
    ("outfield", "OF"),
    ("arm", "AR"),
    ("accuracy", "AC"),
    ("stamina", "ST"),
    ("recovery", "RE"),
    ("ground_balls", "GB"),
    ("strikes", "KK"),
]

CAP_SKILL_ORDER = [
    "durability",
    "clutch",
    "speed",
    "power",
    "eye",
    "contact",
    "base_running",
    "bunting",
    "catching",
    "infield",
    "outfield",
    "arm",
    "accuracy",
    "stamina",
    "recovery",
    "ground_balls",
    "strikes",
]

BATTING_COLS = [
    ("bat_ab", "AB"),
    ("bat_hits", "H"),
    ("bat_doubles", "2B"),
    ("bat_triples", "3B"),
    ("bat_home_runs", "HR"),
    ("bat_rbi", "RBI"),
    ("bat_runs", "R"),
    ("bat_walks", "BB"),
    ("bat_strike_outs", "SO"),
    ("bat_stolen_bases", "SB"),
    ("bat_hbp", "HBP"),
    ("bat_sac_flys", "SF"),
]

PITCHING_COLS = [
    ("pitch_game_started", "GS"),
    ("pitch_game_played", "G"),
    ("pitch_win", "W"),
    ("pitch_loss", "L"),
    ("pitch_save", "SV"),
    ("pitch_outs", "OUTS"),
    ("pitch_hits", "H"),
    ("pitch_earned_runs", "ER"),
    ("pitch_runs", "R"),
    ("pitch_walks", "BB"),
    ("pitch_strike_outs", "SO"),
    ("pitch_home_runs", "HR"),
    ("pitch_count", "PC"),
]

# ---------------------------------------------------------------------------
# Args
# ---------------------------------------------------------------------------


def parse_args():
    p = argparse.ArgumentParser(description="Full career trace for a player.")
    grp = p.add_mutually_exclusive_group(required=True)
    grp.add_argument("name", nargs="?", help="Player name (partial ok)")
    grp.add_argument("--id", dest="player_id", help="Player UUID")
    p.add_argument("--dir", default="team_files", help="Root dir of team CSVs")
    p.add_argument("--db", default="league.db", help="SQLite DB filename")
    return p.parse_args()


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------


def find_all_appearances(directory: Path, player_id: str) -> list[dict]:
    """Find every CSV row for this player ID, across all season subdirs."""
    appearances = []
    for csv_path in sorted(directory.glob("**/*.csv")):
        with open(csv_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("ID", "").strip() == player_id:
                    # Extract season year from path if possible
                    parts = csv_path.relative_to(directory).parts
                    season_year = None
                    for part in parts:
                        if part.isdigit() and len(part) == 4:
                            season_year = int(part)
                            break
                    team = csv_path.stem  # e.g. "madrid"
                    if team.lower() == "draft":
                        continue
                    if team.lower() == "retired":
                        continue
                    appearances.append(
                        {
                            **row,
                            "_season_year": season_year,
                            "_team": team,
                            "_csv_path": str(csv_path),
                        }
                    )
    # Sort by season year, unknown last
    appearances.sort(key=lambda r: r["_season_year"] or 9999)
    return appearances


def resolve_id_from_name(directory: Path, name_query: str) -> list[tuple[str, str]]:
    """Returns list of (player_id, canonical_name) for all matches."""
    query = name_query.lower()
    seen = {}
    for csv_path in sorted(directory.glob("**/*.csv")):
        with open(csv_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if query in row.get("Name", "").lower():
                    pid = row.get("ID", "").strip()
                    if pid:
                        seen[pid] = row["Name"]
    return list(seen.items())


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def get_talent_caps(db_file: str, player_id: str) -> dict | None:
    conn = get_connection(db_file)
    cur = conn.cursor()
    cur.execute("SELECT * FROM player_talent_caps WHERE player_id = ?", (player_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return dict(row)


def get_all_seasons(db_file: str) -> list[dict]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, year, name FROM seasons ORDER BY year")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_season_stats(db_file: str, player_id: str, season_id: int) -> dict:
    conn = get_connection()
    cur = conn.cursor()

    bat_sums = ", ".join(f"SUM(pgs.{col}) as {col}" for col, _ in BATTING_COLS)
    pit_sums = ", ".join(f"SUM(pgs.{col}) as {col}" for col, _ in PITCHING_COLS)

    cur.execute(
        f"""
        SELECT
            COUNT(DISTINCT pgs.game_id) as games_played,
            {bat_sums},
            {pit_sums}
        FROM player_game_stats pgs
        JOIN games g ON g.id = pgs.game_id
        WHERE pgs.player_id = ? AND g.season_id = ?
    """,
        (player_id, season_id),
    )

    row = cur.fetchone()
    conn.close()

    if not row or (row["games_played"] or 0) == 0:
        return {}

    batting = {label: (row[col] or 0) for col, label in BATTING_COLS}
    pitching = {label: (row[col] or 0) for col, label in PITCHING_COLS}

    ab = batting["AB"] or 1
    h = batting["H"]
    bb = batting["BB"]
    hbp = batting["HBP"]
    sf = batting["SF"]
    batting["AVG"] = f"{h/ab:.3f}" if batting["AB"] else ".000"
    denom = ab + bb + hbp + sf
    batting["OBP"] = f"{(h+bb+hbp)/denom:.3f}" if denom else ".000"

    outs = pitching["OUTS"] or 0
    ip_f = outs // 3
    ip_r = outs % 3
    pitching["IP"] = f"{ip_f}.{ip_r}"
    # r = pitching["R"]
    er = pitching["ER"]
    pitching["ERA"] = f"{er*27/outs:.2f}" if outs else "-.--"
    gs = pitching["GS"]
    pc = pitching["PC"]
    pitching["AVG PC"] = f"{pc/gs:.1f}" if gs else "—"

    return {
        "games": row["games_played"],
        "batting": batting,
        "pitching": pitching,
    }


def get_career_stats(db_file: str, player_id: str) -> dict:
    """Sum stats across all seasons."""
    conn = get_connection(db_file)
    cur = conn.cursor()

    bat_sums = ", ".join(f"SUM(pgs.{col}) as {col}" for col, _ in BATTING_COLS)
    pit_sums = ", ".join(f"SUM(pgs.{col}) as {col}" for col, _ in PITCHING_COLS)

    cur.execute(
        f"""
        SELECT
            COUNT(DISTINCT pgs.game_id) as games_played,
            {bat_sums},
            {pit_sums}
        FROM player_game_stats pgs
        WHERE pgs.player_id = ?
    """,
        (player_id,),
    )

    row = cur.fetchone()
    conn.close()

    if not row or (row["games_played"] or 0) == 0:
        return {}

    batting = {label: (row[col] or 0) for col, label in BATTING_COLS}
    pitching = {label: (row[col] or 0) for col, label in PITCHING_COLS}

    ab = batting["AB"] or 1
    h = batting["H"]
    bb = batting["BB"]
    hbp = batting["HBP"]
    sf = batting["SF"]
    batting["AVG"] = f"{h/ab:.3f}" if batting["AB"] else ".000"
    denom = ab + bb + hbp + sf
    batting["OBP"] = f"{(h+bb+hbp)/denom:.3f}" if denom else ".000"

    outs = pitching["OUTS"] or 0
    ip_f = outs // 3
    ip_r = outs % 3
    pitching["IP"] = f"{ip_f}.{ip_r}"
    er = pitching["ER"]
    pitching["ERA"] = f"{er*27/outs:.2f}" if outs else "-.--"
    gs = pitching["GS"]
    pc = pitching["PC"]
    pitching["AVG PC"] = f"{pc/gs:.1f}" if gs else "—"

    return {
        "games": row["games_played"],
        "batting": batting,
        "pitching": pitching,
    }


# ---------------------------------------------------------------------------
# Ratings
# ---------------------------------------------------------------------------


def compute_ratings(row: dict) -> dict:
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from src.player.player_record import PlayerRecord
        from src.player.player_in_game import PlayerInGame

        record = PlayerRecord.from_csv_row(row)
        pig = PlayerInGame(record)
        return pig.ratings
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------


def format_skills_line(row: dict) -> str:
    parts = []
    for skill_key, abbr in SKILL_ABBRS:
        val = row.get(abbr, "—")
        parts.append(f"{abbr}:{str(val):>3}")
    # 8 per line
    lines = []
    for i in range(0, len(parts), 8):
        lines.append("  " + "   ".join(parts[i : i + 8]))
    return "\n".join(lines)


def format_caps_line(caps: dict) -> str:
    if not caps:
        return "  (no caps found)"
    parts = []
    for col in CAP_SKILL_ORDER:
        abbr = SKILL_ABBREVIATIONS.get(col, col)
        val = caps.get(col, "—")
        parts.append(f"{abbr}:{str(val):>3}")
    lines = []
    for i in range(0, len(parts), 8):
        lines.append("  " + "   ".join(parts[i : i + 8]))
    return "\n".join(lines)


def format_ratings_line(ratings: dict) -> str:
    if not ratings:
        return "  (ratings unavailable)"
    def_pos = ["c", "1b", "2b", "ss", "3b", "lf", "cf", "rf"]
    line1 = "  " + "   ".join(f"{p.upper():3s}:{ratings.get(p,0):>3}" for p in def_pos)
    line2 = "  SP:{:>3}   RP:{:>3}   P:{:>3}".format(
        ratings.get("sp", 0), ratings.get("rp", 0), ratings.get("p", 0)
    )
    off = [
        ("lead_off", "LO"),
        ("contact_hitter", "CON"),
        ("power_hitter", "PWR"),
        ("overall_offense", "OFF"),
        ("overall_player", "OVR"),
    ]
    line3 = "  " + "   ".join(f"{a}:{ratings.get(k,0):>3}" for k, a in off)
    return "\n".join([line1, line2, line3])


def format_batting(b: dict) -> str:
    return (
        f"  AVG:{b['AVG']}  OBP:{b['OBP']}  AB:{b['AB']}  H:{b['H']}  "
        f"2B:{b['2B']}  3B:{b['3B']}  HR:{b['HR']}\n"
        f"  RBI:{b['RBI']}  R:{b['R']}  BB:{b['BB']}  SO:{b['SO']}  SB:{b['SB']}"
    )


def format_pitching(p: dict) -> str:
    return (
        f"  ERA:{p['ERA']}  IP:{p['IP']}  GS:{p['GS']}  "
        f"W:{p['W']}  L:{p['L']}  SV:{p['SV']}\n"
        f"  H:{p['H']}  ER:{p['ER']}  BB:{p['BB']}  SO:{p['SO']}  "
        f"HR:{p['HR']}  PC:{p['PC']}  AVG PC:{p['AVG PC']}"
    )


def build_report(
    player_id: str,
    canonical_name: str,
    appearances: list[dict],
    caps: dict | None,
    seasons_db: list[dict],
    db_file: str,
) -> str:
    lines = []
    sep = "=" * 62

    lines.append(sep)
    lines.append(f"  CAREER TRACE: {canonical_name}")
    lines.append(f"  ID: {player_id}")
    lines.append(sep)

    # ── Talent Caps ──
    lines.append("\nTALENT CAPS:")
    lines.append(format_caps_line(caps))

    # ── Build season_id -> year lookup ──
    year_to_sid = {s["year"]: s["id"] for s in seasons_db}

    # ── Per-season blocks ──
    lines.append("\n" + "─" * 62)
    lines.append("  SEASON-BY-SEASON")
    lines.append("─" * 62)

    for row in appearances:
        year = row.get("_season_year")
        team = row.get("_team", "?").upper()
        age = row.get("Age", "?")
        pos = row.get("PS", "?").upper()
        bats = row.get("B", "?")
        throws = row.get("T", "?")

        lines.append(f"\n{'─'*62}")
        lines.append(
            f"  {year or '????'} / {team}  |  Age {age}  |  {pos}  |  B:{bats} T:{throws}"
        )
        lines.append("─" * 62)

        # Skills
        lines.append("SKILLS:")
        lines.append(format_skills_line(row))

        # Ratings
        ratings = compute_ratings(row)
        lines.append("RATINGS:")
        lines.append(format_ratings_line(ratings))

        # Cap headroom snapshot (if caps available)
        if caps:
            headroom_parts = []
            for _, abbr in SKILL_ABBRS:
                col = SKILL_MAP.get(abbr)
                if not col:
                    continue
                cap_val = caps.get(col)
                cur_val_str = row.get(abbr, "")
                if cap_val is None or not str(cur_val_str).isdigit():
                    continue
                cur_val = int(cur_val_str)
                hdroom = cap_val - cur_val
                if hdroom != 0:
                    headroom_parts.append(
                        f"{abbr}:{cur_val}→{cap_val}(+{hdroom})"
                        if hdroom > 0
                        else f"{abbr}:{cur_val}→{cap_val}({hdroom})"
                    )
            if headroom_parts:
                lines.append("CAP HEADROOM (non-zero):")
                # wrap at ~70 chars
                chunk, cur_line = [], ""
                for p in headroom_parts:
                    if len(cur_line) + len(p) + 2 > 68:
                        lines.append("  " + "  ".join(chunk))
                        chunk, cur_line = [], ""
                    chunk.append(p)
                    cur_line += p + "  "
                if chunk:
                    lines.append("  " + "  ".join(chunk))

        # Season stats from DB
        season_id = year_to_sid.get(year) if year else None
        if season_id:
            stats = get_season_stats(db_file, player_id, season_id)
            if stats:
                lines.append(f"SEASON STATS  ({stats['games']} games):")
                b = stats["batting"]
                p = stats["pitching"]
                if b["AB"] > 0:
                    lines.append("  Batting:")
                    lines.append("  " + format_batting(b).replace("\n", "\n  "))
                if p["G"] > 0:
                    lines.append("  Pitching:")
                    lines.append("  " + format_pitching(p).replace("\n", "\n  "))
            else:
                lines.append("SEASON STATS: (no data in DB for this season)")
        else:
            lines.append("SEASON STATS: (season not in DB)")

    # ── Career totals ──
    lines.append(f"\n{'═'*62}")
    lines.append("  CAREER TOTALS")
    lines.append("═" * 62)

    career = get_career_stats(db_file, player_id)
    if career:
        lines.append(f"  {career['games']} games")
        b = career["batting"]
        p = career["pitching"]
        if b["AB"] > 0:
            lines.append("  Batting:")
            lines.append("  " + format_batting(b).replace("\n", "\n  "))
        if p["G"] > 0:
            lines.append("  Pitching:")
            lines.append("  " + format_pitching(p).replace("\n", "\n  "))
    else:
        lines.append("  (no career stats found)")

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    args = parse_args()
    directory = Path(args.dir)
    db_file = args.db

    if not directory.exists():
        print(f"Directory not found: {directory}")
        sys.exit(1)

    # Resolve player ID
    if args.player_id:
        players_to_trace = [(args.player_id.strip(), None)]
    else:
        players_to_trace = resolve_id_from_name(directory, args.name)
        if not players_to_trace:
            print(f"No player found matching '{args.name}'")
            sys.exit(1)
        if len(players_to_trace) > 1:
            print(
                f"Found {len(players_to_trace)} players matching '{args.name}' — tracing all.\n"
            )

    for player_id, canonical_name in players_to_trace:
        apps = find_all_appearances(directory, player_id)
        if not apps:
            print(f"No CSV appearances found for player {player_id} ({canonical_name})")
            continue

    canonical_name = canonical_name or apps[0]["Name"]
    caps = get_talent_caps(db_file, player_id)
    if not caps:
        print(f"  Warning: no talent caps found for {canonical_name} ({player_id})")

    seasons_db = get_all_seasons(db_file)
    report = build_report(player_id, canonical_name, apps, caps, seasons_db, db_file)
    print(report)

    name_parts = canonical_name.lower().split()
    filename = "_".join(name_parts) + f"_{player_id[:8]}.txt"
    out_dir = Path("temp_files")
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / filename
    out_path.write_text(report, encoding="utf-8")
    print(f"  → saved to {out_path}")


if __name__ == "__main__":
    main()
