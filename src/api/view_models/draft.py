# src/api/view_models/draft.py
#
# Context for the draft results: every pick, grouped by round.

from __future__ import annotations

from src.db.repositories.draft_repo import DraftRepository
from src.db.repositories.gm_repo import GMRepository


def draft_rounds(
    db, league_id: str, draft_id: str, my_team_id: str | None
) -> list[dict]:
    """[{round, picks}] in pick order, with the GM's and other humans' picks
    flagged."""
    picks = DraftRepository(db).get_picks_with_details(draft_id)
    human_team_ids = GMRepository(db).get_human_team_ids(league_id)

    rounds_map: dict[int, list] = {}
    for pick in picks:
        is_mine = pick["team_id"] == my_team_id
        is_human = pick["team_id"] in human_team_ids and not is_mine
        rounds_map.setdefault(pick["round"], []).append(
            {
                "pick_number": pick["pick_number"],
                "team_id": pick["team_id"],
                "player_id": pick["player_id"],
                "team_name": f"{pick['city']} {pick['mascot']}",
                "player_name": f"{pick['first_name']} {pick['last_name']}",
                "position": pick["position"] or "%s",
                "auto_picked": bool(pick["auto_picked"]),
                "is_mine": is_mine,
                "is_human": is_human,
            }
        )
    return [{"round": r, "picks": p} for r, p in sorted(rounds_map.items())]
