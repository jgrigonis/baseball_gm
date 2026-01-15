# src/game/events/out.py
from dataclasses import dataclass
from src.game.event import GameEvent


@dataclass(frozen=True)
class OutRecordedEvent(GameEvent):
    reason: str

    def apply(self, game):
        game.inning.record_out()


# # src/game/events/out.py
# from dataclasses import dataclass
# from typing import Optional

# from src.game.event import GameEvent


# @dataclass(frozen=True)
# class OutRecordedEvent(GameEvent):
#     """
#     A runner has been put out.

#     Plate appearances end when the batter is retired or
#     reaches base — never because an out occurred elsewhere.
#     """

#     runner_id: str
#     reason: Optional[str] = None
#     from_base: Optional[int] = None  # None → batter

#     def apply(self, game):
#         game.inning.record_out()

#         # Only end the PA if the batter was retired
#         if self.from_base is None:
#             game._mark_plate_appearance_complete(self.reason)
