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

from src.db.repositories.league_repo import LeagueRepository

# Tabs whose first visit counts toward a step. Explore needs all four.
EXPLORE_TABS = ("schedule", "standings", "stats", "leaders")
VISIT_STEPS = ("strategy", *EXPLORE_TABS)
# The lineup step needs all three of the Lineup tab's saves.
LINEUP_SAVES = ("batting", "rotation", "bullpen")

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


def mark_visit(db, league: dict, tab) -> None:
    """Record the first visit to a tab that one of the steps asks for."""
    if league.get("is_practice") and tab in VISIT_STEPS:
        done = league.get("coach_done") or []
        if tab not in done:
            mark(db, league["id"], tab)
            league["coach_done"] = [*done, tab]


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
        steps.append(
            {"key": key, "title": title, "text": text, "tab": tab, "done": is_done}
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
