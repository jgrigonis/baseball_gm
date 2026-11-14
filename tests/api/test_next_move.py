# tests/api/test_next_move.py
"""The top bar's next-move button: one control that always says what to do
next. Elsewhere it goes to the move; on the move's own page it does it."""

from src.api.services.next_move import pick


def _ctx(**kw):
    ctx = {
        "league_id": "L1",
        "team_id": "T1",
        "is_viewer": False,
        "multiplayer": False,
        "league_state": "season",
        "injuries_enabled": True,
        "trades_enabled": True,
        "draft_complete": True,
        "team_page_label": "Season preview",
    }
    ctx.update(kw)
    return ctx


def _menu(move):
    return [m["label"] for m in move["menu"]]


def test_season_plays_a_day_on_every_page():
    for page in ("roster", "lineup", "standings", "stats"):
        move = pick(_ctx(), page)
        assert move["label"] == "▶ Play Day" and move["fn"] == "schedSim"
        assert move["arg"] == "1" and move["id"] == "sched-play-btn"
        assert move["stop"] and move["trade_stops"]
    assert _menu(pick(_ctx(), "roster")) == ["▶ 1 Week", "▶ 1 Month", "▶▶ Full Season"]


def test_no_injury_or_trade_stops_when_the_league_has_neither():
    move = pick(_ctx(injuries_enabled=False, trades_enabled=False), "roster")
    assert not move["injury_stop"] and not move["trade_stops"]
    assert pick(_ctx(), "roster")["injury_stop"]


def test_no_trade_stops_once_the_deadline_is_behind():
    # No team can offer a trade then, so there's nothing to stop for.
    assert not pick(_ctx(trades_closed=True), "roster")["trade_stops"]


def test_preseason_plays_opening_day():
    move = pick(_ctx(league_state="preseason"), "draft")
    assert move["label"] == "▶ Play Opening Day" and move["short"] == "▶ Play Day"


def test_all_star_break_sims_the_weekend():
    move = pick(_ctx(), "standings", weekend_ready=True)
    assert move["key"] == "all-star-weekend" and move["kind"] == "star"
    assert move["label"] == "★ Sim All-Star Weekend"
    assert move["fn"] == "schedSim" and move["arg"] == "1"
    assert _menu(move) == ["▶▶ Full Season"]


def test_all_star_to_dos_are_a_pill_beside_play_day():
    move = pick(_ctx(all_star_ballot_due=True), "roster")
    assert move["label"] == "▶ Play Day" and move["pill"]["label"] == "★ Vote"
    move = pick(_ctx(all_star_pick_due=True), "roster")
    assert move["pill"]["label"] == "★ Your pick"
    assert move["pill"]["href"] == "/leagues/L1/allstar"
    # Not on the All-Star tab itself, where the ballot is.
    assert pick(_ctx(all_star_ballot_due=True), "allstar")["pill"]["label"] == (
        "📊 Standings"
    )


def test_playoffs_go_there_then_sim_there():
    move = pick(_ctx(league_state="playoffs"), "standings")
    assert (
        move["label"] == "🥇 Go to Playoffs →"
        and move["href"] == "/leagues/L1/playoffs"
    )
    move = pick(_ctx(league_state="playoffs"), "playoffs")
    assert move["label"] == "▶ Sim Playoff Day" and move["fn"] == "simPlayoffs"
    assert move["arg"] == "game" and _menu(move) == ["▶ Sim Round", "▶▶ Full Playoffs"]
    assert move["stop"]


def test_after_the_champion_the_summary_then_expiring_deals_then_begin_offseason():
    move = pick(_ctx(league_state="offseason"), "playoffs")
    assert move["label"] == "📜 Season Summary →"
    assert move["href"] == "/leagues/L1/season-summary"
    move = pick(_ctx(league_state="offseason"), "season-summary")
    assert move["href"] == "/leagues/L1/expiring"
    move = pick(_ctx(league_state="offseason"), "expiring")
    assert move["label"] == "Begin Offseason →" and move["fn"] == "beginOffseason"


def test_draft_go_there_then_run_it():
    ctx = _ctx(
        league_state="draft", draft_complete=False, team_page_label="Meet your team"
    )
    move = pick(ctx, "welcome")
    assert move["label"] == "Go to the draft →" and move["href"] == "/leagues/L1/draft"
    move = pick(ctx, "draft")
    assert move["label"] == "Run Draft ▶" and move["fn"] == "runDraft"


def test_after_the_retirements_the_season_preview():
    ctx = _ctx(league_state="draft", draft_complete=False)
    assert pick(ctx, "retirement")["href"] == "/leagues/L1/welcome"
    assert pick(ctx, "welcome")["label"] == "Go to the draft →"


