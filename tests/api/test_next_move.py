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
    assert _menu(pick(_ctx(), "roster")) == ["▶ Until Injury", "▶▶ Full Season"]


def test_no_until_injury_or_trade_stops_when_the_league_has_neither():
    move = pick(_ctx(injuries_enabled=False, trades_enabled=False), "roster")
    assert _menu(move) == ["▶▶ Full Season"] and not move["trade_stops"]


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
    assert pick(_ctx(all_star_ballot_due=True), "allstar")["pill"] is None


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


def test_after_the_champion_the_summary_then_begin_offseason():
    move = pick(_ctx(league_state="offseason"), "playoffs")
    assert move["label"] == "📜 Season Summary →"
    assert move["href"] == "/leagues/L1/season-summary"
    move = pick(_ctx(league_state="offseason"), "season-summary")
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
