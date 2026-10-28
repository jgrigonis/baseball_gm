# src/api/routers/strategy.py
#
# Strategy tab: the GM's managerial tendencies, stored in gm_profiles and read
# by the game engine every game (src/team/manager_profile.py). Each setting is
# a slider; SETTINGS below drives both the page and the save.

from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from src.api.dependencies import DB, GM, ActiveLeague, IsHTMX, User
from src.db.repositories.gm_repo import GMRepository
from src.team import manager_profile as mp
from src.web.utils import _shell_ctx, tab_response

router = APIRouter(tags=["web"])


@dataclass(frozen=True)
class Setting:
    name: str  # gm_profiles column
    label: str
    values: tuple  # stored values, in slider order
    labels: tuple[str, ...]  # what the slider shows for each
    ends: tuple[str, str]
    hint: str


SETTINGS: tuple[tuple[str, tuple[Setting, ...]], ...] = (
    (
        "Batting",
        (
            Setting(
                "lineup_style",
                "Lineup Construction",
                mp.LINEUP_STYLE,
                ("Traditional", "Analytics", "Speed-first", "Power-first"),
                ("Traditional", "Power-first"),
                "How Auto-fill, Rebuild and the AI order your lineup. Traditional "
                "leads off with speed and bats the best hitter 3rd; Analytics leads "
                "off with on-base and bats the best hitter 2nd.",
            ),
            Setting(
                "baserunning",
                "Baserunning",
                mp.BASERUNNING,
                (
                    "Very conservative",
                    "Conservative",
                    "Standard",
                    "Aggressive",
                    "Very aggressive",
                ),
                ("Station to station", "Run wild"),
                "How often runners steal and hit and run, and how often they try "
                "for the extra base on a hit. Aggressive runners take more bases, "
                "and some of the extra tries are thrown out.",
            ),
            Setting(
                "sac_bunt",
                "Sacrifice Bunt Usage",
                mp.SAC_BUNT,
                ("Never", "Situational", "Frequent"),
                ("Never bunt", "Bunt often"),
                "How often the manager calls a sacrifice bunt with a runner on and "
                "fewer than two outs. Frequent bunts about twice as often.",
            ),
            Setting(
                "rest_days",
                "Rest Days",
                mp.REST_DAYS,
                ("Iron man", "Standard", "Rest often"),
                ("Play every day", "Rest often"),
                "When a tired regular gets the day off. Standard sits a hitter "
                "below 40% energy, Rest often below 60%, and catchers a little "
                "sooner. Iron man never rests anyone: a tired player just plays "
                "worse.",
            ),
        ),
    ),
    (
        "Platoon",
        (
            Setting(
                "platoon_usage",
                "Platoon Usage",
                mp.PLATOON_USAGE,
                ("None", "vs Handedness", "Aggressive"),
                ("Set lineup", "Always split"),
                "How much the lineup changes with the other team's starter. A "
                "hitter facing a pitcher who throws from his side hits worse. "
                "None plays the same lineup every day. vs Handedness benches a "
                "regular only for a bench player who's close to him and has the "
                "better matchup. Aggressive plays the best matchup lineup. Used "
                "by Auto-fill, Rebuild and the AI, and to fill gaps in your "
                "saved lineups; a lineup you save is played as you set it.",
            ),
        ),
    ),
    (
        "Scouting",
        (
            Setting(
                "stats_vs_scouting",
                "Stats vs Scouting",
                mp.STATS_VS_SCOUTING,
                (
                    "Trust the scouts",
                    "Lean on the scouts",
                    "Both equally",
                    "Lean on the stats",
                    "Trust the stats",
                ),
                ("Ratings", "Results"),
                "How much a player's stats this season count against his "
                "ratings when Auto-fill, Rebuild and the AI pick who plays. Stats "
                "are regressed to the ratings by how much he's played, so a hot "
                "couple of weeks barely moves anyone.",
            ),
        ),
    ),
    (
        "Pitching",
        (
            Setting(
                "starter_usage",
                "Starter Leash",
                mp.STARTER_USAGE,
                ("Let them work", "Pitch-count strict", "Matchup-based"),
                ("Long leash", "Short leash"),
                "Let them work allows about 15 more pitches and pulls a starter "
                "less often. Pitch-count strict goes to the pen around 100 "
                "pitches. Matchup-based also pulls him sooner the third time "
                "through the order.",
            ),
            Setting(
                "closer_usage",
                "Closer Deployment",
                mp.CLOSER_USAGE,
                ("Saves only", "High-leverage", "Best available"),
                ("9th inning only", "Any big spot"),
                "Saves only brings the closer in for a save in the 9th. "
                "High-leverage also uses him in a tie or a 1-2 run lead from the "
                "8th on. Best available gives the save to the best rested reliever "
                "by closer rating, whatever his role.",
            ),
            Setting(
                "bullpen_pref",
                "Bullpen Shape",
                mp.BULLPEN_PREF,
                ("Deep pen", "Starter-heavy"),
                ("Use the pen", "Ride the starter"),
                "Starter-heavy keeps starters in a little longer; Deep pen goes "
                "to the bullpen sooner.",
            ),
        ),
    ),
    (
        "Rotation",
        (
            Setting(
                "rotation_size",
                "Rotation Size",
                mp.ROTATION_SIZE,
                ("4-man", "5-man", "6-man"),
                ("4", "6"),
                "How many starters Auto-fill puts in your rotation on the Lineup "
                "tab. Whoever is in your saved rotation is who pitches.",
            ),
            Setting(
                "skip_fifth_starter",
                "Skip the 5th Starter",
                (False, True),
                ("Off", "On"),
                ("Off", "On"),
                "After an off day, skip the last starter in a rotation of five or "
                "more, so your ace pitches again on normal rest.",
            ),
            Setting(
                "playoff_rotation",
                "Playoff Rotation",
                mp.PLAYOFF_ROTATION,
                ("3-man", "4-man", "Same as season"),
                ("Short", "Full"),
                "Shortens the rotation in the playoffs to your top starters.",
            ),
            Setting(
                "tired_starters",
                "Tired Starters",
                mp.TIRED_STARTERS,
                ("Push through", "Standard", "Protect"),
                ("Push", "Protect"),
                "How rested a scheduled starter must be. Push starts him at 75% "
                "energy, Standard at 83%, Protect at 90%; otherwise the next "
                "rested starter takes the game.",
            ),
        ),
    ),
)


