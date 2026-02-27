# src/game/pitcher_appearance.py
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.player.player_in_game import PlayerInGame


@dataclass
class PitcherAppearance:
    pitcher: "PlayerInGame"
    team_id: str
    entered_inning: int
    finished_game: bool = False

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
    responsible_pitcher: "PlayerInGame"  # pitcher who gave up the lead-taking run
