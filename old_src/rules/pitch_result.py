# src/game/rules/pitch_result.py
from src.game.event_outcome import EventOutcome
from src.game.count import Count


def apply_pitch_result(count, pitch: str) -> str | None:
    """
    No EventOutcome here
    No resolver knowledge
    No ball-in-play handling
    """
    match pitch:
        case "ball":
            count.ball()
            if count.balls == 0:  # walk happened
                return "walk"

        case "strike":
            count.strike()
            if count.strikes == 0:  # strikeout happened
                return "strikeout"

        case "foul":
            count.strike()  # capped at 2
            return None

    return None


# def apply_pitch_result(count: Count, result: str) -> EventOutcome | None:
#     """
#     Applies a pitch-level raw result to the count.

#     Mutates `count`.

#     Returns:
#         None                → plate appearance continues
#         EventOutcome        → plate appearance ends OR ball put in play

#     - Mutates `count` via count.ball() / count.strike()
#     - Returns EventOutcome ONLY if the PA ends
#     - If PA ends, Count MUST be reset
#     - If PA continues, returns None
#     """
#     match result:
#         case "ball":
#             count.ball()
#             if count.balls == 0:  # reset occurred → walk
#                 return EventOutcome(
#                     type="walk",
#                     bases=1,
#                     description="Walk",
#                 )

#         case "strike":
#             count.strike()
#             if count.strikes == 0:  # reset occurred → strikeout
#                 return EventOutcome(
#                     type="strikeout",
#                     outs=1,
#                     description="Strikeout",
#                 )

#         case "foul":
#             # Fouls never end PA, may or may not add strike
#             if count.strikes < 2:
#                 count.strike()

#         case "foul_tip":
#             # Foul tip counts as a strike
#             count.strike()
#             if count.strikes == 0:  # third strike caught
#                 return EventOutcome(
#                     type="strikeout",
#                     outs=1,
#                     description="Strikeout on foul tip, caught",
#                 )

#         case "hit_by_pitch":
#             count.reset_count()
#             return EventOutcome(
#                 type="hit_by_pitch",
#                 bases=1,
#                 description="Hit by pitch",
#             )

#         case "in_play":
#             count.reset_count()
#             return None # signals ball put in play

#         case _:
#             raise ValueError(f"Unknown pitch result: {result}")

#     return None
