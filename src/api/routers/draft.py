# src/api/routers/draft.py
#
# Draft tab: the prospect board, saving draft preferences, running the
# blitz draft, and the results page.

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from src.api.dependencies import DB, GM, IsHTMX, User
from src.api.services.draft_execute import execute_blitz_draft
from src.api.view_models.player_cards import draft_roster_card, prospect_card
from src.db.repositories.draft_repo import DraftRepository
from src.db.repositories.gm_repo import GMRepository
from src.db.repositories.player_repo import PlayerRepository
from src.web.utils import _shell_ctx, tab_response

router = APIRouter(tags=["web"])


# ── Draft actions ──────────────────────────────────────────────────────────────


@router.put("/leagues/{league_id}/draft/preferences")
async def save_draft_preferences(
    request: Request,
    league_id: str,
    db: DB,
    user: User,
    gm: GM,
    # gm_session: str | None = Cookie(default=None),
):
    """
    Save the GM's draft preference list. Called from JS using the session
    cookie — no token exposure needed. Proxies to the existing draft logic.
    """

    draft_repo = DraftRepository(db)

    draft = draft_repo.get_current_for_league(league_id)
    if not draft:
        return JSONResponse({"detail": "No draft found"}, status_code=404)
    if draft["state"] == "complete":
        return JSONResponse({"detail": "Draft is already complete"}, status_code=409)

    body = await request.json()
    player_ids = body.get("player_ids", [])
    if not player_ids:
        return JSONResponse({"detail": "player_ids required"}, status_code=422)

    missing = draft_repo.validate_player_ids(player_ids)
    if missing:
        return JSONResponse({"detail": f"Unknown player: {missing}"}, status_code=422)

    draft_repo.save_preferences(draft["id"], gm["id"], player_ids)
    db.commit()

    return JSONResponse({"saved": len(player_ids)})


# ── Tab: Draft ─────────────────────────────────────────────────────────────────


@router.get("/leagues/{league_id}/draft", response_class=HTMLResponse)
def draft_tab(
    request: Request,
    htmx: IsHTMX,
    league_id: str,
    db: DB,
    user: User,
    gm: GM,
):
    ctx = _shell_ctx(request, db, gm, league_id, "draft", user)

    draft_repo = DraftRepository(db)
    draft = draft_repo.get_current_for_league(league_id)
    player_repo = PlayerRepository(db)

    if draft:
        picked_ids = draft_repo.get_picked_ids(draft["id"])
        all_players = draft_repo.get_prospects(league_id)

        board = []
        for row in all_players:
            if row["id"] in picked_ids:
                continue
            board.append(prospect_card(row, player_repo.get_player_skills(row["id"])))

        prefs = draft_repo.get_preferences(draft["id"], gm["id"]) if gm else []

        pick_position = None
        if gm["team_id"]:
            pick_position = draft_repo.get_pick_position(draft["id"], gm["team_id"])

        ctx["draft_id"] = draft["id"]
        ctx["board"] = board
        ctx["preferences"] = prefs
        ctx["pick_position"] = pick_position
    else:
        ctx["draft_id"] = None
        ctx["board"] = []
        ctx["preferences"] = []
        ctx["pick_position"] = None

    # Load GM's current roster for the right-hand column
    players = []
    if gm["team_id"]:
        roster_rows = player_repo.get_team_roster_with_skills(gm["team_id"])
        for row in roster_rows:
            skills = player_repo.get_player_skills(row["id"])
            players.append(draft_roster_card(row, skills))
    ctx["players"] = players

    return tab_response(request, htmx, "dashboard/partials/draft.html", ctx)


@router.post("/leagues/{league_id}/draft/execute")
def execute_draft(
    request: Request,
    league_id: str,
    db: DB,
    gm: GM,
):
    """Execute the blitz auto-draft and redirect to results."""
    draft = DraftRepository(db).get_current_for_league(league_id)

    if not draft:
        return RedirectResponse(f"/leagues/{league_id}/draft", status_code=302)

    # If already complete, just go to results
    if draft["state"] == "complete":
        return RedirectResponse(f"/leagues/{league_id}/draft/results", status_code=302)

    execute_blitz_draft(draft["id"], db)
    db.commit()
    return RedirectResponse(f"/leagues/{league_id}/draft/results", status_code=302)


@router.get("/leagues/{league_id}/draft/results", response_class=HTMLResponse)
def draft_results(
    request: Request,
    htmx: IsHTMX,
    league_id: str,
    db: DB,
    user: User,
    gm: GM,
):
    """Show completed draft results — all picks by round, your picks highlighted."""
    ctx = _shell_ctx(request, db, gm, league_id, "draft", user)

    draft_repo = DraftRepository(db)
    draft = draft_repo.get_current_for_league(league_id)

    rounds = []
    my_team_id = gm["team_id"]

    if draft:
        picks = draft_repo.get_picks_with_details(draft["id"])

        gm_repo = GMRepository(db)
        human_team_ids = gm_repo.get_human_team_ids(league_id)

        # Group by round
        rounds_map = {}
        for pick in picks:
            r = pick["round"]
            if r not in rounds_map:
                rounds_map[r] = []
            is_mine = pick["team_id"] == my_team_id
            is_human = pick["team_id"] in human_team_ids and not is_mine
            rounds_map[r].append(
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
        rounds = [
            {"round": r, "picks": picks} for r, picks in sorted(rounds_map.items())
        ]

    ctx["rounds"] = rounds
    ctx["draft_done"] = bool(draft and draft["state"] == "complete")
    return tab_response(request, htmx, "dashboard/partials/draft_results.html", ctx)
