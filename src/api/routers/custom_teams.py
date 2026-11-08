# src/api/routers/custom_teams.py
#
# /teams/: My Teams, custom teams of real player-seasons
# (services/custom_teams.py). Building one, or saving a copy of someone
# else's, is for paid contributors and admins; anyone signed in can open a
# shared team's code and look at it.

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from src.api.dependencies import DB, IsHTMX, User
from src.api.services import custom_teams as ct
from src.config import settings
from src.db.repositories.custom_team_repo import CustomTeamRepository
from src.league.real_seasons import SKILLS, players
from src.web.utils import templates

router = APIRouter(tags=["web"])

SEARCH_LIMIT = 40


def _ctx(user, **extra) -> dict:
    return {
        "user": user,
        "can_build": ct.can_build(user),
        "skills": SKILLS,
        "abbr": ct.SKILL_ABBR,
        "hitter_skills": ct.HITTER_SKILLS,
        "pitcher_skills": ct.PITCHER_SKILLS,
        **extra,
    }


def _not_found(request: Request, user, message: str = "There's no such team."):
    return templates.TemplateResponse(
        request,
        "error.html",
        {"user": user, "status_code": 404, "message": message},
        status_code=404,
    )


def _search(q: str) -> dict:
    found, total = players.search(q, limit=SEARCH_LIMIT) if q.strip() else ([], 0)
    return {
        "q": q,
        "results": [ct.describe(s) for s in found],
        "total": total,
        "limit": SEARCH_LIMIT,
    }


def _back(team_id: str, q: str = "", anchor: str = "") -> RedirectResponse:
    url = f"/teams/{team_id}"
    if q:
        url += f"?q={quote(q)}"
    return RedirectResponse(url + anchor, status_code=303)


# ── My Teams ───────────────────────────────────────────────────────────


@router.get("/teams/", response_class=HTMLResponse)
def my_teams(request: Request, db: DB, user: User, error: str = ""):
    teams = CustomTeamRepository(db).list_for(user["id"])
    for t in teams:
        t["summary"] = ct.summary(ct.roster(t))
    return templates.TemplateResponse(
        request,
        "custom_teams/index.html",
        _ctx(user, teams=teams, error=error, name_max=ct.NAME_MAX),
    )


@router.post("/teams/")
def create_team(request: Request, db: DB, user: User, name: str = Form("")):
    try:
        team_id = ct.create(CustomTeamRepository(db), user, name)
    except ct.CustomTeamError as e:
        return RedirectResponse(f"/teams/?error={quote(str(e))}", status_code=303)
    db.commit()
    return RedirectResponse(f"/teams/{team_id}", status_code=303)


@router.post("/teams/open")
def open_code(code: str = Form("")):
    """The "Open a shared team" box on My Teams."""
    code = ct.normalize_code(code)
    if not code:
        return RedirectResponse("/teams/", status_code=303)
    return RedirectResponse(f"/teams/shared/{code}", status_code=303)


# ── Shared teams ───────────────────────────────────────────────────────


@router.get("/teams/shared/{code}", response_class=HTMLResponse)
def shared_team(request: Request, code: str, db: DB, user: User):
    team = CustomTeamRepository(db).get_by_code(ct.normalize_code(code))
    if not team:
        return _not_found(request, user, "No team has that share code.")
    rows = ct.roster(team)
    return templates.TemplateResponse(
        request,
        "custom_teams/shared.html",
        _ctx(
            user,
            team=team,
            rows=rows,
            summary=ct.summary(rows),
            mine=team["owner_id"] == user["id"],
        ),
    )


@router.post("/teams/shared/{code}/copy")
def copy_shared(request: Request, code: str, db: DB, user: User):
    repo = CustomTeamRepository(db)
    team = repo.get_by_code(ct.normalize_code(code))
    if not team:
        return _not_found(request, user, "No team has that share code.")
    try:
        team_id = ct.save_copy(repo, user, team)
    except ct.CustomTeamError as e:
        return RedirectResponse(f"/teams/?error={quote(str(e))}", status_code=303)
    db.commit()
    return RedirectResponse(f"/teams/{team_id}", status_code=303)


# ── One of your teams ──────────────────────────────────────────────────


def _team_page(request, user, team, q="", error="", status_code=200):
    rows = ct.roster(team)
    on_team = {r["key"] for r in rows}
    search = _search(q)
    for r in search["results"]:
        r["on_team"] = r["key"] in on_team
    return templates.TemplateResponse(
        request,
        "custom_teams/team.html",
        _ctx(
            user,
            team=team,
            rows=rows,
            summary=ct.summary(rows),
            error=error,
            name_max=ct.NAME_MAX,
            share_url=(settings.public_base_url or str(request.base_url)).rstrip("/")
            + f"/teams/shared/{team['share_code']}",
            **search,
        ),
        status_code=status_code,
    )


