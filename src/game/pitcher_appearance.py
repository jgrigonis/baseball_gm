# src/game/pitcher_appearance.py
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.player.player_in_game import PlayerInGame


@dataclass
class PitcherAppearance:
    pitcher: PlayerInGame
    team_id: str
    entered_inning: int
    finished_game: bool = False
    # Pitching team's lead when he came in (negative = trailing). None when
    # unknown, which falls back to judging a save on the final margin.
    lead_at_entry: int | None = None

    @property
    def outs_recorded(self) -> int:
        return self.pitcher.game_stats.pitching.outs

    @property
    def innings_pitched(self) -> float:
        return self.outs_recorded / 3.0


@dataclass
class LeadChange:
    inning: int
    half: str  # "top" | "bottom"
    new_leader: str  # team_id
    responsible_pitcher: PlayerInGame  # pitcher who gave up the lead-taking run