def test_a_complete_league_links_its_final_summary():
    move = pick(_ctx(league_state="complete"), "standings")
    assert move["kind"] == "quiet" and move["href"] == "/leagues/L1/season-summary"
    assert pick(_ctx(league_state="complete"), "season-summary") is None


def test_multiplayer_is_the_ready_toggle():
    for state in ("draft", "season", "playoffs", "offseason"):
        move = pick(_ctx(multiplayer=True, league_state=state), "playoffs")
        assert move["kind"] == "ready" and move["id"] == "ready-btn"
        assert move["menu"][0]["id"] == "ready-away-btn"


def test_no_button_for_viewers_the_lobby_or_no_team():
    assert pick(_ctx(is_viewer=True), "standings") is None
    assert pick(_ctx(league_state="lobby"), "standings") is None
    assert pick(_ctx(team_id=None), "standings") is None


# ── Full Season's note and the All-Star break toggle ──────────────────────

from src.api.services.next_move import sim_stops  # noqa: E402


class _Win:
    opens, closes, resumes = "2026-06-20", "2026-07-05", "2026-07-09"


def _kinds(stops):
    return [s["kind"] for s in stops]


def test_stops_ahead_in_date_order():
    stops = sim_stops("2026-04-01", "upcoming", _Win(), "2026-07-31")
    assert _kinds(stops) == ["vote", "stars", "deadline", "playoffs"]
    assert stops[0]["note"] == "to the All-Star vote"
    # Ballot open: the break is next.
    assert _kinds(sim_stops("2026-06-25", "open", _Win(), "2026-07-31")) == [
        "stars",
        "deadline",
        "playoffs",
    ]
    # A deadline before the break sorts first.
    assert _kinds(sim_stops("2026-04-01", "open", _Win(), "2026-06-01"))[0] == (
        "deadline"
    )
    # Past the deadline, after the weekend, no trades: just the playoffs.
    assert _kinds(sim_stops("2026-08-10", "played", _Win(), "2026-07-31")) == [
        "playoffs"
    ]
    assert _kinds(sim_stops("2026-04-01", "none", None, None)) == ["playoffs"]


def test_stops_carry_their_dates_for_the_sim_card_bar():
    stops = sim_stops("2026-04-01", "upcoming", _Win(), "2026-07-31", "2026-09-27")
    assert [s["date"] for s in stops] == [
        "2026-06-20",
        "2026-07-05",
        "2026-07-31",
        "2026-09-27",
    ]
    # Without the season's end, the playoffs stop has no date (and no bar).
    assert sim_stops("2026-04-01", "none")[-1]["date"] is None


def test_full_season_names_its_next_stop():
    stops = sim_stops("2026-04-01", "upcoming", _Win(), "2026-07-31")
    move = pick(_ctx(), "roster", stops=stops)
    season = move["menu"][-1]
    assert season["note"] == "to the All-Star vote" and season["stops"] == stops
    assert move["through_break"]


def test_no_break_toggle_once_the_break_is_behind():
    stops = sim_stops("2026-08-10", "played", _Win(), "2026-07-31")
    move = pick(_ctx(), "roster", stops=stops)
    assert move["menu"][-1]["note"] == "to the playoffs"
    assert not move["through_break"]
    # Without stops it still defaults to the playoffs.
    assert pick(_ctx(), "roster")["menu"][-1]["note"] == "to the playoffs"


def test_preseason_sends_the_gm_to_set_the_budget_first():
    # Josh, 2026-11-09: the front office and ticket prices lock on Opening
    # Day, so the button asks for one look at the Budget tab first.
    move = pick(_ctx(league_state="preseason", budget_due=True), "roster")
    assert move["key"] == "set-budget" and move["href"] == "/leagues/L1/budget"
    # On the Budget tab itself it plays Opening Day.
    move = pick(_ctx(league_state="preseason", budget_due=True), "budget")
    assert move["label"] == "▶ Play Opening Day"
    # Once it's seen, the button plays on as before.
    move = pick(_ctx(league_state="preseason", budget_due=False), "roster")
    assert move["label"] == "▶ Play Opening Day"
    # Several GMs: a pill beside the ready button instead.
    move = pick(
        _ctx(league_state="preseason", budget_due=True, multiplayer=True), "roster"
    )
    assert move["key"] == "ready" and move["pill"]["href"] == "/leagues/L1/budget"
    move = pick(_ctx(league_state="season", budget_due=True), "roster")
    assert move["label"] == "▶ Play Day"


