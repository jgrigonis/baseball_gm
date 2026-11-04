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
    # Runners on base when he came in. With the lead, they decide whether
    # the tying run was on base, at bat or on deck.
    runners_at_entry: int = 0
    # Set once a run against him ties the game or puts his team behind. A
    # pitcher who gives the lead away can't get a hold or a save, even if
    # his team takes it back.
    lead_lost: bool = False

    @property
    def entered_in_save_situation(self) -> bool:
        """He came in leading by 1-3, or with the tying run on base, at bat
        or on deck. (Pitching three innings with any lead also makes a save
        situation; callers check that against outs recorded.)"""
        lead = self.lead_at_entry
        if lead is None or lead < 1:
            return False
        return lead <= 3 or lead <= self.runners_at_entry + 2

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
