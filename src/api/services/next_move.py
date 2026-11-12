# src/api/services/next_move.py
#
# The top bar's next-move button: one control on every league page that
# always says what to do next. On any other page it takes the GM to where the
# next move happens ("Go to Playoffs →"); on that page it does the move
# ("▶ Sim Playoff Day"). Its ▾ menu has the other ways to do it, and a pill
# beside it carries optional to-dos (the All-Star ballot, a captain's pick)
# that never block play.
#
# pick() reads the league shell's context (web/utils.py _shell_ctx), so it
# needs no queries of its own; what the shell doesn't have comes in as
# arguments: whether the All-Star weekend is ready to sim, and the season's
# stops (sim_stops) for the Full Season note.

from __future__ import annotations


def _go(key, label, short, href, kind="go"):
    return {"key": key, "kind": kind, "label": label, "short": short, "href": href}


def _act(key, label, short, fn, arg="", btn_id=None, menu=(), kind="play"):
    return {
        "key": key,
        "kind": kind,
        "label": label,
        "short": short,
        "fn": fn,
        "arg": arg,
        "id": btn_id,
        "menu": list(menu),
    }


def _item(label, fn, arg="", btn_id=None, note=""):
    return {"label": label, "fn": fn, "arg": arg, "id": btn_id, "note": note}


# Where a multi-day sim stops (_play_script.html), and the Full Season note
# for each. The All-Star stops go by with "Stop for All-Star breaks"
# unchecked, the deadline with "Stop at the trade deadline" unchecked; the
# browser picks the first stop left (schedUpdateStops).
STOP_NOTES = {
    "vote": "to the All-Star vote",
    "stars": "to the All-Star break",
    "weekend": "through the All-Star Weekend",
    "deadline": "to the trade deadline",
    "playoffs": "to the playoffs",
}
ALL_STAR_STOPS = ("vote", "stars", "weekend")


def sim_stops(
    today: str | None,
    as_phase: str,
    as_window=None,
    deadline: str | None = None,
    season_end: str | None = None,
) -> list[dict]:
    """The regular season's scheduled stops still ahead, in order: the day
    the All-Star ballot opens, the break (the All-Stars are named), the
    weekend itself, the trade deadline, and the end of the season. today is
    the next day to play; as_window is all_star.Window (opens, closes,
    resumes); deadline is the trade deadline's date, None when the league
    doesn't trade; season_end is the regular season's last day. Each stop
    carries its date, which fills the sim card's bar on a Full Season run.
    A sim also stops for a new trade offer, which can't be known ahead."""
    stops = []
    if as_window and as_phase == "upcoming":
        stops.append(("vote", as_window.opens))
    if as_window and as_phase in ("upcoming", "open"):
        stops.append(("stars", as_window.closes))
    if as_window and as_phase == "done":
        stops.append(("weekend", as_window.resumes))
    if deadline and today and today <= deadline:
        # The sim stops after the deadline day's games; the break days
        # around it sort by date like everything else.
        stops.append(("deadline", deadline))
    stops.sort(key=lambda s: s[1])
    out = [{"kind": k, "note": STOP_NOTES[k], "date": d} for k, d in stops]
    return out + [
        {"kind": "playoffs", "note": STOP_NOTES["playoffs"], "date": season_end}
    ]


def _season_item(stops: list[dict]) -> dict:
    """▶▶ Full Season, noting where it will stop."""
    item = _item(
        "▶▶ Full Season", "schedSim", "season", "sched-season-btn", stops[0]["note"]
    )
    item["stops"] = stops
    return item


def _play_menu(ctx: dict, stops: list[dict]) -> list[dict]:
    menu = []
    if ctx.get("injuries_enabled"):
        menu.append(_item("▶ Until Injury", "schedSim", "injury", "sched-injury-btn"))
    menu.append(_season_item(stops))
    return menu


def _pill(ctx: dict, page: str) -> dict | None:
    """An optional All-Star to-do. Not on the All-Star tab, where it's in
    front of the GM already."""
    if page == "allstar":
        return None
    href = f"/leagues/{ctx['league_id']}/allstar"
    if ctx.get("all_star_ballot_due"):
        return {
            "label": "★ Vote",
            "href": href,
            "title": "Your All-Star ballot isn't saved yet. If you skip it, "
            "your scouts fill it in.",
        }
    if ctx.get("all_star_pick_due"):
        return {
            "label": "★ Your pick",
            "href": href,
            "title": "Your pick in the All-Star draft. If you play on, "
            "your scouts make the rest.",
        }
    return None