def test_preseason_goes_budget_then_roster_then_lineup():
    # Josh, 2026-11-10: after the budget, a look at the roster and the
    # lineup before Opening Day, each until the GM has opened it.
    pre = dict(league_state="preseason", roster_due=True, lineup_due=True)
    move = pick(_ctx(budget_due=True, **pre), "standings")
    assert move["key"] == "set-budget"
    move = pick(_ctx(budget_due=True, **pre), "budget")
    assert move["key"] == "go-roster" and move["href"] == "/leagues/L1/roster"
    # Opening the Roster tab marks it seen, so there it points on.
    move = pick(_ctx(league_state="preseason", lineup_due=True), "roster")
    assert move["key"] == "go-lineup" and move["href"] == "/leagues/L1/lineup"
    move = pick(_ctx(league_state="preseason", lineup_due=True), "standings")
    assert move["key"] == "go-lineup"
    move = pick(_ctx(league_state="preseason"), "lineup")
    assert move["label"] == "▶ Play Opening Day"
    # The lineup first: the roster is still to see.
    move = pick(_ctx(league_state="preseason", roster_due=True), "lineup")
    assert move["key"] == "go-roster"
    # Several GMs keep the ready button; the season ignores the flags.
    move = pick(_ctx(multiplayer=True, **pre), "budget")
    assert move["key"] == "ready"
    move = pick(_ctx(league_state="season", roster_due=True), "standings")
    assert move["label"] == "▶ Play Day"


def test_once_the_summary_is_seen_every_page_points_on_to_expiring_deals():
    ctx = _ctx(league_state="offseason", summary_seen=True)
    for page in ("roster", "standings", "budget", "playoffs"):
        move = pick(ctx, page)
        assert move["label"] == "📝 Expiring Deals →"
        assert move["href"] == "/leagues/L1/expiring"
    assert pick(ctx, "season-summary")["href"] == "/leagues/L1/expiring"
    # The pool is just a page on the way now: it points on to the deals.
    assert pick(ctx, "free-agents")["href"] == "/leagues/L1/expiring"
    assert pick(ctx, "expiring")["fn"] == "beginOffseason"


def test_after_a_trade_the_roster_then_play_day():
    # Josh, 2026-11-11: players traded for wait in the organization, so the
    # button goes to the Roster tab; opening it clears the flag (web/utils).
    move = pick(_ctx(trade_roster_due=True), "trades")
    assert move["key"] == "trade-roster" and move["href"] == "/leagues/L1/roster"
    assert pick(_ctx(trade_roster_due=True), "standings")["key"] == "trade-roster"
    assert pick(_ctx(trade_roster_due=True), "roster")["label"] == "▶ Play Day"
    assert pick(_ctx(), "trades")["label"] == "▶ Play Day"
    move = pick(_ctx(league_state="preseason", trade_roster_due=True), "budget")
    assert move["key"] == "trade-roster"
    # Several GMs: the ready button stays, with a Roster pill beside it.
    move = pick(_ctx(multiplayer=True, trade_roster_due=True), "trades")
    assert move["key"] == "ready" and move["pill"]["href"] == "/leagues/L1/roster"
    assert pick(_ctx(multiplayer=True, trade_roster_due=True), "roster")["pill"] is None


def test_multiplayer_draft_pills_draft_then_free_agents():
    # Josh, 2026-11-12: with several GMs the draft period's to-dos ride
    # beside the ready button, the Draft tab, then the Free Agents tab, each
    # until it's opened (web/utils marks them).
    mp = dict(multiplayer=True, league_state="draft", draft_complete=False)
    move = pick(_ctx(draft_tab_due=True, fa_tab_due=True, **mp), "standings")
    assert move["key"] == "ready" and move["pill"]["href"] == "/leagues/L1/draft"
    # On the Draft tab (marked seen there), the Free Agents tab is next.
    move = pick(_ctx(fa_tab_due=True, **mp), "draft")
    assert move["pill"]["href"] == "/leagues/L1/free-agents"
    # The pool first: the Draft tab is still to see.
    move = pick(_ctx(draft_tab_due=True, **mp), "free-agents")
    assert move["pill"]["href"] == "/leagues/L1/draft"
    assert pick(_ctx(**mp), "standings")["pill"] is None
    # A solo draft keeps its own button and no pill.
    move = pick(
        _ctx(league_state="draft", draft_complete=False, draft_tab_due=True),
        "standings",
    )
    assert move["key"] == "go-draft" and "pill" not in move


