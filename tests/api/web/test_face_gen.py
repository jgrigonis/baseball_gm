# tests/api/web/test_face_gen.py
"""/face_gen/: build a player face by hand."""

import json

from fastapi.testclient import TestClient

from src.api.main import app
from src.player.face import TRAITS, random_traits

client = TestClient(app)


def test_page_has_a_control_for_every_trait():
    r = client.get("/face_gen/")
    assert r.status_code == 200
    assert "Face Generator" in r.text
    for t in TRAITS:
        assert f'name="{t.key}"' in r.text, t.key


def test_svg_draws_the_traits_and_returns_what_would_be_stored():
    traits = random_traits("p-1")
    r = client.get(
        "/face_gen/svg",
        params={"traits": json.dumps(traits), "age": 33, "team": "Tokyo|Samurai"},
    )
    d = r.json()
    assert d["svg"].startswith("<svg")
    assert [a["age"] for a in d["ages"]] == [22, 30, 38]
    assert d["traits"] == traits
    assert json.loads(d["stored"]) == traits
    assert d["bytes"] == len(d["stored"])
    assert "face-tokyo-" in d["svg"]  # Tokyo's cap logo


def test_svg_cleans_bad_input():
    bad = {"chin": 999, "mouth": "<script>", "skin": "red", "junk": 1}
    d = client.get(
        "/face_gen/svg", params={"traits": json.dumps(bad), "team": "Nowhere|X"}
    ).json()
    assert d["traits"]["chin"] == 12  # clamped to the top of its range
    assert d["traits"]["mouth"] == "flat"
    assert "junk" not in d["traits"]
    assert "<script>" not in d["svg"]
    assert client.get("/face_gen/svg", params={"traits": "not json"}).status_code == 200


def test_random_is_the_players_face_for_an_id():
    assert client.get(
        "/face_gen/random", params={"seed": "p-1"}
    ).json() == random_traits("p-1")
