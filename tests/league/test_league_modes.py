# tests/league/test_league_modes.py
"""
Speed blitz leagues preset the create form and play without injuries or
trades. Plain blitz keeps both.
"""

import html
import json
import re
from random import Random

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.game.game import Game
from src.league.league_modes import (
    BLITZ,
    SPEED_BLITZ,
    get_mode,
    injuries_allowed,
    is_blitz_style,
    trades_allowed,
)
from src.team.team_in_game_factory import TeamInGameFactory
from tests.factories.team_record_factory import make_team_record


def test_speed_blitz_presets():
    assert SPEED_BLITZ.form_presets == {
        "sim_period_days": 30,
        "decision_window_sec": 30,
        "num_seasons": 5,
    }


def test_speed_blitz_has_no_injuries_or_trades():
    assert not injuries_allowed("speed_blitz")
    assert not trades_allowed("speed_blitz")


def test_blitz_keeps_injuries_and_trades():
    assert injuries_allowed("blitz")
    assert trades_allowed("blitz")


def test_both_blitz_modes_play_blitz_style():
    assert is_blitz_style("blitz")
    assert is_blitz_style("speed_blitz")
    assert not is_blitz_style("longform")


def test_longform_keeps_injuries_and_trades():
    assert injuries_allowed("longform")
    assert trades_allowed("longform")


def test_league_without_a_mode_is_blitz():
    assert get_mode(None) is BLITZ


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError):
        get_mode("turbo")


def test_new_league_form_offers_both_blitz_modes_with_their_presets():
    r = TestClient(app).get("/leagues/new")
    assert r.status_code == 200
    options = re.findall(r'<option value="(\w+)" data-presets=\'([^\']*)\'', r.text)
    presets = {key: json.loads(html.unescape(p)) for key, p in options}
    assert presets == {
        "blitz": BLITZ.form_presets,
        "speed_blitz": SPEED_BLITZ.form_presets,
    }


def _play(monkeypatch, injuries_enabled):
    # Every check hurts someone, so any check that runs shows up.
    monkeypatch.setattr("src.game.game.INJURY_BASE_PROB", 1.0)
    home = TeamInGameFactory.from_record(make_team_record(size=10))
    away = TeamInGameFactory.from_record(make_team_record(size=10))
    game = Game(home, away, rng=Random(7), injuries_enabled=injuries_enabled)
    game.home.set_lineup()
    game.away.set_lineup()
    game.play()
    return game


def test_game_without_injuries_hurts_nobody(monkeypatch):
    assert _play(monkeypatch, injuries_enabled=False).new_injuries == []


def test_game_with_injuries_can_hurt_players(monkeypatch):
    assert _play(monkeypatch, injuries_enabled=True).new_injuries


def test_db_accepts_a_speed_blitz_league(db_conn, factory):
    league = factory.league(state="lobby", mode="speed_blitz")
    row = db_conn.execute(
        "SELECT mode FROM leagues WHERE id = %s", (league.id,)
    ).fetchone()
    assert row["mode"] == "speed_blitz"
