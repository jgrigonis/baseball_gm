# tests/api/web/test_team_uniforms.py
"""/team_uniforms/: every team's uniform set on one page."""

from fastapi.testclient import TestClient

from src.api.main import app
from src.api.routers.uniforms import all_team_uniforms
from src.api.services.lobby_teams import manifest_teams


def test_every_team_is_listed_with_its_set():
    rows = {r["city"]: r for r in all_team_uniforms()}
    for city, _ in manifest_teams():
        u = rows[city]["uniforms"]
        assert u and u["helmet"].endswith("/helmet.svg"), city
    # The 32-team extras are listed even without a set.
    assert rows["Berlin"]["uniforms"] is None
    assert rows["Seattle"]["uniforms"] is None


def test_page_renders_without_signing_in():
    r = TestClient(app).get("/team_uniforms/")
    assert r.status_code == 200
    assert "Team Uniforms" in r.text
    assert "img/uniforms/tokyo/helmet.svg" in r.text
    assert "Berlin Bears" in r.text
    assert "No uniform set yet." in r.text