def _index(values: tuple, current) -> int:
    """The slider step for a stored value: the closest one for a number
    between steps."""
    if current in values:
        return values.index(current)
    return min(range(len(values)), key=lambda i: abs(values[i] - current))


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

    row = GMRepository(db).get_profile(gm["id"]) if gm else None
    current = vars(mp.ManagerProfile.from_row(row))
    ctx["cards"] = [
        (
            title,
            [
                {
                    "name": s.name,
                    "label": s.label,
                    "labels": s.labels,
                    "ends": s.ends,
                    "hint": s.hint,
                    "index": _index(s.values, current[s.name]),
                }
                for s in settings
            ],
        )
        for title, settings in SETTINGS
    ]
    return tab_response(request, htmx, "dashboard/partials/strategy.html", ctx)


@router.post("/leagues/{league_id}/strategy")
async def save_strategy(
    request: Request,
    league_id: str,
    db: DB,
    gm: GM,
    _active: ActiveLeague,
):
    if not gm:
        return HTMLResponse("Not a member of this league", status_code=403)

    form = await request.form()
    updates = {}
    for _, settings in SETTINGS:
        for s in settings:
            if s.name in form:
                try:
                    i = int(form[s.name])
                except ValueError:
                    continue
                updates[s.name] = s.values[max(0, min(i, len(s.values) - 1))]

    if updates:
        GMRepository(db).save_profile(gm["id"], updates)
        db.commit()
    return HTMLResponse(
        '<span style="color:var(--green);font-family:var(--font-mono);font-size:11px;">✓ Saved</span>'
    )
