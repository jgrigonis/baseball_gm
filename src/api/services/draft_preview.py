# src/api/services/draft_preview.py
#
# The draft page's projected picks: simulate the Blitz draft in memory with
# the strategy the GM is editing and return their first few picks.

from __future__ import annotations

from src.db.repositories.draft_repo import DraftRepository
from src.league.offseason.draft_strategy import (
    DraftStrategy,
    StrategyScorer,
    project_picks,
)
from src.league.offseason.snake_draft import ROUNDS
from src.player.player_evaluator import PlayerEvaluator

PREVIEW_PICKS = 5


def preview_picks(
    db, league_id: str, draft_id: str, team_id: str, strategy: DraftStrategy
) -> dict:
    """{"picks": [{pick, round, player_id}], "pins_gone": {player_id: pick}}:
    the team's first PREVIEW_PICKS picks, and which of its pins other teams
    take before then.

    Other human GMs follow their saved strategies and AI GMs take the best
    prospect rating. Saved preference lists are left out, so it's a guide,
    not a promise."""
    draft_repo = DraftRepository(db)
    order = [r["team_id"] for r in draft_repo.get_team_id_draft_order(draft_id)]
    empty = {"picks": [], "pins_gone": {}}
    if team_id not in order:
        return empty

    rated = sorted(
        (
            (p, PlayerEvaluator.prospect_rating(p.skills))
            for p in draft_repo.get_prospect_records(league_id)
        ),
        key=lambda x: x[1],
        reverse=True,
    )
    if not rated:
        return empty

    strategies = draft_repo.get_strategies_by_team(draft_id, league_id)
    strategies[team_id] = strategy

    taken: dict[str, int] = {}
    picks = project_picks(
        StrategyScorer(rated), order, ROUNDS, strategies, team_id, PREVIEW_PICKS, taken
    )
    return {
        "picks": [
            {"pick": pick, "round": (pick - 1) // len(order) + 1, "player_id": pid}
            for pick, pid in picks
        ],
        "pins_gone": {pid: taken[pid] for pid in strategy.pins if pid in taken},
    }
