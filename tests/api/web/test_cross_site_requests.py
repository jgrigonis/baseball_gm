# tests/api/web/test_cross_site_requests.py
"""
Forms and fetches that change something must come from the site's own
pages (the Origin check in main.py), so another site, even a subdomain of
the same domain, can't act as a signed-in GM or sign a visitor in.
"""

import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.main import app
from src.config import settings

PASSWORD = "correct horse battery"
SITE = "https://baseball.gbros.us"


@pytest.fixture
def client(db_conn):
    app.dependency_overrides[get_db] = lambda: db_conn
    yield TestClient(app, follow_redirects=False)
    app.dependency_overrides.clear()


@pytest.fixture
def deployed():
    with patch.object(settings, "public_base_url", SITE):
        yield


def _register(client, **headers):
    return client.post(
        "/auth/register",
        data={
            "username": "gm_" + uuid.uuid4().hex[:10],
            "password": PASSWORD,
            "confirm": PASSWORD,
        },
        headers=headers,
    )


class TestDeployed:
    def test_own_pages_pass(self, client, deployed):
        assert _register(client, origin=SITE).status_code == 302

    def test_origin_ignores_case(self, client, deployed):
        assert _register(client, origin=SITE.upper()).status_code == 302

    @pytest.mark.parametrize(
        "origin",
        [
            "https://evil.example.com",
            "https://other.gbros.us",  # same site as far as SameSite goes
            "http://baseball.gbros.us",  # not HTTPS
            "https://baseball.gbros.us:8443",
            "null",
        ],
    )
    def test_other_origins_are_refused(self, client, deployed, origin):
        resp = _register(client, origin=origin)

        assert resp.status_code == 403
        assert "set-cookie" not in resp.headers

    def test_sign_in_from_another_site_is_refused(self, client, deployed):
        resp = client.post(
            "/auth/login",
            data={"username": "someone", "password": PASSWORD},
            headers={"origin": "https://evil.example.com"},
        )

        assert resp.status_code == 403

    def test_referer_is_checked_without_origin(self, client, deployed):
        assert _register(client, referer=f"{SITE}/").status_code == 302
        assert (
            _register(client, referer="https://evil.example.com/page").status_code
            == 403
        )

    def test_signed_in_fetch_from_another_site_is_refused(self, client, deployed):
        _register(client)
        resp = client.post(
            "/auth/logout",
            headers={"origin": "https://evil.example.com", "accept": "*/*"},
        )

        assert resp.status_code == 403
        assert resp.json() == {"detail": "That request came from another site."}

    def test_form_post_gets_an_error_page(self, client, deployed):
        resp = _register(client, origin="https://evil.example.com", accept="text/html")

        assert resp.status_code == 403
        assert "text/html" in resp.headers["content-type"]

    def test_page_loads_from_links_on_other_sites_pass(self, client, deployed):
        resp = client.get("/", headers={"referer": "https://evil.example.com/"})

        assert resp.status_code == 200

    def test_no_origin_or_referer_passes(self, client, deployed):
        # Not a browser, so no victim's cookie to borrow.
        assert _register(client).status_code == 302


class TestDeveloping:
    def test_checks_against_the_requested_address(self, client):
        assert _register(client, origin="http://testserver").status_code == 302
        assert _register(client, origin="http://localhost:5173").status_code == 403

    def test_local_server_with_the_deployed_settings(self, db_conn, deployed):
        # e.g. the deployed .env, browsing the local server at 127.0.0.1.
        app.dependency_overrides[get_db] = lambda: db_conn
        local = TestClient(
            app, base_url="http://127.0.0.1:8000", follow_redirects=False
        )

        assert _register(local, origin="http://127.0.0.1:8000").status_code == 302
        assert _register(local, origin="http://127.0.0.1:9999").status_code == 403

    def test_cors_origins_are_allowed(self, client):
        with patch.object(settings, "cors_origins", ["http://localhost:5173"]):
            resp = _register(client, origin="http://localhost:5173")

        assert resp.status_code == 302


def test_no_cors_by_default(client):
    resp = client.options(
        "/auth/logout",
        headers={
            "origin": "http://localhost:5173",
            "access-control-request-method": "POST",
        },
    )

    assert "access-control-allow-origin" not in resp.headers


@pytest.mark.parametrize("path", ["/", "/signup", "/auth/forgot"])
def test_sign_in_pages_keep_their_origin_on_posts(client, path):
    # no-referrer would make browsers send "Origin: null", which is refused.
    html = client.get(path).text

    assert '<meta name="referrer" content="same-origin">' in html
