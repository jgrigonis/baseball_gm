# src/league/offseason/draft_generator.py
"""
Generates the prospect pool for the annual draft.

Steps:
1. Generate 650 new players at ages 18-22 with position distribution:
   - 55% pitchers: 27.5% sp, 27.5% rp
   - 45% position players: evenly split across 11 positions (~4.1% each)
2. Insert new players into DB with status 'prospect'
3. Collect existing unattached prospects (status=prospect/unassigned, no team)
4. Write draft.csv with all draftable players
"""

import csv
import dataclasses
import random
from pathlib import Path

from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.db.repositories.talent_cap_repo import TalentCapRepository
from src.player.player_factory import PlayerFactory
from src.player.player_skills import START_AGE
from src.player.talent_caps import generate_talent_caps
from src.util.locations import TEAM_FILES_DIR

# -----------------------------------------------------------------------
# Draft pool configuration
# -----------------------------------------------------------------------

DRAFT_POOL_SIZE = 650

# Age distribution for new prospects
AGE_DISTRIBUTION = [
    (18, 0.25),
    (19, 0.10),
    (20, 0.15),
    (21, 0.25),
    (22, 0.25),
]

# Position distribution
PITCHER_SHARE = 0.55
POSITION_PLAYER_SHARE = 0.45

PITCHER_POSITIONS = ["sp", "rp"]  # even split

POSITION_PLAYER_POSITIONS = [
    "c",
    "1b",
    "2b",
    "ss",
    "3b",
    "lf",
    "cf",
    "rf",
    "if",
    "of",
    "dh",
]


def _age_distribution_positions(rng: random.Random, n: int) -> list[tuple[int, str]]:
    """
    Return list of (age, position) for n prospects.
    Ages sampled from AGE_DISTRIBUTION, positions from weighted distribution.
    """
    # Build age pool
    ages = []
    cumulative = 0.0
    breakpoints = []
    for age, pct in AGE_DISTRIBUTION:
        cumulative += pct
        breakpoints.append((cumulative, age))

    for _ in range(n):
        r = rng.random()
        for threshold, age in breakpoints:
            if r <= threshold:
                ages.append(age)
                break
        else:
            ages.append(AGE_DISTRIBUTION[-1][0])

    # Build position pool
    n_pitchers = int(round(n * PITCHER_SHARE))
    n_position = n - n_pitchers

    positions = []
    for i in range(n_pitchers):
        positions.append(PITCHER_POSITIONS[i % len(PITCHER_POSITIONS)])

    per_pos = n_position // len(POSITION_PLAYER_POSITIONS)
    remainder = n_position % len(POSITION_PLAYER_POSITIONS)
    for pos in POSITION_PLAYER_POSITIONS:
        positions.extend([pos] * per_pos)
    for i in range(remainder):
        positions.append(POSITION_PLAYER_POSITIONS[i])

    rng.shuffle(positions)

    return list(zip(ages, positions))


class DraftGenerator:
    """
    Generates and persists the annual draft prospect pool.
    """

    def __init__(self, conn, rng: random.Random | None = None):
        self.conn = conn
        self.rng = rng or random.Random()
        self.player_repo = PlayerRepository(conn)
        self.status_repo = PlayerStatusRepository(conn)
        self.cap_repo = TalentCapRepository(conn)
        self.factory = PlayerFactory(rng=self.rng)

    def run(self, season_id: str, year: int) -> int:
        """
        Generate draft pool, insert into DB, write draft.csv.

        Args:
            season_id: Current season ID (used for output path)
            year: The year of the draft (used for output directory)

        Returns:
            Total number of draftable players written to CSV
        """
        # 1. Collect existing unattached prospects FIRST (before inserting new ones)
        existing = self._get_existing_draftable()
        print(f"  Found {len(existing)} existing undrafted prospects")

        # 2. Generate new prospects
        new_players = self._generate_prospects()
        print(f"  Generated {len(new_players)} new prospects")

        # 3. Insert into DB with status 'prospect'
        for player in new_players:
            self.player_repo.insert(
                id=player.id,
                first_name=player.first_name,
                last_name=player.last_name,
                bats=player.bats,
                throws=player.throws,
                position=player.position,
                skills=player.skills,
            )
            if player.caps is not None:
                self.cap_repo.insert(player.id, player.caps)
            self.status_repo.set_status(player.id, "prospect")

        # 4. Write draft.csv
        all_draftable = new_players + existing
        out_path = self._write_draft_csv(all_draftable, year)
        print(f"  Wrote {out_path} ({len(all_draftable)} players)")

        return len(all_draftable)

    def _generate_prospects(self):
        """Generate DRAFT_POOL_SIZE new players at appropriate ages."""
        age_positions = _age_distribution_positions(self.rng, DRAFT_POOL_SIZE)
        players = []

        for age, position in age_positions:
            # Create at age 17, then age forward
            player = self.factory.create(position=position)
            caps = generate_talent_caps(player.skills.as_dict(), rng=self.rng)
            if age > START_AGE:
                aged_skills = player.skills.age_to(age, rng=self.rng, caps=caps)
                player = dataclasses.replace(player, skills=aged_skills, caps=caps)

            players.append(player)

        return players

    def _get_existing_draftable(self):
        """
        Return existing players who are draftable:
        - status is 'prospect' or 'unassigned'
        - not on any team (no team_players row)
        - excludes newly generated players (already handled)
        """
        rows = self.conn.execute(
            """
            SELECT p.id
            FROM players p
            JOIN player_status ps ON p.id = ps.player_id
            LEFT JOIN team_players tp ON p.id = tp.player_id
            WHERE ps.status IN ('prospect', 'unassigned')
              AND tp.player_id IS NULL
            """
        ).fetchall()

        players = []
        for row in rows:
            player = self.player_repo.look_up(row["id"])
            if player:
                players.append(player)

        return players

    def _write_draft_csv(self, players, year: int) -> Path:
        """Write all draftable players to draft.csv."""
        out_dir = Path(TEAM_FILES_DIR) / str(year)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "draft.csv"

        if not players:
            return out_path

        rows = [p.to_csv_dict() for p in players]
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

        return out_path
