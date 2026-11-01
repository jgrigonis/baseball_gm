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

from src.player.player_constants import VALID_BATS, VALID_THROWS
from src.player.player_skills import PlayerSkills
from src.player.positions import ALL_POSITIONS, is_pitcher
from src.types.rows import DbRow

type PlayerId = str
type BattingSide = str  # "L" | "R" | "S"
type ThrowingHand = str  # "L" | "R"
type PositionCode = str  # "ss" | "cf" | etc.


@dataclass(frozen=True)
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
    caps: dict | None = None  # only set when generated, not from CSV

    def __post_init__(self):
        """Validate player data after initialization."""
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
    def name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def age(self) -> int:
        return self.skills.age

    def __str__(self) -> str:
        return f"{self.name}"

    def __repr__(self) -> str:
        return (
            f"PlayerRecord(id='{self.id}', name='{self.name}', "
            f"pos='{self.position}', bats='{self.bats}', throws='{self.throws}')"
        )

    @classmethod
    def from_db_row(cls, row: DbRow) -> PlayerRecord:
        return cls(
            id=row["id"],
            first_name=row["first_name"],
            last_name=row["last_name"],
            bats=row["bats"],
            throws=row["throws"],
            skills=PlayerSkills.from_db_row(row),
            position=row["position"],
        )

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

    def __lt__(self, other: PlayerRecord) -> bool:
        """Sort by last name, then first name."""
        if not isinstance(other, PlayerRecord):
            return NotImplemented
        return (self.last_name, self.first_name) < (other.last_name, other.first_name)

    @property
    def accuracy(self) -> int:
        """Shortcut to accuracy skill."""
        return self.skills["accuracy"]

    @property
    def stamina(self) -> int:
        """Shortcut to stamina skill."""
        return self.skills["stamina"]

    @property
    def recovery(self) -> int:
        """Shortcut to recovery skill."""
        return self.skills["recovery"]

    @property
    def ground_balls(self) -> int:
        """Shortcut to ground_balls skill."""
        return self.skills["ground_balls"]

    @property
    def strikes(self) -> int:
        """Shortcut to strikes skill."""
        return self.skills["strikes"]

    @property
    def clutch(self) -> int:
        """Shortcut to clutch skill."""
        return self.skills["clutch"]

    @property
    def speed(self) -> int:
        """Shortcut to speed skill."""
        return self.skills["speed"]

    @property
    def power(self) -> int:
        """Shortcut to power skill."""
        return self.skills["power"]

    @property
    def eye(self) -> int:
        """Shortcut to eye skill."""
        return self.skills["eye"]

    @property
    def contact(self) -> int:
        """Shortcut to contact skill."""
        return self.skills["contact"]

    @property
    def base_running(self) -> int:
        """Shortcut to base_running skill."""
        return self.skills["base_running"]

    @property
    def bunting(self) -> int:
        """Shortcut to bunting skill."""
        return self.skills["bunting"]

    @property
    def catching(self) -> int:
        """Shortcut to catching skill."""
        return self.skills["catching"]

    @property
    def infield(self) -> int:
        """Shortcut to infield skill."""
        return self.skills["infield"]

    @property
    def outfield(self) -> int:
        """Shortcut to outfield skill."""
        return self.skills["outfield"]

    @property
    def arm(self) -> int:
        """Shortcut to arm skill."""
        return self.skills["arm"]
