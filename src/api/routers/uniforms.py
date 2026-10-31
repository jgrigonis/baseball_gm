# src/api/routers/uniforms.py
#
# /team_uniforms/: every team's uniform set on one page, the same pieces the
# Meet your team screen shows (view_models/welcome.uniforms) plus the helmet.
# Nothing links here; it's for looking the sets over side by side.

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from src.api.services.lobby_teams import EXTRA_TEAMS, manifest_teams
from src.api.view_models.welcome import UNIFORMS_DIR, uniform_slug, uniforms
from src.team.colors import colors_for
from src.web.utils import templates

router = APIRouter(tags=["web"])


def all_team_uniforms() -> list[dict]:
    """Every World League team and the extra 32-team-league teams, by city,
    each with its uniform pieces (None for a team without a set)."""
    teams = list(manifest_teams()) + [(t["city"], t["mascot"]) for t in EXTRA_TEAMS]
    rows = []
    for city, mascot in sorted(set(teams)):
        u = uniforms(city)
        slug = uniform_slug(city)
        if u and (UNIFORMS_DIR / slug / "helmet.svg").exists():
            u["helmet"] = f"img/uniforms/{slug}/helmet.svg"
        rows.append(
            {
                "city": city,
                "mascot": mascot,
                "primary": colors_for(city, mascot).primary,
                "uniforms": u,
            }
        )
    return rows


@router.get("/team_uniforms/", response_class=HTMLResponse)
def team_uniforms(request: Request):
    return templates.TemplateResponse(
        request, "team_uniforms.html", {"teams": all_team_uniforms()}
    )
