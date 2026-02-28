# src/game/game_result_resolver.py

from dataclasses import dataclass
from src.game.pitcher_appearance import PitcherAppearance, LeadChange


@dataclass
class PitchingDecisions:
    win: PitcherAppearance | None = None
    loss: PitcherAppearance | None = None
    save: PitcherAppearance | None = None


class GameResultResolver:
    """
    Resolve the pitching decisions for a game.
    """
    @staticmethod
    def resolve(
        pitcher_appearances: list[PitcherAppearance],
        lead_changes: list[LeadChange],
        winning_team_id: str,
        losing_team_id: str,
        winning_score: int,
        losing_score: int,
    ) -> PitchingDecisions:
        return GameResultResolver._resolve_simple(
            pitcher_appearances,
            lead_changes,
            winning_team_id,
            losing_team_id,
            winning_score,
            losing_score,
        )

    @staticmethod
    def _resolve_simple(
        pitcher_appearances: list[PitcherAppearance],
        lead_changes: list[LeadChange],
        winning_team_id: str,
        losing_team_id: str,
        winning_score: int,
        losing_score: int,
    ) -> PitchingDecisions:
        decisions = PitchingDecisions()

        winning_appearances = [
            a for a in pitcher_appearances if a.team_id == winning_team_id
        ]
        losing_appearances = [
            a for a in pitcher_appearances if a.team_id == losing_team_id
        ]

        # --- LOSS ---
        # The pitcher on the losing team who was responsible for the go-ahead run.
        # That's the responsible_pitcher on the final lead change (the one that
        # gave the winning team a lead they never relinquished).
        if lead_changes:
            final_lead_change = lead_changes[-1]
            losing_pitcher = final_lead_change.responsible_pitcher
            # Find their appearance
            decisions.loss = next(
                (a for a in losing_appearances if a.pitcher == losing_pitcher),
                None,
            )

        # --- WIN ---
        # The winning pitcher is the one on the winning team who was pitching
        # when the go-ahead run scored, provided they were still pitching when
        # their team took the lead (i.e. they "held" it).
        # Simple rule: pitcher of record is the winning team's pitcher who was
        # active at the time of the go-ahead lead change.
        #
        # We find the last lead change that gave the winning team the lead,
        # then find which winning-team pitcher was active at that inning.
        if lead_changes:
            final_lead_change = lead_changes[-1]
            go_ahead_inning = final_lead_change.inning
            # go_ahead_half = final_lead_change.half # not used

            # Find the winning team's pitcher who was pitching during that inning/half
            # i.e. entered at or before that point and hadn't been replaced yet
            winning_pitcher_at_goahead = None
            for appearance in reversed(winning_appearances):
                if appearance.entered_inning < go_ahead_inning:
                    winning_pitcher_at_goahead = appearance
                    break
                if appearance.entered_inning == go_ahead_inning:
                    # Same inning — if go-ahead was in "top" (away scoring),
                    # the home pitcher was pitching; if "bottom", the away pitcher was.
                    # The winning team's pitcher was pitching when the other team scored,
                    # so they were on defense — they're the one giving up the go-ahead.
                    # Actually for the WIN, we want the winning team's pitcher who was
                    # on the mound when THEIR team took the lead in the next half.
                    winning_pitcher_at_goahead = appearance
                    break

            decisions.win = winning_pitcher_at_goahead

        # --- SAVE ---
        # Save conditions (simplified):
        # 1. A different pitcher than the winner finished the game
        # 2. The winning margin was 3 runs or fewer OR the tying run was on base/at bat
        finishing_pitcher = next(
            (a for a in winning_appearances if a.finished_game), None
        )
        margin = winning_score - losing_score
        if (
            finishing_pitcher is not None
            and decisions.win is not None
            and finishing_pitcher.pitcher != decisions.win.pitcher
            and margin <= 3
        ):
            decisions.save = finishing_pitcher

        return decisions
