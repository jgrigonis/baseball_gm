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
    # Some player among the first few has visible hair: compare his sideburns.
    def sideburn(svg):
        return re.search(
            r'<path d="M[\d.]+ 46 L[^"]*" fill="(#[0-9a-f]{6})"', svg
        ).group(1)

    young = [sideburn(face_svg(f"p-{i}", 22, "London", "Lions")) for i in range(10)]
    old = [sideburn(face_svg(f"p-{i}", 40, "London", "Lions")) for i in range(10)]
    assert young != old


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
    assert html.startswith('<span class="player-face player-face--lg"><svg')
