# src/game/game_result_resolver.py

from dataclasses import dataclass, field
from src.game.pitcher_appearance import PitcherAppearance, LeadChange


@dataclass
class PitchingDecisions:
    win: PitcherAppearance | None = None
    loss: PitcherAppearance | None = None
    save: PitcherAppearance | None = None
    holds: list[PitcherAppearance] = field(default_factory=list)


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
        # A pitcher other than the winner who finished the game and got at
        # least one out, and came in with a lead of 1-3 runs, or with the
        # tying run on base, at bat or on deck, or held a lead over 3+
        # innings. A pitcher who came in tied or behind, or who gave the lead
        # away, can't save it.
        finishing_pitcher = next(
            (a for a in winning_appearances if a.finished_game), None
        )
        if (
            finishing_pitcher is not None
            and decisions.win is not None
            and finishing_pitcher.pitcher != decisions.win.pitcher
            and GameResultResolver._is_save(
                finishing_pitcher, winning_score - losing_score
            )
        ):
            decisions.save = finishing_pitcher

        decisions.holds = GameResultResolver._holds(pitcher_appearances, decisions)

        return decisions

    @staticmethod
    def _holds(
        pitcher_appearances: list[PitcherAppearance],
        decisions: PitchingDecisions,
    ) -> list[PitcherAppearance]:
        """MLB's hold: a reliever who came in with a save situation, got at
        least one out, and left without giving up the lead, without finishing
        the game. A pitcher with the win or the save doesn't also get a hold.
        Either team can have holds: a setup man who hands over the lead keeps
        his hold even if a later pitcher blows it."""
        credited = {
            id(d.pitcher) for d in (decisions.win, decisions.save) if d is not None
        }
        starters: set[str] = set()
        holds = []
        for appearance in pitcher_appearances:
            if appearance.team_id not in starters:
                starters.add(appearance.team_id)
                continue  # a starter isn't a relief pitcher
            lead = appearance.lead_at_entry
            if lead is None or lead < 1:
                continue  # came in tied or behind (or the score isn't known)
            outs = appearance.outs_recorded
            if (
                not appearance.finished_game
                and not appearance.lead_lost
                and outs >= 1
                and id(appearance.pitcher) not in credited
                and (appearance.entered_in_save_situation or outs >= 9)
            ):
                holds.append(appearance)
        return holds

    @staticmethod
    def _is_save(appearance: PitcherAppearance, margin: int) -> bool:
        lead = appearance.lead_at_entry
        if lead is None:
            # Older callers that don't track the score at entry
            return margin <= 3
        if lead < 1 or appearance.outs_recorded < 1 or appearance.lead_lost:
            return False
        return appearance.entered_in_save_situation or appearance.outs_recorded >= 9
