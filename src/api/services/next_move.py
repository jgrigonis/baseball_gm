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
# needs no queries of its own; the one fact the shell doesn't have, whether
# the All-Star weekend is ready to sim, comes in as weekend_ready.

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


def _play_menu(ctx: dict, season_note: str) -> list[dict]:
    menu = []
    if ctx.get("injuries_enabled"):
        menu.append(_item("▶ Until Injury", "schedSim", "injury", "sched-injury-btn"))
    menu.append(
        _item("▶▶ Full Season", "schedSim", "season", "sched-season-btn", season_note)
    )
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


def pick(ctx: dict, page: str, weekend_ready: bool = False) -> dict | None:
    """The next move for this GM on this page, or None for no button.

    page is the last part of the page's path: draft, playoffs,
    season-summary, retirement, welcome and so on."""
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
        move["pill"] = _pill(ctx, page)
        return move

    if state == "draft":
        if ctx.get("draft_complete"):
            return None
        if page == "draft":
            return _act("run-draft", "Run Draft ▶", "Run Draft ▶", "runDraft",
                        btn_id="execute-btn")
        if page == "retirement" and ctx.get("team_page_label") == "Season preview":
            return _go("preview", "Season preview →", "Preview →", f"{base}/welcome")
        return _go("go-draft", "Go to the draft →", "Draft →", f"{base}/draft")

    if state in ("preseason", "season"):
        if weekend_ready:
            move = _act(
                "all-star-weekend",
                "★ Sim All-Star Weekend",
                "★ All-Star",
                "schedSim",
                "1",
                "sched-play-btn",
                menu=[
                    _item("▶▶ Full Season", "schedSim", "season", "sched-season-btn",
                          "plays the weekend, then keeps going")
                ],
                kind="star",
            )
        elif state == "preseason":
            move = _act("play", "▶ Play Opening Day", "▶ Play Day", "schedSim", "1",
                        "sched-play-btn", _play_menu(ctx, "to the playoffs"))
        else:
            move = _act("play", "▶ Play Day", "▶ Play Day", "schedSim", "1",
                        "sched-play-btn", _play_menu(ctx, "to the playoffs"))
        move["stop"] = True
        move["ignore_trades"] = bool(ctx.get("trades_enabled"))
        move["pill"] = _pill(ctx, page)
        return move

    if state == "playoffs":
        if page == "playoffs":
            return _act(
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
        return _go("go-playoffs", "🥇 Go to Playoffs →", "Playoffs →",
                   f"{base}/playoffs")

    # offseason: the champion is crowned and the offseason hasn't run.
    if page == "season-summary":
        return _act("begin-offseason", "Begin Offseason →", "Offseason →",
                    "beginOffseason", btn_id="begin-offseason-btn")
    return _go("go-summary", "📜 Season Summary →", "Summary →",
               f"{base}/season-summary")
