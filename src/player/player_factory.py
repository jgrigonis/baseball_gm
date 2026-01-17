# src/player/player_factory.py
"""
The PlayerFactory class.

Create a PlayerRecord, their attributes, skills, etc.

CSV / Random / Import
        ↓
   PlayerFactory
        ↓
   PlayerRecord
        ↓
   PlayerRepository.insert()

PlayerFactory → creates PlayerRecord
PlayerRepository → persists PlayerRecord
PlayerInGame → runtime simulation

Generate names
If not supplied, generate a random position affinity
Generate handedness, if not specified
Generate base skills
Return a PlayerRecord

“The only legal way players are born into the world.”

"""
import logging
import random
import uuid

import src.game.game_exceptions as game_exceptions
from src.player.player_record import PlayerRecord
from src.player.player_skills import PlayerSkills
from src.player.positions import (
    POSITION_TEMPLATES,
    POSITIONS,
    PositionTemplate,
    is_valid_position,
    get_handedness_probabilities,
)
from src.name_generator.names import NameGenerator
from src.util.logger import setup_logger

VALID_BATS = {"left", "right", "switch"}
VALID_THROWS = {"left", "right"}
DEFAULT_LEFT_HANDED_PROB = 0.21  # Much higher than general population


class PlayerFactory(object):
    """Factory for creating persistent PlayerRecord instances."""

    def __init__(
        self, rng: random.Random | None = None, log_level: int | None = None
    ) -> None:
        self.rng = rng or random.Random()
        self.name_gen = NameGenerator(rng=self.rng)

        # Logging
        self.log_level = log_level or logging.INFO
        self.logger = logging.getLogger("pfactory")
        self.logger = setup_logger(
            name="pfactory", level=self.log_level, console_level=self.log_level
        )

    def _generate_id(self) -> str:
        return uuid.UUID(int=self.rng.getrandbits(128)).hex

    def create(
        self,
        *,
        position: str | None = None,
        bats: str | None = None,
        throws: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        gender: str = "male",
    ) -> PlayerRecord:
        """
        Create a brand new PlayerRecord with generated attributes and skills.
        """
        # -------------------------
        # Resolve core attributes
        # -------------------------
        self.logger.trace(
            f"Creating player: position={position}, throws={throws}, bats={bats}"
        )
        position = self._resolve_position(position)
        template = self._get_position_template(position)

        throws = self._resolve_handedness(position, throws, template)
        bats = self._resolve_batting_side(bats, throws, template)

        # -------------------------
        # Name generation
        # -------------------------
        first_name = first_name or self.name_gen.first(gender)
        last_name = last_name or self.name_gen.last()

        # -------------------------
        # Skill generation
        # -------------------------
        skills = PlayerSkills.generate(self.rng, position, throws)
        self.logger.trace(
            f"Created player: first_name={first_name}, last_name={last_name}, position={position}, throws={throws}, bats={bats}"
        )
        return PlayerRecord(
            id=self._generate_id(),
            first_name=first_name,
            last_name=last_name,
            bats=bats,
            throws=throws,
            position=position,
            skills=skills,
        )

    def _resolve_position(self, position: str | None) -> str:
        """
        Resolve position to a valid value.

        If position is None, randomly select one.
        Otherwise validate the provided position.

        Raises:
            BadPositionException: If position is invalid
        """
        if position is None:
            return self.rng.choice(POSITIONS)
        if not is_valid_position(position):
            raise game_exceptions.BadPositionException(
                f"Invalid position '{position}'. Valid: {', '.join(POSITIONS)}"
            )
        return position

    def _resolve_handedness(
        self, position: str | None, throws: str | None, template: dict
    ) -> str:
        """
        Resolve throwing handedness to a valid value.

        If throws is None, randomly select one. We use
        the player position to give variable probabilities
        for throwing handedness.

        Otherwise validate the provided value of throws.

        Raises:
            BadHandednessException: If throws is invalid
        """
        if throws is not None:
            self._validate_handedness(throws, VALID_THROWS, "throws")
            return throws

        probs = get_handedness_probabilities(position)
        throws_left_prob = probs.get("throws_left", DEFAULT_LEFT_HANDED_PROB)
        # throws_left_prob = template.get("throws_left", 0.21)
        return "left" if self.rng.random() < throws_left_prob else "right"

    def _resolve_batting_side(
        self,
        bats: str | None,
        throws: str,
        template: dict,
    ) -> str:
        """
        Resolve batting handedness to a valid value.

        If bats is None, randomly select one. We use
        the player's throwing handedness to give variable probabilities
        for batting handedness.

        Otherwise validate the provided value of bats.

        Raises:
            BadHandednessException: If bats is invalid
        """
        if bats is not None:
            self._validate_handedness(bats, VALID_BATS, "bats")
            return bats

        # Switch hitter?
        if self.rng.random() < template.get("switch_hitter", 0.09):
            return "switch"

        # Natural left-handed batter?
        if self.rng.random() < template.get("bats_left", 0.1):
            return "left"

        # Otherwise bat same as throwing hand
        return throws

    def _get_position_template(self, position: str) -> PositionTemplate:
        """
        This retrieves the position specific template from positions.py

        It includes:
        throws_left: float
        switch_hitter: float
        bats_left: float
        """
        try:
            return POSITION_TEMPLATES[position]
        except KeyError:
            raise game_exceptions.BadPositionException()

    def _validate_handedness(self, value: str, valid_set: set[str], label: str) -> None:
        """Validate handedness value."""
        if value not in valid_set:
            raise game_exceptions.BadHandednessException(
                f"Invalid {label}: '{value}'. Valid: {', '.join(sorted(valid_set))}"
            )
