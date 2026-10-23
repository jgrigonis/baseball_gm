# src/api/routers/strategy.py
#
# Strategy tab: the GM's managerial tendencies.

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from src.api.dependencies import DB, GM, IsHTMX, User
from src.db.repositories.gm_repo import GMRepository
from src.web.utils import _shell_ctx, tab_response

router = APIRouter(tags=["web"])


@router.get("/leagues/{league_id}/strategy", response_class=HTMLResponse)
def strategy(
    request: Request,
    htmx: IsHTMX,
    league_id: str,
    db: DB,
    user: User,
    gm: GM,
):
    ctx = _shell_ctx(request, db, gm, league_id, "strategy", user)

    profile_row = GMRepository(db).get_profile(gm["id"])

    _L = ["traditional", "analytics", "speed-first", "power-first"]
    _S = ["conservative", "standard", "aggressive"]
    _B = ["never", "situational", "frequent"]
    _P = ["none", "vs-handedness", "aggressive"]
    _U = ["let-them-work", "pitch-count-strict", "matchup-based"]
    _C = ["saves-only", "high-leverage", "best-available"]
    _N = ["deep-pen", "starter-heavy"]

    def idx(lst, val, default=0):
        try:
            return lst.index(val)
        except ValueError:
            return default

    if profile_row:
        p = profile_row
        ctx["profile"] = {
            "lineup_style_index": idx(_L, p.get("lineup_style", "analytics"), 1),
            "steal_aggression_index": idx(_S, p.get("steal_aggression", "standard"), 1),
            "sac_bunt_index": idx(_B, p.get("sac_bunt", "situational"), 1),
            "platoon_usage_index": idx(_P, p.get("platoon_usage", "none"), 0),
            "starter_usage_index": idx(
                _U, p.get("starter_usage", "pitch-count-strict"), 1
            ),
            "closer_usage_index": idx(_C, p.get("closer_usage", "saves-only"), 0),
            "bullpen_pref_index": idx(_N, p.get("bullpen_pref", "deep-pen"), 0),
        }
    else:
        ctx["profile"] = {
            "lineup_style_index": 1,
            "steal_aggression_index": 1,
            "sac_bunt_index": 1,
            "platoon_usage_index": 0,
            "starter_usage_index": 1,
            "closer_usage_index": 0,
            "bullpen_pref_index": 0,
        }

    return tab_response(request, htmx, "dashboard/partials/strategy.html", ctx)


@router.post("/leagues/{league_id}/strategy")
async def save_strategy(
    request: Request,
    league_id: str,
    db: DB,
    gm: GM,
):
    if not gm:
        return HTMLResponse("Not a member of this league", status_code=403)

    form = await request.form()
    _MAPS = {
        "lineup_style": ["traditional", "analytics", "speed-first", "power-first"],
        "steal_aggression": ["conservative", "standard", "aggressive"],
        "sac_bunt": ["never", "situational", "frequent"],
        "platoon_usage": ["none", "vs-handedness", "aggressive"],
        "starter_usage": ["let-them-work", "pitch-count-strict", "matchup-based"],
        "closer_usage": ["saves-only", "high-leverage", "best-available"],
        "bullpen_pref": ["deep-pen", "starter-heavy"],
    }
    updates = {}
    for field, options in _MAPS.items():
        i = int(form.get(field, 0))
        updates[field] = options[min(i, len(options) - 1)]

    GMRepository(db).save_profile(gm["id"], updates)
    db.commit()
    return HTMLResponse(
        '<span style="color:var(--green);font-family:var(--font-mono);font-size:11px;">✓ Saved</span>'
    )
