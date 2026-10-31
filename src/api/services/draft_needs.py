# src/api/services/draft_needs.py
#
# Each team's suggested draft needs, from its roster, and the strategy each
# team drafts with: its saved strategy, or else those needs. A saved strategy
# with every need chip Low still drafts by those needs, keeping its pins and
# age slider. AI GMs never save one: they draft by need, weighed by their team
# state and persona (src/league/front_office.py): best available or need, an
# age slider, and offense for a bat-first GM.

from __future__ import annotations

import time

from src.api.services import front_office
from src.db.repositories.draft_repo import DraftRepository
from src.league import front_office as draft_rules
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
    needs = league_needs(
        draft_repo.get_roster_records(team_ids),
        draft_repo.get_staff_groups(team_ids),
    )
    _cache[draft_id] = (time.monotonic(), needs)
    return needs


def draft_strategies(
    db, draft_id: str, league_id: str, cached: bool = True
) -> dict[str, DraftStrategy]:
    """{team_id: DraftStrategy} for every team: saved, or else by need (an
    AI team's weighed by its outlook)."""
    draft_repo = DraftRepository(db)
    saved = draft_repo.get_strategies_by_team(draft_id, league_id)
    needs = needs_for_draft(db, draft_id, cached)
    draft = draft_repo.get_draft(draft_id)
    ai = front_office.outlooks(db, league_id, draft["season_id"] if draft else None)
    out = {}
    for tid, n in needs.items():
        if tid in saved:
            out[tid] = saved[tid].or_needs(n.chips)
        elif tid in ai:
            out[tid] = draft_rules.draft_strategy(n.chips, ai[tid].state, ai[tid].lean)
        else:
            out[tid] = n.strategy()
    return out