def _budget_pill(ctx: dict, page: str) -> dict | None:
    """With several GMs the button is the ready toggle, so the budget
    reminder rides beside it instead."""
    if ctx.get("league_state") != "preseason" or not ctx.get("budget_due"):
        return None
    if page == "budget":
        return None
    return {
        "label": "💰 Budget",
        "short": "💰",
        "href": f"/leagues/{ctx['league_id']}/budget",
        "title": "Set your front office and ticket prices before Opening Day; "
        "they're locked for the season after that.",
    }


def _trade_pill(ctx: dict, page: str) -> dict | None:
    """With several GMs the button is the ready toggle, so the after-trade
    Roster reminder rides beside it instead."""
    if not ctx.get("trade_roster_due") or page == "roster":
        return None
    return {
        "label": "📋 Roster",
        "short": "📋",
        "href": f"/leagues/{ctx['league_id']}/roster",
        "title": "Your trade's new players are in your organization. Move "
        "them to your 40-man on the Roster tab to use them.",
    }


def _draft_pill(ctx: dict, page: str) -> dict | None:
    """A multiplayer draft's to-dos beside the ready toggle (Josh,
    2026-11-12): the Draft tab, then the Free Agents tab, each until the GM
    opens it."""
    if ctx.get("league_state") != "draft":
        return None
    base = f"/leagues/{ctx['league_id']}"
    if ctx.get("draft_tab_due") and page != "draft":
        return {
            "label": "📋 Draft",
            "short": "📋",
            "href": f"{base}/draft",
            "title": "Set your draft board before everyone's ready and the draft runs.",
        }
    if ctx.get("fa_tab_due") and page != "free-agents":
        return {
            "label": "✍️ Free Agents",
            "short": "✍️",
            "href": f"{base}/free-agents",
            "title": "Free agents take bids during the draft. They pick a "
            "team as the preseason starts.",
        }
    return None


def _roster_pill(ctx: dict, page: str) -> dict | None:
    """After the draft, a look at the roster the draft and free agency left
    (Josh, 2026-11-12), once each preseason until the Roster tab is opened."""
    if ctx.get("league_state") != "preseason" or not ctx.get("roster_due"):
        return None
    if page == "roster":
        return None
    return {
        "label": "👥 Roster",
        "short": "👥",
        "href": f"/leagues/{ctx['league_id']}/roster",
        "title": "See who the draft and free agency brought you, and set "
        "your 40-man and 26-man.",
    }


