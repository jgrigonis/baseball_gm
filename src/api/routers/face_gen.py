# src/api/routers/face_gen.py
#
# /face_gen/: build a player face by hand (src/player/face.py). Every trait
# has a control; the preview redraws on each change, and the page shows the
# traits as the small JSON a stored face would be. Nothing links here yet.

from __future__ import annotations

import json
import secrets

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from src.player.face import (
    TRAITS_BY_KEY,
    clean_traits,
    default_traits,
    face_svg,
    random_traits,
)
from src.team.colors import TEAM_COLORS
from src.web.utils import templates

router = APIRouter(tags=["web"])

# The controls, grouped as on the page
GROUPS = (
    ("Skin & hair", ("skin", "hair", "long_hair", "sideburns", "gray_rate")),
    ("Head", ("face_width", "face_length", "chin", "ears", "neck")),
    (
        "Eyes",
        ("eyes", "eye_spacing", "eye_height", "eye_width", "eye_open", "eye_black"),
    ),
    ("Brows", ("brow_thickness", "brow_tilt", "brow_gap")),
    ("Nose & mouth", ("nose_width", "nose_length", "mouth", "mouth_width", "lips")),
    ("Facial hair", ("facial_hair",)),
    ("Mole", ("mole", "mole_x", "mole_y")),
)
PREVIEW_AGES = (22, 30, 38)


def _team(value: str) -> tuple[str | None, str | None]:
    """ "London|Lions" -> ("London", "Lions"); anything else is a free agent."""
    city, _, mascot = (value or "").partition("|")
    if (city, mascot) in TEAM_COLORS:
        return city, mascot
    return None, None


def _traits(raw: str) -> dict:
    try:
        data = json.loads(raw or "{}")
    except ValueError:
        data = {}
    return clean_traits(data if isinstance(data, dict) else {})


@router.get("/face_gen/", response_class=HTMLResponse)
def face_gen(request: Request):
    groups = [
        {"title": title, "traits": [TRAITS_BY_KEY[k] for k in keys]}
        for title, keys in GROUPS
    ]
    teams = sorted(TEAM_COLORS)
    start = random_traits(secrets.token_hex(4))
    return templates.TemplateResponse(
        request,
        "face_gen.html",
        {
            "groups": groups,
            "teams": teams,
            "start": start,
            "defaults": default_traits(),
        },
    )


@router.get("/face_gen/svg")
def face_gen_svg(
    traits: str = Query(default="{}"),
    age: int = Query(default=27, ge=16, le=50),
    team: str = Query(default=""),
):
    """The face drawn from the page's traits, plus the same face at a few
    ages, and the cleaned traits as they'd be stored."""
    t = _traits(traits)
    city, mascot = _team(team)
    stored = json.dumps(t, separators=(",", ":"))
    return JSONResponse(
        {
            "svg": face_svg("", age, city, mascot, t),
            "ages": [
                {"age": a, "svg": face_svg("", a, city, mascot, t)}
                for a in PREVIEW_AGES
            ],
            "traits": t,
            "stored": stored,
            "bytes": len(stored.encode()),
        }
    )


@router.get("/face_gen/random")
def face_gen_random(seed: str = Query(default="")):
    """Random traits: the face a player with this id gets, or a fresh one."""
    return JSONResponse(random_traits(seed or secrets.token_hex(4)))
