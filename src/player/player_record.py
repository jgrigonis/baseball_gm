# src/player/player_record.py
"""
Database identity & History for a player.

PlayerFactory  →  PlayerRecord  →  PlayerInGame
        │               │               │
        │        persistent data   volatile state
        └──── RNG & rules

PlayerRecord  ── snapshot ──▶  PlayerInGame
      ▲                              │
      └────── apply results ◀────────┘

If you ever think “this changes during a game”,
it does not belong here.
"""

from dataclasses import dataclass

from src.player.player_skills import PlayerSkills
from src.types.rows import CsvRow, DbRow
from typing import TypeAlias

PlayerId: TypeAlias = str
BattingSide: TypeAlias = str  # "left" | "right" | "switch"
ThrowingHand: TypeAlias = str  # "left" | "right"
PositionCode: TypeAlias = str  # "ss" | "cf" | etc.


@dataclass(slots=True, frozen=True)
class PlayerRecord:
    """
    Persistent, authoritative player data.
    Maps 1:1 to a row in the `players` table.
    """

    id: PlayerId
    first_name: str
    last_name: str
    bats: BattingSide
    throws: ThrowingHand
    position: PositionCode
    skills: PlayerSkills

    @property
    def name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    def __str__(self) -> str:
        return f"{self.name}"

    def __repr__(self) -> str:
        return (
            f"PlayerRecord(id='{self.id}', name='{self.name}', "
            f"pos='{self.position}', bats='{self.bats}', throws='{self.throws}')"
        )

    @classmethod
    def from_csv_row(cls, row: CsvRow) -> "PlayerRecord":
        """Create PlayerRecord from CSV row with abbreviated codes."""
        try:
            # Parse name
            full_name = row["Name"]
            parts = full_name.split(maxsplit=1)
            first_name = parts[0]
            last_name = parts[1] if len(parts) > 1 else ""

            # Convert single-letter codes to full names
            bats_map = {"l": "left", "r": "right", "s": "switch"}
            throws_map = {"l": "left", "r": "right"}

            bats = bats_map.get(row["B"].lower())
            throws = throws_map.get(row["T"].lower())

            if not bats:
                raise ValueError(f"Invalid bats code: {row['B']}")
            if not throws:
                raise ValueError(f"Invalid throws code: {row['T']}")

            return cls(
                id=row["ID"],
                first_name=first_name,
                last_name=last_name,
                bats=bats,
                throws=throws,
                position=row["PS"].lower(),
                skills=PlayerSkills.from_csv_row(row),
            )
        except KeyError as e:
            raise ValueError(f"Missing required CSV column: {e}") from e

    # @classmethod
    # def from_csv_row(cls, row: CsvRow) -> "PlayerRecord":
    #     full_name = row["Name"]
    #     parts = full_name.split(maxsplit=1)
    #     first_name = parts[0]
    #     last_name = parts[1] if len(parts) > 1 else ""

    #     # Map single letters to full names
    #     bats_map = {"l": "left", "r": "right", "s": "switch"}
    #     throws_map = {"l": "left", "r": "right"}

    #     bats_letter = row["B"].lower()
    #     throws_letter = row["T"].lower()

    #     return cls(
    #         id=row["ID"],
    #         first_name=first_name,
    #         last_name=last_name,
    #         bats=bats_map[bats_letter],
    #         throws=throws_map[throws_letter],
    #         position=row["PS"].lower(),
    #         skills=PlayerSkills.from_csv_row(row),
    #     )

    # @classmethod
    # def from_csv_row(cls, row: CsvRow) -> "PlayerRecord":
    #     """
    #     Create a PlayerRecord from a CSV row.

    #     CSV format uses single-letter abbreviations:
    #     - B: batting side (l/r/s)
    #     - T: throwing hand (l/r)
    #     - PS: position (lowercase)
    #     """
    #     try:
    #         full_name = row["Name"]
    #         parts = full_name.split(maxsplit=1)
    #         first_name = parts[0]
    #         last_name = parts[1] if len(parts) > 1 else ""

    #         return cls(
    #             id=row["ID"],
    #             first_name=first_name,
    #             last_name=last_name,
    #             bats=row["B"].lower(),      # Normalize to lowercase
    #             throws=row["T"].lower(),    # Normalize to lowercase
    #             position=row["PS"].lower(), # Normalize to lowercase
    #             skills=PlayerSkills.from_csv_row(row),
    #         )
    #     except KeyError as e:
    #         raise ValueError(f"Missing required CSV column: {e}") from e
    #     except Exception as e:
    #         raise ValueError(f"Error creating PlayerRecord from CSV: {e}") from e

    # @classmethod
    # def from_csv_row(cls, row: CsvRow) -> "PlayerRecord":
    #     try:
    #         full_name = row["Name"]
    #         # Handle names with multiple spaces or single names
    #         parts = full_name.split(maxsplit=1)
    #         first_name = parts[0]
    #         last_name = parts[1] if len(parts) > 1 else ""

    #         return cls(
    #             id=row["ID"],
    #             first_name=first_name,
    #             last_name=last_name,
    #             bats=row["B"],
    #             throws=row["T"],
    #             skills=PlayerSkills.from_csv_row(row),
    #             position=row["PS"],
    #         )
    #     except KeyError as e:
    #         raise ValueError(f"Missing required CSV column: {e}") from e
    #     except Exception as e:
    #         raise ValueError(f"Error creating PlayerRecord from CSV: {e}") from e

    # @classmethod
    # def from_csv_row(cls, row: CsvRow) -> "PlayerRecord":
    #     full_name = row["Name"]

    #     # Handle names with multiple spaces or single names
    #     parts = full_name.split(maxsplit=1)
    #     if len(parts) == 1:
    #         first_name = parts[0]
    #         last_name = ""
    #     else:
    #         first_name, last_name = parts

    #     return cls(
    #         id=row["ID"],
    #         first_name=first_name,
    #         last_name=last_name,
    #         bats=row["B"],
    #         throws=row["T"],
    #         skills=PlayerSkills.from_csv_row(row),
    #         position=row["PS"],
    #     )

    # @classmethod
    # def from_csv_row(cls, row: CsvRow) -> "PlayerRecord":
    #     first, last = row["Name"].split(" ", 1)
    #     return cls(
    #         id=row["ID"],
    #         first_name=first,
    #         last_name=last,
    #         bats=row["B"],
    #         throws=row["T"],
    #         skills=PlayerSkills.from_csv_row(row),
    #         position=row["PS"],
    #     )

    @classmethod
    def from_db_row(cls, row: DbRow) -> "PlayerRecord":
        return cls(
            id=row["id"],
            first_name=row["first_name"],
            last_name=row["last_name"],
            bats=row["bats"],
            throws=row["throws"],
            skills=PlayerSkills.from_db_row(row),
            position=row["position"],
        )

    def __post_init__(self):
        """Validate player data after initialization."""
        from src.player.positions import ALL_POSITIONS
        from src.player.player_factory import VALID_BATS, VALID_THROWS
        
        if self.position not in ALL_POSITIONS:
            raise ValueError(
                f"Invalid position: {self.position}. "
                f"Valid positions: {', '.join(sorted(ALL_POSITIONS))}"
            )
        
        if self.bats not in VALID_BATS:
            raise ValueError(f"Invalid bats: {self.bats}")
        
        if self.throws not in VALID_THROWS:
            raise ValueError(f"Invalid throws: {self.throws}")
        
        if not self.first_name or not self.last_name:
            raise ValueError("Name cannot be empty")
        
        if not self.id:
            raise ValueError("ID cannot be empty")

    @property
    def full_name(self) -> str:
        """Full name (alias for name property)."""
        return self.name

    @property
    def initials(self) -> str:
        """Player initials (e.g., 'J.D.' for John Doe)."""
        first_initial = self.first_name[0] if self.first_name else ""
        last_initial = self.last_name[0] if self.last_name else ""
        return f"{first_initial}.{last_initial}."

    def is_pitcher(self) -> bool:
        """True if player is a pitcher."""
        from src.player.positions import is_pitcher

        return is_pitcher(self.position)

    def is_switch_hitter(self) -> bool:
        """True if player switch hits."""
        return self.bats == "switch"

    def is_left_handed(self) -> bool:
        """True if player throws left-handed."""
        return self.throws == "left"

    def to_db_dict(self) -> dict[str, any]:
        """Convert to dictionary for database storage."""
        skills_dict = self.skills.to_db_dict()
        return {
            "id": self.id,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "bats": self.bats,
            "throws": self.throws,
            "position": self.position,
            **skills_dict,  # Flatten skills into the dict
        }

    def to_csv_dict(self) -> dict[str, any]:
        """Convert to dictionary for CSV export."""
        skills_dict = self.skills.to_csv_dict()

        # Convert bats to single letter
        bats_abbr = {"left": "L", "right": "R", "switch": "S"}[self.bats]

        # Convert throws to single letter
        throws_abbr = {"left": "L", "right": "R"}[self.throws]

        return {
            "ID": self.id,
            "Name": self.name,
            "B": bats_abbr,
            "T": throws_abbr,
            "PS": self.position,
            **skills_dict,
        }

    def __lt__(self, other: "PlayerRecord") -> bool:
        """Sort by last name, then first name."""
        if not isinstance(other, PlayerRecord):
            return NotImplemented
        return (self.last_name, self.first_name) < (other.last_name, other.first_name)

    @property
    def power(self) -> int:
        """Shortcut to power skill."""
        return self.skills["power"]

    @property
    def speed(self) -> int:
        """Shortcut to speed skill."""
        return self.skills["speed"]


# etc. for commonly accessed skills
# TODO add more shortcuts
