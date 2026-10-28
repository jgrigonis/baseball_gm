# src/player/player_value.py
#
# One number for how good a player is in the role he'd play: the best of the
# starter and reliever ratings for a pitcher, the overall rating for a hitter.
# Uses only the visible ratings, never the hidden talent caps.

from __future__ import annotations

from src.player.player_evaluator import PlayerEvaluator
from src.player.player_record import PlayerRecord

# A reliever pitches a fraction of a starter's innings.
RELIEVER_DISCOUNT = 0.9


def role_rating(player: PlayerRecord) -> int:
    ratings = PlayerEvaluator.rate_player(player.skills, player.throws)
    if player.is_pitcher():
        return max(ratings["sp"], round(ratings["rp"] * RELIEVER_DISCOUNT))
    return ratings["overall_player"]
