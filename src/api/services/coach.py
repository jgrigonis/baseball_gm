# src/api/services/coach.py
#
# The coach panel in a tutorial league: a checklist that walks a new GM from
# the lobby through their first season and offseason, one step at a time.
#
# Some steps the league's own state answers (the draft has run, the playoffs
# are over). The rest are things only the GM's clicks show, like saving a
# lineup or opening the Stats tab; those are recorded in leagues.coach_done
# by mark() as the GM does them.

from __future__ import annotations

from src.api.services import all_star
from src.db.repositories.all_star_repo import AllStarRepository
from src.db.repositories.gm_repo import GMRepository
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.season_repo import SeasonRepository
from src.league import hr_derby
from src.league.all_star import PITCHER_OUTS_CAP

# Tabs whose first visit counts toward a step. Explore needs all four.
EXPLORE_TABS = ("schedule", "standings", "stats", "leaders")
VISIT_STEPS = ("strategy", *EXPLORE_TABS)
# The lineup step needs all three of the Lineup tab's saves.
LINEUP_SAVES = ("batting", "rotation", "bullpen")
# The All-Star week steps, in order: the ballot, the captains' draft, and
# the break's games (the Rookie Game, the Home Run Derby and the All-Star
# Game, all played in the same sim).
ALL_STAR_STEPS = ("allstar_vote", "allstar_draft", "allstar_break")
# What a step's "Go to" button calls a tab, where its name isn't enough.
GO_LABELS = {"welcome": "Meet your team", "allstar": "All-Stars"}
# The draft step before the votes are counted.
WAIT_TEXT = (
    "Keep playing up to the break. After the last games before it the votes "
    "are counted, and the 64 All-Stars get a ★ by their names. The GMs of the "
    "two best teams are the captains, and they take turns drafting their "
    "sides from the 64."
)
# A captain's extra line on the All-Star draft step.
CAPTAIN_TEXT = (
    " Your team is one of the two best, so you're a captain: make your picks "
    "on the All-Star tab, or let the scouts make the rest for you."
)

# key, title, what to do, the tab it happens on (None: the page it's on)
STEPS = (
    (
        "start",
        "Start the league",
        "This is the lobby. The GM list shows you who is running each team. "
        "Hover or tap any setting's name to see what it does. Speed Blitz is the quick mode: no injuries or trades, and "
        "each sim period plays 30 days. Press Start League when you're ready.",
        None,
    ),
    (
        "welcome",
        "Meet your team",
        "This is the team you're taking over: its uniforms, how it did last "
        "season, a scouting report, your stars and your weak spots, your "
        "draft slot and your rivals. Click any player for more. The weak "
        "spots are what the draft can fix, so the Draft tab is next. You can "
        "come back here from the Roster tab, or by clicking your team's name "
        "at the top.",
        "welcome",
    ),
    (
        "prefs",
        "Set your draft strategy",
        "Your team's needs start out filled in from your roster, with the "
        "reason for each. Click a need to cycle through Low, Med and High, "
        "press ☆ on any prospect you really want, and set the age slider. Your first 5 "
        "projected picks on the right update as you go. Press Save Strategy "
        "when they look right.",
        "draft",
    ),
    (
        "draft",
        "Run the draft",
        "Press Run Draft. Each of your picks goes to your highest pinned "
        "player still there, else the best prospect for your needs. The AI "
        "picks for the other teams.",
        "draft",
    ),
    (
        "roster",
        "Save your roster",
        "The Roster tab shows everyone in your organization. Up to 40 of them "
        "fit on the 40-man roster, all of which are available to play in "
        "Blitz leagues. Make any changes, then save.",
        "roster",
    ),
    (
        "lineup",
        "Set your lineup",
        "On the Lineup tab, set the batting order, the rotation and the "
        "bullpen, and save each one (or press Save All Lineups). Your team "
        "plays them until you change them.",
        "lineup",
    ),
    (
        "strategy",
        "Look at Strategy",
        "Strategy sets how your manager plays: how often to steal and bunt, "
        "how long starters go, and how the bullpen is used.",
        "strategy",
    ),
    (
        "play",
        "Play some games",
        "Use the play buttons on Standings or Schedule tab. Play Day plays one "
        "day and Full Season plays to the end.",
        "standings",
    ),
    (
        "explore",
        "See how you're doing",
        "Schedule has every game and its box score, Standings has the races, "
        "and Stats and Leaders have the numbers. Open each one.",
        None,
    ),
    (
        "allstar_vote",
        "Vote for the All-Stars",
        "About two weeks before the All-Star break, the sim stops and the "
        "ballot opens on the All-Star tab. Every GM votes, the AI ones too: a "
        "1st and 2nd choice at each position, a DH and nine pitchers. Your "
        "ballot starts out filled in with the stat leaders, so change what you "
        "like and press Save ballot before the break.",
        "allstar",
    ),
    (
        "allstar_draft",
        "See who made it",
        "The votes are in: the 64 All-Stars are on the All-Star tab, with a ★ "
        "by their names everywhere. The GMs of the two best teams are the "
        "captains, and they take turns drafting their sides from the 64.",
        "allstar",
    ),
    (
        "allstar_break",
        "Play through the All-Star break",
        "Press play to go through the break. Day 1 has the Rookie Game, day 2 "
        "the Home Run Derby, where the top home run hitters meet in a bracket "
        f"and each swings until {hr_derby.OUTS_PER_ROUND} outs, and day 3 the "
        "All-Star Game, where no pitcher goes more than "
        f"{PITCHER_OUTS_CAP} outs. Nobody gets tired or hurt. Then the "
        "All-Star tab has the derby bracket, the box scores and the MVP.",
        "allstar",
    ),
    (
        "season",
        "Finish the regular season",
        "Keep playing until the regular season ends. The best teams go on to "
        "the playoffs.",
        "standings",
    ),
    (
        "playoffs",
        "Play the playoffs",
        "The Playoffs tab has the bracket. Sim through it to crown a champion, "
        "even if your team is out.",
        "playoffs",
    ),
    (
        "offseason",
        "Get through the offseason",
        "The season summary has the awards and final standings. Press Begin "
        "Offseason: players age, some retire, and the next season's draft "
        "opens. That's the whole cycle.",
        None,
    ),
)


