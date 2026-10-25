# tests/league/test_league_modes.py
"""
Blitz leagues preset the create form and play without injuries or trades.
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
    get_mode,
    injuries_allowed,
    trades_allowed,
)
from src.team.team_in_game_factory import TeamInGameFactory
from tests.factories.team_record_factory import make_team_record


def test_blitz_presets():
    assert BLITZ.form_presets == {
        "sim_period_days": 30,
        "decision_window_sec": 30,
        "num_seasons": 5,
    }


def test_blitz_has_no_injuries_or_trades():
    assert not injuries_allowed("blitz")
    assert not trades_allowed("blitz")


def test_longform_keeps_injuries_and_trades():
    assert injuries_allowed("longform")
    assert trades_allowed("longform")


def test_league_without_a_mode_is_blitz():
    assert get_mode(None) is BLITZ


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError):
        get_mode("turbo")


def test_new_league_form_carries_the_blitz_presets():
    r = TestClient(app).get("/leagues/new")
    assert r.status_code == 200
    presets = re.search(r"data-presets='([^']*)'", r.text).group(1)
    assert json.loads(html.unescape(presets)) == BLITZ.form_presets


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