@router.get("/teams/{team_id}", response_class=HTMLResponse)
def team_page(request: Request, team_id: str, db: DB, user: User, q: str = ""):
    team = ct.owned(CustomTeamRepository(db), user, team_id)
    if not team:
        return _not_found(request, user)
    return _team_page(request, user, team, q)


@router.get("/teams/{team_id}/search", response_class=HTMLResponse)
def team_search(
    request: Request, team_id: str, db: DB, user: User, htmx: IsHTMX, q: str = ""
):
    """Search results as you type (htmx); a plain load gets the whole page."""
    team = ct.owned(CustomTeamRepository(db), user, team_id)
    if not team:
        return _not_found(request, user)
    if not htmx:
        return _back(team_id, q)
    search = _search(q)
    on_team = {e["key"] for e in team["players"]}
    for r in search["results"]:
        r["on_team"] = r["key"] in on_team
    return templates.TemplateResponse(
        request,
        "custom_teams/_search.html",
        _ctx(user, team=team, full=len(team["players"]) >= ct.ROSTER_MAX, **search),
    )


def _change(request, db, user, team_id, q, change, anchor=""):
    """Run one change to the user's team, then back to the team page (or
    the page again with the reason it couldn't be done)."""
    repo = CustomTeamRepository(db)
    team = ct.owned(repo, user, team_id)
    if not team:
        return _not_found(request, user)
    try:
        change(repo, team)
    except ct.CustomTeamError as e:
        db.rollback()
        team = ct.owned(repo, user, team_id)
        return _team_page(request, user, team, q, str(e), 400)
    db.commit()
    return _back(team_id, q, anchor)


@router.post("/teams/{team_id}/add")
def add_player(
    request: Request,
    team_id: str,
    db: DB,
    user: User,
    key: str = Form(...),
    q: str = Form(""),
):
    return _change(
        request,
        db,
        user,
        team_id,
        q,
        lambda repo, team: ct.add_player(repo, team, key),
        "#search",
    )


@router.post("/teams/{team_id}/remove")
def remove_player(
    request: Request,
    team_id: str,
    db: DB,
    user: User,
    slot: int = Form(...),
    q: str = Form(""),
):
    return _change(
        request,
        db,
        user,
        team_id,
        q,
        lambda repo, team: ct.remove_player(repo, team, slot),
        "#roster",
    )


@router.post("/teams/{team_id}/rename")
def rename_team(
    request: Request, team_id: str, db: DB, user: User, name: str = Form("")
):
    def change(repo, team):
        repo.rename(team["id"], ct.clean_name(name))

    return _change(request, db, user, team_id, "", change)


@router.post("/teams/{team_id}/delete")
def delete_team(request: Request, team_id: str, db: DB, user: User):
    repo = CustomTeamRepository(db)
    team = ct.owned(repo, user, team_id)
    if not team:
        return _not_found(request, user)
    repo.delete(team_id)
    db.commit()
    return RedirectResponse("/teams/", status_code=303)


# ── Editing a player's skills ──────────────────────────────────────────


def _player_page(request, user, team, slot, error="", values=None, status_code=200):
    rows = [r for r in ct.roster(team) if r["slot"] == slot]
    if not rows:
        return _not_found(request, user, "That player isn't on the team.")
    return templates.TemplateResponse(
        request,
        "custom_teams/player.html",
        _ctx(user, team=team, p=rows[0], error=error, values=values),
        status_code=status_code,
    )


@router.get("/teams/{team_id}/players/{slot}", response_class=HTMLResponse)
def player_page(request: Request, team_id: str, slot: int, db: DB, user: User):
    team = ct.owned(CustomTeamRepository(db), user, team_id)
    if not team:
        return _not_found(request, user)
    return _player_page(request, user, team, slot)


@router.post("/teams/{team_id}/players/{slot}")
async def save_player(request: Request, team_id: str, slot: int, db: DB, user: User):
    repo = CustomTeamRepository(db)
    team = ct.owned(repo, user, team_id)
    if not team:
        return _not_found(request, user)
    form = await request.form()
    values = {s: str(form.get(s, "")) for s in SKILLS}
    try:
        ct.edit_skills(repo, team, slot, values)
    except ct.CustomTeamError as e:
        db.rollback()
        return _player_page(request, user, team, slot, str(e), values, 400)
    db.commit()
    return RedirectResponse(f"/teams/{team_id}#slot-{slot}", status_code=303)


@router.post("/teams/{team_id}/players/{slot}/reset")
def reset_player(request: Request, team_id: str, slot: int, db: DB, user: User):
    return _change(
        request,
        db,
        user,
        team_id,
        "",
        lambda repo, team: ct.reset_skills(repo, team, slot),
        f"#slot-{slot}",
    )
