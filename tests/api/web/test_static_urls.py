"""Stylesheets and scripts are linked with a hash of their contents, so a
deploy that changes them makes browsers fetch them again."""

import re

from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.main import app
from src.web.utils import static_url


def test_static_url_is_stamped_with_the_files_hash():
    url = static_url("css/main.css")

    assert re.fullmatch(r"/static/css/main\.css\?v=[0-9a-f]{10}", url)
    assert static_url("css/main.css") == url


def test_missing_file_gets_a_plain_url():
    assert static_url("css/nope.css") == "/static/css/nope.css"


def test_pages_link_the_stamped_stylesheet(db_conn):
    app.dependency_overrides[get_db] = lambda: db_conn
    try:
        html = TestClient(app).get("/signup").text
    finally:
        app.dependency_overrides.clear()

    assert f'href="{static_url("css/main.css")}"' in html


def test_stamped_url_still_serves_the_file():
    r = TestClient(app).get(static_url("css/main.css"))

    assert r.status_code == 200
    assert "--bg" in r.text
