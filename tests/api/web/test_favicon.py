# tests/api/web/test_favicon.py
"""The baseball tab icon: every page links it, and /favicon.ico answers."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.main import app

TEMPLATES = Path(__file__).resolve().parents[3] / "src" / "web" / "templates"


@pytest.fixture
def client():
    return TestClient(app)


def test_icon_files_are_served(client):
    svg = client.get("/static/img/favicon.svg")
    assert svg.status_code == 200
    assert svg.headers["content-type"].startswith("image/svg+xml")
    assert client.get("/static/img/apple-touch-icon.png").status_code == 200


def test_favicon_ico_answers(client):
    r = client.get("/favicon.ico")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"


@pytest.mark.parametrize(
    "path", sorted(p for p in TEMPLATES.rglob("*.html") if "<head>" in p.read_text())
)
def test_every_page_head_links_the_icon(path):
    assert 'href="/static/img/favicon.svg"' in path.read_text()