def mark(db, league_id: str, step: str) -> None:
    """Record a coach step the GM just did. Does nothing outside a tutorial
    league, so callers don't need to check."""
    LeagueRepository(db).mark_coach_step(league_id, step)


def _mark_once(db, league: dict, step: str) -> None:
    done = league.get("coach_done") or []
    if step not in done:
        mark(db, league["id"], step)
        league["coach_done"] = [*done, step]


def mark_visit(db, league: dict, tab) -> None:
    """Record the first visit to a tab that one of the steps asks for. Moving
    on to any tab from Meet your team finishes that step: the league's first
    page is Meet your team, so its step stays up while the GM reads it."""
    if not league.get("is_practice"):
        return
    if tab in VISIT_STEPS:
        _mark_once(db, league, tab)
    if tab and tab != "welcome" and league["state"] != "lobby":
        _mark_once(db, league, "welcome")


def mark_all_star_visit(db, league: dict, phase: str, pick_due: bool) -> bool:
    """A look at the All-Star tab: once the All-Stars are in (and a captain
    has made all their picks) it finishes the draft step, and once the games
    are played, the break's step. True if it finished one."""
    if not league or not league.get("is_practice"):
        return False
    step = None
    if phase == "done" and not pick_due:
        step = "allstar_draft"
    elif phase == "played":
        step = "allstar_break"
    if not step or step in (league.get("coach_done") or []):
        return False
    _mark_once(db, league, step)
    return True


def _all_star_week(db, league: dict) -> dict:
    """Where the current season's All-Star week is, for its steps: the phase
    (all_star.phase) and whether the GM is a captain in either draft."""
    season_id = SeasonRepository(db).get_current_id_for_league(league["id"])
    phase = all_star.phase(db, season_id)
    captain = False
    if phase == "done":
        mine = GMRepository(db).get_human_team_ids(league["id"])
        for event in all_star.EVENTS:
            g = AllStarRepository(db, event).game(season_id)
            if g and {g["captain1_team_id"], g["captain2_team_id"]} & mine:
                captain = True
    return {"phase": phase, "captain": captain}


def coach_steps(db, league: dict) -> list[dict]:
    """Each step with whether it's done, in order."""
    repo = LeagueRepository(db)
    done = set(league.get("coach_done") or [])
    state = league["state"]
    seasons = repo.count_seasons(league["id"]) if state != "lobby" else 0
    past_first = seasons >= 2 or state == "complete"
    draft_done = past_first or (state != "lobby" and repo.draft_complete(league["id"]))
    season_over = past_first or state in ("playoffs", "offseason")
    # Steps the league's state shows are done. Setting a draft strategy and
    # playing games also count as done once the GM is past them.
    reached = {
        "start": state != "lobby",
        "prefs": draft_done,
        "draft": draft_done,
        "play": season_over,
        "season": season_over,
        "playoffs": past_first or state == "offseason",
        "offseason": past_first,
    }
    reached["welcome"] = draft_done
    # All-Star week happens partway through the regular season.
    week = {"phase": "none", "captain": False}
    if season_over:
        reached.update(dict.fromkeys(ALL_STAR_STEPS, True))
    elif state == "season" and not done.issuperset(ALL_STAR_STEPS):
        week = _all_star_week(db, league)
        phase = week["phase"]
        # "none" in the season: the break has gone by.
        gone = phase == "none"
        reached["allstar_vote"] = gone or phase in ("done", "played")
        reached["allstar_draft"] = gone or phase == "played"
        reached["allstar_break"] = gone
    explore_left = [t for t in EXPLORE_TABS if t not in done]
    steps = []
    for key, title, text, tab in STEPS:
        if key == "explore":
            is_done = not explore_left
            tab = explore_left[0] if explore_left else None
        elif key == "lineup":
            is_done = all(s in done for s in LINEUP_SAVES)
        else:
            is_done = key in done or reached.get(key, False)
        if key == "allstar_vote" and week["phase"] != "open":
            tab = None  # No All-Star tab until the ballot opens.
        elif key == "allstar_draft" and week["phase"] in ("upcoming", "open"):
            text, tab = WAIT_TEXT, "standings"
        elif key == "allstar_draft" and week["captain"]:
            text += CAPTAIN_TEXT
        elif key == "allstar_break" and week["phase"] != "played":
            tab = "standings"  # Where the play buttons are.
        steps.append(
            {
                "key": key,
                "title": title,
                "text": text,
                "tab": tab,
                "go": GO_LABELS.get(tab, (tab or "").title()),
                "done": is_done,
            }
        )
    return steps


def coach_ctx(db, league: dict) -> dict | None:
    """What dashboard/partials/_coach.html needs, or None outside a tutorial
    league."""
    if not league or not league.get("is_practice"):
        return None
    steps = coach_steps(db, league)
    current = next((s for s in steps if not s["done"]), None)
    return {
        "steps": steps,
        "current": current,
        "done_count": sum(1 for s in steps if s["done"]),
        "explore_left": [
            t for t in EXPLORE_TABS if t not in (league.get("coach_done") or [])
        ],
        "lineup_saved": [
            s for s in LINEUP_SAVES if s in (league.get("coach_done") or [])
        ],
    }
