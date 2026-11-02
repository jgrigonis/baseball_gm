from src.team.colors import TEAM_COLORS, colors_for, contrast, team_badge
from src.league.team_pool import TEAM_POOL


def test_every_pool_team_has_colors():
    for team in TEAM_POOL:
        assert team.key in TEAM_COLORS, team


def test_codes_are_unique():
    codes = [c.code for c in TEAM_COLORS.values()]
    assert len(codes) == len(set(codes))


def test_badge_text_is_readable_on_every_team():
    for c in TEAM_COLORS.values():
        assert contrast(c.primary, c.ink) >= 3, c


def test_unknown_team_gets_stable_colors():
    a = colors_for("Denver", "Beans")
    assert a == colors_for("Denver", "Beans")
    assert a.code == "DEN"
    assert colors_for("Mexico City", "Llamas").code == "MC"


def test_badge_markup_escapes_and_carries_colors():
    html = str(team_badge("London", "Lions"))
    assert "LON" in html and "#A6192E" in html
    assert "<script>" not in str(team_badge("<script>", "x"))


def test_beijing_badge_shows_its_name_in_chinese():
    html = str(team_badge("Beijing", "Dragons"))
    assert ">北京<" in html and "team-badge--long" in html
    # Line scores and the like still use the code
    assert colors_for("Beijing", "Dragons").code == "BEI"


def test_mexico_city_badge_reads_cdmx():
    assert ">CDMX<" in str(team_badge("Mexico City", "Aztecs"))
    assert colors_for("Mexico City", "Aztecs").code == "MEX"
