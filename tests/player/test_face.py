# tests/player/test_face.py
"""Player faces (src/player/face.py): stable per player, dressed by team,
aged by age, and every team's cap logo is measured."""

import re
from xml.etree import ElementTree

from src.player.face import (
    UNIFORMS_DIR,
    _logo_boxes,
    cap_parts,
    face_svg,
    player_face,
    team_cap,
)


def _parses(svg: str):
    return ElementTree.fromstring(svg)


def test_same_player_always_gets_the_same_face():
    assert face_svg("p-1", 27, "London", "Lions") == face_svg(
        "p-1", 27, "London", "Lions"
    )


def test_different_players_get_different_faces():
    faces = {face_svg(f"p-{i}", 27, "London", "Lions") for i in range(30)}
    assert len(faces) == 30


def test_face_is_valid_svg_for_every_team():
    for slug in sorted(
        p.name for p in UNIFORMS_DIR.iterdir() if (p / "cap.svg").exists()
    ):
        cap = cap_parts(slug)
        assert cap is not None, slug
        assert cap.logo, slug
    from src.team.colors import TEAM_COLORS

    for city, mascot in TEAM_COLORS:
        _parses(face_svg("p-7", 30, city, mascot))


def test_every_cap_logo_is_measured():
    """A new team needs `node scripts/measure_cap_logos.js` run."""
    boxes = _logo_boxes()
    for p in UNIFORMS_DIR.iterdir():
        if (p / "cap.svg").exists():
            assert p.name in boxes, f"{p.name}: run node scripts/measure_cap_logos.js"


def test_a_trade_changes_the_cap_but_not_the_face():
    london = face_svg("p-3", 28, "London", "Lions")
    tokyo = face_svg("p-3", 28, "Tokyo", "Samurai")
    assert london != tokyo
    assert team_cap("London", "Lions").crown in london
    assert team_cap("Tokyo", "Samurai").crown in tokyo
    # Without the cap and jersey, the drawings match: same eyes.
    eyes = lambda s: re.findall(r'<ellipse[^>]*fill="#f4efe6"/>', s)
    assert eyes(london) == eyes(tokyo)


def test_logo_ids_are_prefixed_by_team():
    cap = cap_parts("dublin")
    assert 'id="face-dublin-shamrock"' in cap.logo
    assert 'href="#face-dublin-shamrock"' in cap.logo


def test_free_agent_wears_a_plain_cap():
    cap = team_cap("—", "")
    assert not cap.logo and not cap.code
    _parses(face_svg("p-4", 31, "—", ""))


def test_team_without_uniforms_shows_its_code():
    cap = team_cap("Denver", "Test")
    assert cap.code and not cap.logo
    assert cap.code in face_svg("p-5", 25, "Denver", "Test")


def test_hair_grays_with_age():
    from src.player.face import HAIR, default_traits

    t = default_traits() | {"hair": HAIR[0], "sideburns": 8, "gray_rate": 1.4}
    assert HAIR[0] in face_svg("p", 22, "London", "Lions", t)
    assert HAIR[0] not in face_svg("p", 40, "London", "Lions", t)


def test_every_option_and_slider_end_draws():
    """Every option and both ends of every slider draw valid SVG."""
    from src.player.face import TRAITS, default_traits

    for trait in TRAITS:
        values = (
            trait.options
            if trait.kind in ("choice", "color")
            else (True, False)
            if trait.kind == "bool"
            else (trait.lo, trait.hi)
        )
        for v in values:
            _parses(
                face_svg("p", 30, "Tokyo", "Samurai", default_traits() | {trait.key: v})
            )


def test_sideburns_show_at_any_length():
    from src.player.face import default_traits

    t = default_traits() | {"hair": "#1b1512"}
    assert "#1b1512" not in face_svg(
        "p", 25, "Rome", "Gladiators", t | {"sideburns": 0}
    )
    assert "#1b1512" in face_svg("p", 25, "Rome", "Gladiators", t | {"sideburns": 1})


def test_player_face_markup():
    html = str(
        player_face(
            {
                "player_id": "p-9",
                "age": 26,
                "team_city": "Rome",
                "team_mascot": "Gladiators",
            }
        )
    )
    assert html.startswith('<button type="button" class="player-face player-face--lg"')
    # Clicking opens the same face bigger in a dialog
    assert '<dialog class="face-zoom"' in html
    assert html.count("<svg") == 2


def test_zoom_caption_names_the_player_and_escapes():
    html = str(
        player_face(
            {
                "player_id": "p",
                "first_name": "Al",
                "last_name": "<b>",
                "team_city": "Rome",
                "team_mascot": "Gladiators",
            }
        )
    )
    assert "Al &lt;b&gt; · Rome Gladiators" in html


def test_grin_shows_teeth():
    from src.player.face import default_traits

    svg = face_svg("p", 27, "Rome", "Gladiators", default_traits() | {"mouth": "grin"})
    assert 'clip-path="url(#grin' in svg


def test_stored_traits_draw_the_same_face_as_random_ones():
    from src.player.face import random_traits

    t = random_traits("p-1")
    assert face_svg("other-id", 30, "Rome", "Gladiators", t) == face_svg(
        "p-1", 30, "Rome", "Gladiators"
    )


def test_clean_traits_fills_missing_and_drops_bad_values():
    from src.player.face import TRAITS, clean_traits, default_traits

    assert clean_traits({}) == default_traits()
    t = clean_traits({"face_width": "nan", "eye_black": "on", "hair": "#000000"})
    assert t["face_width"] == default_traits()["face_width"]
    assert t["eye_black"] is True
    assert t["hair"] == default_traits()["hair"]
    assert set(t) == {tr.key for tr in TRAITS}


def test_random_traits_stay_in_range():
    from src.player.face import clean_traits, random_traits

    for i in range(200):
        t = random_traits(f"p-{i}")
        assert clean_traits(t) == t
