"""
Look up a player by name across team CSV files, display their skills,
ratings, and season stats from the database.

Usage:
    python player_lookup.py "John Smith"
    python player_lookup.py "John Smith" --season 2025
    python player_lookup.py "John Smith" --season 2025 --db path/to/db.sqlite
    python player_lookup.py "John Smith" --dir team_files/2025

Defaults:
    --dir   team_files/
    --db    league.db
"""

import argparse
import csv
import sqlite3
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Args
# ---------------------------------------------------------------------------


def parse_args():
    parser = argparse.ArgumentParser(description="Look up a player by name.")
    parser.add_argument("name", help="Player name (case-insensitive, partial match ok)")
    parser.add_argument("--dir", default="team_files", help="Directory of team CSVs")
    parser.add_argument(
        "--season", help="Season year or name to filter stats (e.g. 2025)"
    )
    parser.add_argument(
        "--db", default="leagues/league.db", help="Path to SQLite database"
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# CSV search
# ---------------------------------------------------------------------------


def find_players_in_csvs(name_query: str, directory: Path) -> list[dict]:
    """Search all CSVs for players matching name_query (case-insensitive)."""
    matches = []
    query = name_query.lower()

    for csv_path in sorted(directory.glob("**/*.csv")):
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if query in row.get("Name", "").lower():
                    matches.append({**row, "_source_file": csv_path.name})

    return matches


# ---------------------------------------------------------------------------
# Ratings
# ---------------------------------------------------------------------------


def compute_ratings(row: dict) -> dict:
    """Build PlayerRecord from CSV row and compute ratings."""
    # Lazy imports — keep script runnable from project root
    sys.path.insert(0, str(Path(__file__).parent))
    from src.player.player_record import PlayerRecord
    from src.player.player_in_game import PlayerInGame

    record = PlayerRecord.from_csv_row(row)
    pig = PlayerInGame(record)
    return pig.ratings


# ---------------------------------------------------------------------------
# Season stats query
# ---------------------------------------------------------------------------

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
    ("pitch_hold", "HLD"),
    ("pitch_outs", "OUTS"),
    ("pitch_hits", "H"),
    ("pitch_runs", "R"),
    ("pitch_walks", "BB"),
    ("pitch_strike_outs", "SO"),
    ("pitch_home_runs", "HR"),
    ("pitch_complete_game", "CG"),
    ("pitch_shutout", "SHO"),
    ("pitch_count", "PC"),
]