def pick(
    ctx: dict,
    page: str,
    weekend_ready: bool = False,
    stops: list[dict] | None = None,
) -> dict | None:
    """The next move for this GM on this page, or None for no button.

    page is the last part of the page's path: draft, playoffs,
    season-summary, retirement, welcome and so on. stops is sim_stops(),
    for the regular season's Full Season note."""
    if not ctx.get("league_id") or ctx.get("is_viewer") or not ctx.get("team_id"):
        return None
    state = ctx.get("league_state")
    lid = ctx["league_id"]
    base = f"/leagues/{lid}"

    if state == "complete":
        if page == "season-summary":
            return None
        return _go(
            "complete",
            "🏆 Final Summary →",
            "Final →",
            f"{base}/season-summary",
            kind="quiet",
        )
    if state not in ("draft", "preseason", "season", "playoffs", "offseason"):
        return None

    # Several human GMs: the league moves on when everyone is ready, so the
    # button is the ready toggle (_ready_bar.html runs it).
    if ctx.get("multiplayer"):
        move = {
            "key": "ready",
            "kind": "ready",
            "label": "I'm ready",
            "short": "I'm ready",
            "fn": "readyToggle",
            "arg": "",
            "id": "ready-btn",
            "menu": [_item("Mark me away", "readyToggleAway", btn_id="ready-away-btn")],
        }
        move["pill"] = (
            _pill(ctx, page)
            or _draft_pill(ctx, page)
            or _trade_pill(ctx, page)
            or _budget_pill(ctx, page)
            or _roster_pill(ctx, page)
        )
        return move

    if state == "draft":
        if ctx.get("draft_complete"):
            return None
        if page == "draft":
            return _act(
                "run-draft",
                "Run Draft ▶",
                "Run Draft ▶",
                "runDraft",
                btn_id="execute-btn",
            )
        if page == "retirement" and ctx.get("team_page_label") == "Season preview":
            return _go("preview", "Season preview →", "Preview →", f"{base}/welcome")
        return _go("go-draft", "Go to the draft →", "Draft →", f"{base}/draft")

    # A trade brought players in: they wait in the organization, so the
    # Roster tab first, to move them to the 40-man; opening it clears this
    # and the button goes back to Play Day (Josh, 2026-11-11).
    if (
        state in ("preseason", "season")
        and ctx.get("trade_roster_due")
        and page != "roster"
    ):
        return _go("trade-roster", "📋 Go to Roster →", "Roster →", f"{base}/roster")
    # The front office and ticket prices lock on Opening Day, so the GM
    # gets one look at the Budget tab first (Josh, 2026-11-09).
    if state == "preseason" and ctx.get("budget_due") and page != "budget":
        return _go("set-budget", "💰 Set Your Budget →", "Budget →", f"{base}/budget")
    # Then a look at the roster and the batting order before the first game
    # (Josh, 2026-11-10). Opening the tab marks it seen (web/utils.py), so
    # on the Roster tab the button already points on to the Lineup.
    if state == "preseason" and ctx.get("roster_due") and page != "roster":
        return _go("go-roster", "📋 Check Your Roster →", "Roster →", f"{base}/roster")
    if state == "preseason" and ctx.get("lineup_due") and page != "lineup":
        return _go("go-lineup", "📝 Set Your Lineup →", "Lineup →", f"{base}/lineup")

    if state in ("preseason", "season"):
        stops = stops or [{"kind": "playoffs", "note": STOP_NOTES["playoffs"]}]
        if weekend_ready:
            move = _act(
                "all-star-weekend",
                "★ Sim All-Star Weekend",
                "★ All-Star",
                "schedSim",
                "1",
                "sched-play-btn",
                menu=[_season_item(stops)],
                kind="star",
            )
        elif state == "preseason":
            move = _act(
                "play",
                "▶ Play Opening Day",
                "▶ Play Day",
                "schedSim",
                "1",
                "sched-play-btn",
                _play_menu(ctx, stops),
            )
        else:
            move = _act(
                "play",
                "▶ Play Day",
                "▶ Play Day",
                "schedSim",
                "1",
                "sched-play-btn",
                _play_menu(ctx, stops),
            )
        move["stop"] = True
        # Leagues that trade: boxes for stopping at offers and the deadline,
        # until deadline day is behind (no offers after it).
        move["trade_stops"] = bool(
            ctx.get("trades_enabled") and not ctx.get("trades_closed")
        )
        # Multi-day sims can play straight through the All-Star break
        # (Stop for All-Star breaks unchecked).
        move["through_break"] = any(s["kind"] in ALL_STAR_STOPS for s in stops)
        move["pill"] = _pill(ctx, page)
        return move

    if state == "playoffs":
        if page == "playoffs":
            move = _act(
                "sim-playoffs",
                "▶ Sim Playoff Day",
                "▶ Sim Day",
                "simPlayoffs",
                "game",
                "po-day-btn",
                menu=[
                    _item("▶ Sim Round", "simPlayoffs", "round", "po-round-btn"),
                    _item("▶▶ Full Playoffs", "simPlayoffs", "all", "po-all-btn"),
                ],
            )
            # Sim Round and Full Playoffs play a day at a time; Stop ends them.
            move["stop"] = True
            return move
        return _go(
            "go-playoffs", "🥇 Go to Playoffs →", "Playoffs →", f"{base}/playoffs"
        )

    # offseason: the champion is crowned and the offseason hasn't run. The
    # summary, then the Expiring Deals tab to decide on expiring deals (Josh,
    # 2026-11-09; its own tab since 2026-11-10), then the offseason runs. Once the GM has opened the
    # summary (summary_seen), every page points on to the next step and the
    # summary is a sidebar link.
    if page == "expiring":
        return _act(
            "begin-offseason",
            "Begin Offseason →",
            "Offseason →",
            "beginOffseason",
            btn_id="begin-offseason-btn",
        )
    if page == "season-summary" or ctx.get("summary_seen"):
        return _go(
            "go-expiring",
            "📝 Expiring Deals →",
            "Deals →",
            f"{base}/expiring",
        )
    return _go(
        "go-summary", "📜 Season Summary →", "Summary →", f"{base}/season-summary"
    )
