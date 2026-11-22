# src/api/routers/custom_players.py
#
# /my-players/: the player creator (services/custom_players.py). Paid
# contributors and admins make their own players and edit them; My Teams
# lists them and a custom team can add them next to real player-seasons.
#
# The creator page edits the player in the browser and saves him as JSON.
# A wide screen walks through steps with rating sliders; a phone gets the
# same steps as tabs with rating tiles (Josh, 2026-11-22: "B + C").

from __future__ import annotations

import random
from urllib.parse import quote

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from src.api.dependencies import DB, User
from src.api.services import custom_players as cp
from src.api.services import custom_teams as ct
from src.db.repositories.custom_player_repo import CustomPlayerRepository
from src.db.repositories.custom_team_repo import CustomTeamRepository
from src.web.utils import templates

router = APIRouter(tags=["web"])


def _refused(request: Request, user, message: str, status_code: int = 403):
    return templates.TemplateResponse(
        request,
        "error.html",
        {"user": user, "status_code": status_code, "message": message},
        status_code=status_code,
    )


def _own_team(db, user, team_id: str) -> dict | None:
    return ct.owned(CustomTeamRepository(db), user, team_id) if team_id else None


def _page(request, db, user, player: dict, made_id: str | None, team: dict | None):
    teams = [
        {"id": t["id"], "name": t["name"], "size": len(t["players"])}
        for t in CustomTeamRepository(db).list_for(user["id"])
    ]
    on_teams = []
    if made_id:
        key = ct.made_key(made_id)
        on_teams = [
            t["name"]
            for t in CustomTeamRepository(db).list_for(user["id"])
            if any(e["key"] == key for e in t["players"])
        ]
    return templates.TemplateResponse(
        request,
        "custom_players/edit.html",
        {
            "user": user,
            "player": cp.snapshot(player),
            "face_svg": cp.face_svg(player),
            "made_id": made_id,
            "team": team,
            "teams": teams,
            "on_teams": on_teams,
            "roster_max": ct.ROSTER_MAX,
            "config": cp.creator_config(),
        },
    )


@router.get("/my-players/new", response_class=HTMLResponse)
def new_player(request: Request, db: DB, user: User, pos: str = "", team: str = ""):
    if not cp.can_build(user):
        return _refused(request, user, "Making players is for paid contributors.")
    player = cp.roll(position=pos or None)
    return _page(request, db, user, player, None, _own_team(db, user, team))


@router.get("/my-players/roll")
def roll_player(user: User, pos: str = "", age: int = 0):
    """A random player for the creator's 🎲 New player (JSON)."""
    if not cp.can_build(user):
        return JSONResponse({"error": "Making players is for paid contributors."}, 403)
    return JSONResponse(cp.roll(position=pos or None, age=age or None))


@router.get("/my-players/name")
def roll_name(user: User):
    """A random name for the creator's 🎲 by the name (JSON)."""
    if not cp.can_build(user):
        return JSONResponse({"error": "Making players is for paid contributors."}, 403)
    return JSONResponse(cp.random_name(random.Random()))


@router.get("/my-players/{player_id}", response_class=HTMLResponse)
def edit_player(request: Request, player_id: str, db: DB, user: User, team: str = ""):
    if not cp.can_build(user):
        return _refused(request, user, "Making players is for paid contributors.")
    row = CustomPlayerRepository(db).get(player_id)
    if not row or row["owner_id"] != user["id"]:
        return _refused(request, user, "There's no such player.", 404)
    return _page(request, db, user, row, row["id"], _own_team(db, user, team))


async def _body(request: Request) -> dict:
    try:
        body = await request.json()
    except ValueError:
        body = None
    return body if isinstance(body, dict) else {}


def _saved(db, user, made_id: str, team_id: str, added: bool) -> JSONResponse:
    url = f"/teams/{team_id}#roster" if team_id else "/teams/#my-players"
    return JSONResponse({"ok": True, "id": made_id, "url": url, "added": added})


@router.post("/my-players/")
async def create_player(request: Request, db: DB, user: User):
    """Save a new player; with a team, put him on it too (JSON)."""
    if not cp.can_build(user):
        return JSONResponse({"error": "Making players is for paid contributors."}, 403)
    body = await _body(request)
    try:
        player = cp.clean(body.get("player"))
    except cp.CustomPlayerError as e:
        return JSONResponse({"error": str(e)}, 400)
    repo = CustomPlayerRepository(db)
    made_id = repo.create(user["id"], player)
    team = _own_team(db, user, str(body.get("team") or ""))
    added = False
    if team:
        try:
            ct.add_made(CustomTeamRepository(db), team, repo.get(made_id))
            added = True
        except ct.CustomTeamError as e:
            db.commit()  # he's saved; he just didn't fit on the team
            return JSONResponse(
                {
                    "ok": True,
                    "id": made_id,
                    "url": "/teams/#my-players",
                    "warning": str(e),
                }
            )
    db.commit()
    return _saved(db, user, made_id, team["id"] if team else "", added)


@router.post("/my-players/{player_id}")
async def save_player(request: Request, player_id: str, db: DB, user: User):
    """Save changes to one of the user's players (JSON)."""
    if not cp.can_build(user):
        return JSONResponse({"error": "Making players is for paid contributors."}, 403)
    repo = CustomPlayerRepository(db)
    row = repo.get(player_id)
    if not row or row["owner_id"] != user["id"]:
        return JSONResponse({"error": "There's no such player."}, 404)
    body = await _body(request)
    try:
        player = cp.clean(body.get("player"))
    except cp.CustomPlayerError as e:
        return JSONResponse({"error": str(e)}, 400)
    repo.update(player_id, player)
    team = _own_team(db, user, str(body.get("team") or ""))
    db.commit()
    return _saved(db, user, player_id, team["id"] if team else "", False)


@router.post("/my-players/{player_id}/delete")
def delete_player(request: Request, player_id: str, db: DB, user: User):
    repo = CustomPlayerRepository(db)
    row = repo.get(player_id)
    if not row or row["owner_id"] != user["id"]:
        return _refused(request, user, "There's no such player.", 404)
    ct.drop_made(CustomTeamRepository(db), user["id"], player_id)
    repo.delete(player_id)
    db.commit()
    return RedirectResponse("/teams/#my-players", status_code=303)


@router.post("/teams/{team_id}/add-made")
def add_made(
    request: Request,
    team_id: str,
    db: DB,
    user: User,
    made_id: str = Form(...),
):
    """Put one of the user's made-up players on one of their teams."""
    team = _own_team(db, user, team_id)
    if not team:
        return _refused(request, user, "There's no such team.", 404)
    row = CustomPlayerRepository(db).get(made_id)
    if not row or row["owner_id"] != user["id"]:
        return _refused(request, user, "There's no such player.", 404)
    try:
        ct.add_made(CustomTeamRepository(db), team, row)
    except ct.CustomTeamError as e:
        db.rollback()
        return RedirectResponse(
            f"/teams/{team_id}?made_error={quote(str(e))}#my-players-add",
            status_code=303,
        )
    db.commit()
    return RedirectResponse(f"/teams/{team_id}#my-players-add", status_code=303)