def test_multiplayer_preseason_roster_pill_after_the_budget():
    # After the draft (and free agents settling), the Roster tab, once the
    # budget pill is done.
    pre = dict(multiplayer=True, league_state="preseason", roster_due=True)
    move = pick(_ctx(budget_due=True, **pre), "standings")
    assert move["pill"]["href"] == "/leagues/L1/budget"
    move = pick(_ctx(budget_due=True, **pre), "budget")
    assert move["pill"]["href"] == "/leagues/L1/roster"
    move = pick(_ctx(**pre), "standings")
    assert move["key"] == "ready" and move["pill"]["href"] == "/leagues/L1/roster"
    assert pick(_ctx(**pre), "roster")["pill"] is None
    # The season ignores the preseason flag.
    move = pick(
        _ctx(multiplayer=True, league_state="season", roster_due=True), "standings"
    )
    assert move["pill"] is None


def test_preseason_bids_come_before_the_roster():
    """Free agent bids stay open into the preseason (Josh, 2026-11-12): the
    Free Agents tab after the budget, Close Bidding there, then the Roster."""
    pre = dict(
        league_state="preseason", fa_bidding=True, roster_due=True, lineup_due=True
    )
    assert pick(_ctx(**pre, budget_due=True), "standings")["key"] == "set-budget"
    assert pick(_ctx(**pre), "roster")["key"] == "go-bids"
    move = pick(_ctx(**pre), "free-agents")
    assert move["key"] == "close-bidding" and move["fn"] == "closeBidding"
    pre["fa_bidding"] = False
    assert pick(_ctx(**pre), "free-agents")["key"] == "go-roster"


def test_multiplayer_preseason_bids_pill_before_roster():
    pre = dict(
        multiplayer=True, league_state="preseason", fa_bidding=True, roster_due=True
    )
    assert pick(_ctx(**pre), "standings")["pill"]["label"] == "✍️ Bids"
    assert pick(_ctx(**pre), "free-agents")["pill"] is None
    pre["fa_bidding"] = False
    assert pick(_ctx(**pre), "standings")["pill"]["label"] == "👥 Roster"


def test_multiplayer_offseason_pills_summary_then_expiring_deals():
    # Josh, 2026-11-12: in multiplayer the Expiring Deals tab was never in
    # front of him. Beside the ready toggle: the season summary, then the
    # Expiring Deals tab until it's opened (web/utils marks it).
    mp = dict(multiplayer=True, league_state="offseason")
    move = pick(_ctx(expiring_due=True, **mp), "playoffs")
    assert move["key"] == "ready"
    assert move["pill"]["href"] == "/leagues/L1/season-summary"
    # On the summary, and anywhere once it's been opened: Expiring Deals.
    move = pick(_ctx(expiring_due=True, **mp), "season-summary")
    assert move["pill"]["href"] == "/leagues/L1/expiring"
    move = pick(_ctx(expiring_due=True, summary_seen=True, **mp), "standings")
    assert move["pill"]["href"] == "/leagues/L1/expiring"
    # Not on the tab itself, and gone once it's been opened.
    assert (
        pick(_ctx(expiring_due=True, summary_seen=True, **mp), "expiring")["pill"]
        is None
    )
    assert pick(_ctx(summary_seen=True, **mp), "standings")["pill"] is None
    assert pick(_ctx(**mp), "playoffs")["pill"] is None
    # Solo keeps its own button.
    move = pick(_ctx(league_state="offseason", summary_seen=True), "standings")
    assert move["key"] == "go-expiring" and "pill" not in move


def test_speed_blitz_offseason_skips_expiring_deals():
    """Josh, 2026-11-14: no money in Speed Blitz, so expiring deals re-sign
    on their own. The summary leads straight to Begin Offseason."""
    solo = dict(league_state="offseason", has_money=False)
    assert pick(_ctx(**solo), "standings")["key"] == "go-summary"
    assert pick(_ctx(**solo), "season-summary")["key"] == "begin-offseason"
    assert pick(_ctx(summary_seen=True, **solo), "standings")["key"] == (
        "begin-offseason"
    )
    mp = dict(multiplayer=True, **solo)
    assert pick(_ctx(expiring_due=True, **mp), "playoffs")["pill"]["href"] == (
        "/leagues/L1/season-summary"
    )
    assert pick(_ctx(expiring_due=True, **mp), "season-summary")["pill"] is None


def test_strategy_pill_before_opening_day_and_standings_pill_in_season():
    move = pick(_ctx(league_state="preseason", strategy_due=True), "roster")
    assert move["label"] == "▶ Play Opening Day"
    assert move["pill"]["label"] == "🧠 Strategy"
    assert (
        pick(_ctx(league_state="preseason", strategy_due=True), "strategy")["pill"]
        is None
    )
    assert pick(_ctx(league_state="preseason"), "roster")["pill"] is None
    assert pick(_ctx(), "roster")["pill"]["label"] == "📊 Standings"
    for page in ("standings", "schedule"):
        assert pick(_ctx(), page)["pill"] is None