def query_season_stats(db_path: Path, player_id: str, season: str | None) -> dict:
    """
    Aggregate player_game_stats for a player, optionally filtered by season.
    Returns dict with 'batting', 'pitching', and 'games' keys.
    """
    if not db_path.exists():
        return {}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Show available seasons and resolve season_id
    cur.execute("SELECT id, year, name FROM seasons ORDER BY year")
    all_seasons = cur.fetchall()
    if not all_seasons:
        print("  Warning: no seasons found in database.")
        conn.close()
        return {}

    season_id = None
    if season:
        try:
            season_year = int(season)
        except ValueError:
            season_year = None
        for s in all_seasons:
            if (season_year and s["year"] == season_year) or s["name"] == season:
                season_id = s["id"]
                break
        if not season_id:
            print(f"  Warning: season '{season}' not found. Available seasons:")
            for s in all_seasons:
                print(f"    year={s['year']}  name={s['name']}  id={s['id']}")
    elif len(all_seasons) == 1:
        season_id = all_seasons[0]["id"]
    else:
        print("  Tip: multiple seasons in DB, use --season to filter:")
        for s in all_seasons:
            print(f"    year={s['year']}  name={s['name']}")

    # Build WHERE clause
    where = "WHERE pgs.player_id = ?"
    params: list = [player_id]
    if season_id:
        where += " AND g.season_id = ?"
        params.append(season_id)

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
        {where}
    """,
        params,
    )

    row = cur.fetchone()
    conn.close()

    if not row or row["games_played"] == 0:
        return {}

    batting = {label: (row[col] or 0) for col, label in BATTING_COLS}
    pitching = {label: (row[col] or 0) for col, label in PITCHING_COLS}

    # Derived batting stats
    ab = batting["AB"] or 1
    h = batting["H"]
    bb = batting["BB"]
    hbp = batting["HBP"]
    sf = batting["SF"]
    batting["AVG"] = f"{h / ab:.3f}" if ab else ".000"
    obp_denom = ab + bb + hbp + sf
    batting["OBP"] = f"{(h + bb + hbp) / obp_denom:.3f}" if obp_denom else ".000"

    # Derived pitching stats
    outs = pitching["OUTS"] or 0
    ip_full = outs // 3
    ip_rem = outs % 3
    pitching["IP"] = f"{ip_full}.{ip_rem}"
    er = pitching["R"]  # no earned runs yet — using runs as proxy
    pitching["ERA"] = f"{(er * 27 / outs):.2f}" if outs else "-.--"
    pitching["AVG PC"] = (
        f"{row['pitch_count'] / row['pitch_game_started']:.1f}"
        if (row["pitch_game_started"] or 0) > 0
        else "—"
    )

    return {
        "games": row["games_played"],
        "batting": batting,
        "pitching": pitching,
    }


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

SKILL_DISPLAY = [
    # Hitting
    ("contact", "CT"),
    ("power", "PO"),
    ("eye", "EY"),
    ("speed", "SP"),
    ("base_running", "BR"),
    ("bunting", "BU"),
    ("clutch", "CL"),
    # Defense
    ("catching", "CA"),
    ("infield", "IF"),
    ("outfield", "OF"),
    ("arm", "AR"),
    ("accuracy", "AC"),
    # Pitching
    ("stamina", "ST"),
    ("recovery", "RE"),
    ("ground_balls", "GB"),
    ("strikes", "KK"),
]


def display_player(row: dict, ratings: dict, stats: dict):
    name = row.get("Name", "Unknown")
    age = row.get("Age", "?")
    pos = row.get("PS", "?")
    bats = row.get("B", "?")
    throws = row.get("T", "?")
    team = row.get("_source_file", "?").replace(".csv", "")

    print()
    print("=" * 58)
    print(f"  {name}")
    print(
        f"  {team.upper()}  |  Age {age}  |  Pos {pos.upper()}  |  B:{bats} T:{throws}"
    )
    print("=" * 58)

    # Skills — 4 per row
    print("\nSKILLS:")
    chunks = [SKILL_DISPLAY[i : i + 4] for i in range(0, len(SKILL_DISPLAY), 4)]
    for chunk in chunks:
        parts = []
        for skill_key, abbr in chunk:
            val = row.get(abbr, "—")
            parts.append(f"{abbr}:{val:>3}")
        print("  " + "   ".join(parts))

    # Ratings
    print("\nRATINGS:")
    print("  Defensive positions:")
    def_pos = ["c", "1b", "2b", "ss", "3b", "lf", "cf", "rf"]
    line = "  " + "   ".join(f"{p.upper():3s}:{ratings.get(p, 0):>3}" for p in def_pos)
    print(line)

    print("  Pitching:")
    pit_line = "  " + "   ".join(
        f"{r.upper():3s}:{ratings.get(r, 0):>3}" for r in ["sp", "rp", "p"]
    )
    print(pit_line)

    print("  Offense / Overall:")
    off_roles = [
        ("lead_off", "LO"),
        ("contact_hitter", "CON"),
        ("power_hitter", "PWR"),
        ("overall_offense", "OFF"),
        ("overall_player", "OVR"),
    ]
    off_line = "  " + "   ".join(
        f"{abbr}:{ratings.get(role, 0):>3}" for role, abbr in off_roles
    )
    print(off_line)

    # Season stats
    if not stats:
        print("\nSEASON STATS: (no data found)")
        return

    print(f"\nSEASON STATS  ({stats['games']} games):")

    bat = stats["batting"]
    if bat["AB"] > 0:
        print("  Batting:")
        print(
            f"    AVG:{bat['AVG']}  OBP:{bat['OBP']}  "
            f"AB:{bat['AB']}  H:{bat['H']}  2B:{bat['2B']}  "
            f"3B:{bat['3B']}  HR:{bat['HR']}"
        )
        print(
            f"    RBI:{bat['RBI']}  R:{bat['R']}  BB:{bat['BB']}  "
            f"SO:{bat['SO']}  SB:{bat['SB']}"
        )

    pit = stats["pitching"]
    if pit["G"] > 0:
        print("  Pitching:")
        print(
            f"    ERA:{pit['ERA']}  IP:{pit['IP']}  "
            f"GS:{pit['GS']}  W:{pit['W']}  L:{pit['L']}  SV:{pit['SV']}"
        )
        print(
            f"    H:{pit['H']}  R:{pit['R']}  BB:{pit['BB']}  "
            f"SO:{pit['SO']}  HR:{pit['HR']}  PC:{pit['PC']}  AVG PC:{pit['AVG PC']}"
        )
        if pit["CG"] > 0:
            print(f"    CG:{pit['CG']}  SHO:{pit['SHO']}")

    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    args = parse_args()
    directory = Path(args.dir)

    if not directory.exists():
        print(f"Directory not found: {directory}")
        sys.exit(1)

    matches = find_players_in_csvs(args.name, directory)

    if not matches:
        print(f"No players found matching '{args.name}' in {directory}")
        sys.exit(0)

    if len(matches) > 1:
        print(f"Found {len(matches)} players matching '{args.name}':")
        for i, m in enumerate(matches):
            print(
                f"  [{i}] {m['Name']}  ({m.get('_source_file','?')})  Age:{m.get('Age','?')}  Pos:{m.get('PS','?')}"
            )
        choice = input("Select [0]: ").strip()
        idx = int(choice) if choice.isdigit() else 0
        row = matches[idx]
    else:
        row = matches[0]

    # Ratings
    try:
        ratings = compute_ratings(row)
    except Exception as e:
        print(f"  Warning: could not compute ratings: {e}")
        ratings = {}

    # DB stats
    db_path = Path(args.db)
    player_id = row.get("ID", "")
    season_stats = (
        query_season_stats(db_path, player_id, args.season) if player_id else {}
    )

    display_player(row, ratings, season_stats)


if __name__ == "__main__":
    main()
