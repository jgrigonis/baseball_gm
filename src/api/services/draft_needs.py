# src/api/services/draft_needs.py
#
# Each team's suggested draft needs, from its roster, and the strategy each
# team drafts with: its saved strategy, or else those needs. A saved strategy
# with every need chip Off still drafts by those needs, keeping its pins and
# age slider. AI GMs never save one, so they always draft by need.

from __future__ import annotations

import time

from src.db.repositories.draft_repo import DraftRepository
from src.league.offseason.draft_needs import TeamNeeds, league_needs
from src.league.offseason.draft_strategy import DraftStrategy

# Rosters don't change while a draft waits to run, and working out needs reads
# every roster in the league, so the draft page and its preview share a copy.
CACHE_SECONDS = 300
_cache: dict[str, tuple[float, dict[str, TeamNeeds]]] = {}


def needs_for_draft(db, draft_id: str, cached: bool = True) -> dict[str, TeamNeeds]:
    """{team_id: TeamNeeds} for every team in the draft order."""
    hit = _cache.get(draft_id)
    if cached and hit and time.monotonic() - hit[0] < CACHE_SECONDS:
        return hit[1]
    draft_repo = DraftRepository(db)
    team_ids = [r["team_id"] for r in draft_repo.get_team_id_draft_order(draft_id)]
    needs = league_needs(draft_repo.get_roster_records(team_ids))
    _cache[draft_id] = (time.monotonic(), needs)
    return needs


def draft_strategies(
    db, draft_id: str, league_id: str, cached: bool = True
) -> dict[str, DraftStrategy]:
    """{team_id: DraftStrategy} for every team: saved, or else by need."""
    saved = DraftRepository(db).get_strategies_by_team(draft_id, league_id)
    needs = needs_for_draft(db, draft_id, cached)
    return {
        tid: saved[tid].or_needs(n.chips) if tid in saved else n.strategy()
        for tid, n in needs.items()
    }
