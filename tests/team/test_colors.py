import json

from src.team.colors import TEAM_COLORS, colors_for, contrast, team_badge
from src.util.locations import MANIFEST_FILES_DIR


def test_every_world_league_team_has_colors():
    manifest = json.loads((MANIFEST_FILES_DIR / "world_league-2025.json").read_text())
    for team in manifest["teams"]:
        assert (team["city"], team["mascot"]) in TEAM_COLORS, team


def test_codes_are_unique():
    codes = [c.code for c in TEAM_COLORS.values()]
    assert len(codes) == len(set(codes))


def test_badge_text_is_readable_on_every_team():
    for c in TEAM_COLORS.values():
        assert contrast(c.primary, c.ink) >= 3, c


def test_unknown_team_gets_stable_colors():
    a = colors_for("Boston", "Beans")
    assert a == colors_for("Boston", "Beans")
    assert a.code == "BOS"
    assert colors_for("Mexico City", "Llamas").code == "MC"


def test_badge_markup_escapes_and_carries_colors():
    html = str(team_badge("London", "Lions"))
    assert "LON" in html and "#A6192E" in html
    assert "<script>" not in str(team_badge("<script>", "x"))
