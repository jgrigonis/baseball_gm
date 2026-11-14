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
                ("Traditional", "Analytics", "Speed-first", "Power-first", "Defensive"),
                ("Traditional", "Defensive"),
                "How Fill, Rebuild and the AI build your lineup. Every style "
                "leads off with your best on-base hitter. Traditional bats the best "
                "hitter 3rd; Analytics bats him 2nd; Speed-first plays faster bats "
                "and puts speed 2nd and 9th; Power-first plays bigger bats and "
                "stacks power 3rd through 5th. Defensive plays "
                "the best gloves, above all at C, 2B, SS and CF, even when that "
                "costs some bat, then bats them in the Traditional order. The "
                "Lineup tab's Rebuild All menu (▾) rebuilds with any style so you "
                "can compare.",
            ),
            Setting(
                "lineup_updates",
                "Lineup Updates",
                mp.LINEUP_UPDATES,
                ("Keep mine", "Rebuild daily"),
                ("Keep mine", "Rebuild daily"),
                "Keep mine plays the batting orders you saved (vs RHP and vs "
                "LHP) game after game; holes from injuries are filled for the "
                "day. Rebuild daily redoes and saves both before every game, "
                "the way the Lineup tab's Rebuild does, so they follow hot "
                "and cold bats, injuries and rust. A player only loses his "
                "spot, changes position or moves in the order when the change "
                "is clearly better, so the lineup doesn't flip on near ties. "
                "With Rebuild daily on, the Injury Lineup setting isn't "
                "needed: every game is a rebuild.",
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
                ("Never", "vs Handedness", "Aggressive"),
                ("Set lineup", "Always split"),
                "How much the lineup changes with the other team's starter. A "
                "hitter facing a pitcher who throws from his side hits worse. "
                "The Never setting will play the lineup every game. vs Handedness "
                "benches a "
                "regular only for a bench player who's close to him and has the "
                "better matchup. Aggressive plays the best matchup lineup. Used "
                "by Fill, Rebuild and the AI, and to fill gaps in your "
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
                "ratings when Fill, Rebuild and the AI pick who plays. Stats "
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
                ("115", "105", "95", "85", "75"),
                ("Long leash", "Short leash"),
                "The pitch count a starter is usually pulled at on a normal "
                "day; 85 is standard. One who's getting hit can come out "
                "sooner, and at 75 he's pulled sooner the third time through "
                "the order. A starter can have his own on the Lineup tab's "
                "rotation.",
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
                ("Starter-heavy", "Balanced", "Deep pen"),
                ("Ride the starter", "Use the pen"),
                "How you handle trouble and use relievers. Starter-heavy lets a "
                "starter pitch through a rough inning and finish a few more "
                "batters at his pitch count, and relievers often go two innings. "
                "Deep pen pulls a struggling starter early and uses more "
                "relievers for about an inning each.",
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
                "How many starters Fill and Rebuild put in your rotation on the Lineup "
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


@dataclass(frozen=True)
class Checkbox:
    name: str  # gm_profiles column, a boolean
    label: str
    hint: str


# Settings shown in a checkbox panel, above its checkboxes, by panel title.
PANEL_SETTINGS: dict[str, tuple[Setting, ...]] = {
    "Injuries": (
        Setting(
            "injury_lineup",
            "Injury Lineup",
            mp.INJURY_LINEUP,
            (
                "Always auto-fill",
                *(
                    f"Auto-fill up to {d} day{'s' if d > 1 else ''}"
                    for d in mp.INJURY_FILL_DAYS
                ),
                "Always rebuild",
            ),
            ("Keep my lineup", "Rebuild it"),
            "What the coach does to your saved batting orders when a hitter is "
            "hurt during a sim. Auto-fill plays your lineup and puts someone in "
            "his slot for the day; he's back in it when he returns. Rebuild "
            "redoes both lineups (vs RHP and vs LHP) the way the Lineup tab's "
            "Rebuild does and saves them: when he goes out, when he's back in "
            "the lineup, and when his rust wears off. In between, outs up to "
            "that many days are auto-filled and longer ones rebuild. Days out "
            "is the injury's length; with Rest rusty players on, the days he "
            "sits out rust count too (rust fades twice as fast while he sits, "
            "so a 1-day injury with 4 days of rust is a 3-day out). Pitchers "
            "aren't changed: a hurt starter's turn goes to the next healthy one.",
        ),
    ),
}


# Checkbox panels: (title, checkboxes). A box left unticked isn't posted, so
# the save reads each one as on when it's in the form and off when it isn't.
CHECKBOXES: tuple[tuple[str, tuple[Checkbox, ...]], ...] = (
    (
        "Injuries",
        (
            Checkbox(
                "rest_rusty",
                "Rest rusty players",
                "A player back from an injury is rusty for a while: a few "
                "ratings are down until it fades. When this is on he sits "
                "until it's gone. Rebuild and Fill leave him out of the "
                "lineup and rotation, the bullpen gives him no role, and on "
                "game day he's out like an injured player. Rust fades twice as "
                "fast on days he doesn't play. Off plays him through it.",
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


def _slider(s: Setting, current: dict) -> dict:
    return {
        "name": s.name,
        "label": s.label,
        "labels": s.labels,
        "ends": s.ends,
        "hint": s.hint,
        "index": _index(s.values, current[s.name]),
    }


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
        (title, [_slider(s, current) for s in settings]) for title, settings in SETTINGS
    ]
    ctx["checkbox_cards"] = [
        (
            title,
            [
                {
                    "name": c.name,
                    "label": c.label,
                    "hint": c.hint,
                    "checked": bool(current[c.name]),
                }
                for c in boxes
            ],
            [_slider(s, current) for s in PANEL_SETTINGS.get(title, ())],
        )
        for title, boxes in CHECKBOXES
    ]
    # Unsaved slider moves are kept in the browser under this key, so they
    # survive a look at another tab.
    ctx["draft_key"] = f"strategy_draft_{league_id}_{gm['id'] if gm else 'none'}"
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
    all_settings = [*SETTINGS, *PANEL_SETTINGS.items()]
    for _, settings in all_settings:
        for s in settings:
            if s.name in form:
                try:
                    i = int(form[s.name])
                except ValueError:
                    continue
                updates[s.name] = s.values[max(0, min(i, len(s.values) - 1))]
    for _, boxes in CHECKBOXES:
        for c in boxes:
            updates[c.name] = c.name in form

    repo = GMRepository(db)
    saved = repo.get_profile(gm["id"]) or {}
    if "injury_lineup" in updates and updates["injury_lineup"] != saved.get(
        "injury_lineup"
    ):
        # A new Injury Lineup step starts fresh: the next game notes who's
        # out, and only a change after that rebuilds (src/league/injury_lineup.py).
        updates["injury_lineup_key"] = None
    if updates:
        repo.save_profile(gm["id"], updates)
        db.commit()
    # Shown as a toast (gmToast in dialogs.js).
    return HTMLResponse(
        '<span hidden data-toast="✓ Strategy saved" data-toast-kind="ok"></span>'
    )
