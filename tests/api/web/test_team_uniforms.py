# tests/api/web/test_team_uniforms.py
"""/team_uniforms/: every team's uniform set on one page."""

from fastapi.testclient import TestClient

from src.api.main import app
from src.api.routers.uniforms import all_team_uniforms
from src.api.services.lobby_teams import EXTRA_TEAMS, manifest_teams


def test_every_team_is_listed_with_its_set():
    rows = {r["city"]: r for r in all_team_uniforms()}
    cities = [c for c, _ in manifest_teams()] + [t["city"] for t in EXTRA_TEAMS]
    assert len(rows) == len(cities) == 33
    for city in cities:
        u = rows[city]["uniforms"]
        assert u and u["helmet"].endswith("/helmet.svg"), city


def test_page_renders_without_signing_in():
    r = TestClient(app).get("/team_uniforms/")
    assert r.status_code == 200
    assert "Team Uniforms" in r.text
    assert "img/uniforms/tokyo/helmet.svg" in r.text
    for team in ("Berlin Bears", "Seattle Rain", "Portland Weird"):
        assert team in r.text
    assert "No uniform set yet." not in r.text
