"""
The PlayerFactory class.

Create a PlayerRecord, their stats, attributes, skills, etc.

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

import random
import uuid

import src.game.game_exceptions as game_exceptions
from src.player.player_record import PlayerRecord
from src.player.player_skills import PlayerSkills
from src.player.positions import POSITION_TEMPLATES, POSITIONS
from src.name_generator.names import NameGenerator

BATS = {"left", "right", "switch"}
THROWS = {"left", "right"}


class PlayerFactory(object):
    """Factory for creating persistent PlayerRecord instances."""

    def __init__(self, rng: random.Random | None = None):
        self.rng = rng or random.Random()
        self.name_gen = NameGenerator(rng=self.rng)

    def _generate_id(self) -> str:
        return uuid.UUID(int=self.rng.getrandbits(128)).hex

    def create(
        self,
        *,
        position: str | None = None,
        bats: str | None = None,
        throws: str | None = None,
    ) -> PlayerRecord:
        """
        Create a brand new PlayerRecord with generated attributes and skills.
        """
        # -------------------------
        # Resolve core attributes
        # -------------------------
        position = self._resolve_position(position)
        template = self._get_position_template(position)

        throws = self._resolve_handedness(throws, template)
        bats = self._resolve_batting_side(bats, throws, template)

        # -------------------------
        # Name generation
        # -------------------------
        first_name = self.name_gen.first("male")
        last_name = self.name_gen.last()

        # -------------------------
        # Skill generation
        # -------------------------
        skills = PlayerSkills.generate(self.rng, position, throws)

        return PlayerRecord(
            id=self._generate_id(),
            first_name=first_name,
            last_name=last_name,
            bats=bats,
            throws=throws,
            skills=skills,
        )

    def _resolve_position(self, position: str | None) -> str:
        if position is None:
            return self.rng.choice(POSITIONS)
        if position not in POSITIONS:
            raise game_exceptions.BadPositionException()
        return position

    def _resolve_handedness(self, throws: str | None, template: dict) -> str:
        if throws is not None:
            if throws not in THROWS:
                raise game_exceptions.BadHandednessException()
            return throws

        throws_left_prob = template.get("throws_left", 0.21)
        return "left" if self.rng.random() < throws_left_prob else "right"

    def _resolve_batting_side(
        self,
        bats: str | None,
        throws: str,
        template: dict,
    ) -> str:
        if bats is not None:
            if bats not in BATS:
                raise game_exceptions.BadHandednessException()
            return bats

        # Switch hitter?
        if self.rng.random() < template.get("switch_hitter", 0.09):
            return "switch"

        # Natural left-handed batter?
        if self.rng.random() < template.get("bats_left", 0.1):
            return "left"

        # Otherwise bat same as throwing hand
        return throws

    def _get_position_template(self, position: str) -> dict:
        try:
            return POSITION_TEMPLATES[position]
        except KeyError:
            raise game_exceptions.BadPositionException()
