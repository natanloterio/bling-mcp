"""Tests for the one-time OAuth authorization-code helper."""

import base64
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

import bling_mcp.authorize as authorize_module
from bling_mcp.auth import AuthError
from bling_mcp.authorize import (
    DEFAULT_AUTHORIZE_URL,
    build_authorize_url,
    exchange_code,
    main,
)


def build_http(responses):
    requests = []

    def handler(request):
        requests.append(request)
        spec = responses[min(len(requests) - 1, len(responses) - 1)]
        return httpx.Response(
            spec.get("status", 200), json=spec.get("json"), request=request
        )

    return httpx.Client(transport=httpx.MockTransport(handler)), requests


def test_build_authorize_url_includes_required_params():
    url = build_authorize_url("CID", state="xyz")
    query = parse_qs(urlparse(url).query)

    assert url.startswith(DEFAULT_AUTHORIZE_URL)
    assert query["response_type"] == ["code"]
    assert query["client_id"] == ["CID"]
    assert query["state"] == ["xyz"]


def test_build_authorize_url_includes_redirect_uri_when_given():
    url = build_authorize_url("CID", redirect_uri="https://app.test/cb")
    assert parse_qs(urlparse(url).query)["redirect_uri"] == ["https://app.test/cb"]


def test_build_authorize_url_omits_redirect_uri_when_absent():
    url = build_authorize_url("CID")
    assert "redirect_uri" not in parse_qs(urlparse(url).query)


def test_exchange_code_uses_basic_auth_and_authorization_code_grant():
    http, reqs = build_http(
        [{"json": {"access_token": "AT", "refresh_token": "RT", "expires_in": 21600}}]
    )

    result = exchange_code("CID", "SEC", "THECODE", http)

    req = reqs[0]
    assert req.method == "POST"
    decoded = base64.b64decode(req.headers["Authorization"].split(" ", 1)[1]).decode()
    assert decoded == "CID:SEC"
    body = req.content.decode()
    assert "grant_type=authorization_code" in body
    assert "code=THECODE" in body
    assert result["refresh_token"] == "RT"


def test_exchange_code_raises_on_failure():
    http, _ = build_http([{"status": 400, "json": {"error": "invalid_grant"}}])

    with pytest.raises(AuthError):
        exchange_code("CID", "SEC", "bad-code", http)


# --- CLI (main) ----------------------------------------------------------------
def test_main_url_prints_authorize_url(capsys):
    rc = main(["url", "--client-id", "CID", "--state", "s"])
    out = capsys.readouterr().out.strip()

    assert rc == 0
    assert out.startswith(DEFAULT_AUTHORIZE_URL)
    assert "client_id=CID" in out


def test_main_url_requires_client_id(monkeypatch):
    monkeypatch.delenv("BLING_CLIENT_ID", raising=False)
    with pytest.raises(SystemExit):
        main(["url"])


def test_main_exchange_refresh_only_prints_token(monkeypatch, capsys):
    monkeypatch.setattr(
        authorize_module, "exchange_code", lambda *a, **k: {"refresh_token": "RT"}
    )
    rc = main(
        ["exchange", "--client-id", "CID", "--client-secret", "SEC", "--code", "C",
         "--refresh-only"]
    )

    assert rc == 0
    assert capsys.readouterr().out.strip() == "RT"


def test_main_exchange_prints_full_json(monkeypatch, capsys):
    monkeypatch.setattr(
        authorize_module,
        "exchange_code",
        lambda *a, **k: {"refresh_token": "RT", "access_token": "AT"},
    )
    rc = main(["exchange", "--client-id", "CID", "--client-secret", "SEC", "--code", "C"])

    assert rc == 0
    assert '"refresh_token": "RT"' in capsys.readouterr().out


def test_main_exchange_requires_credentials(monkeypatch):
    monkeypatch.delenv("BLING_CLIENT_ID", raising=False)
    monkeypatch.delenv("BLING_CLIENT_SECRET", raising=False)
    with pytest.raises(SystemExit):
        main(["exchange", "--code", "C"])


def test_exchange_code_includes_redirect_uri_when_given():
    http, reqs = build_http([{"json": {"access_token": "AT", "refresh_token": "RT"}}])

    exchange_code("CID", "SEC", "C", http, redirect_uri="http://localhost:8765/callback")

    assert parse_qs(reqs[0].content.decode())["redirect_uri"] == ["http://localhost:8765/callback"]


def test_exchange_code_omits_redirect_uri_when_absent():
    http, reqs = build_http([{"json": {"access_token": "AT", "refresh_token": "RT"}}])

    exchange_code("CID", "SEC", "C", http)

    assert "redirect_uri" not in parse_qs(reqs[0].content.decode())


# --- JWT opt-in (Bling migração JWT) --------------------------------------------------
def test_exchange_code_sends_the_jwt_header_when_asked():
    http, reqs = build_http([{"json": {"access_token": "AT", "refresh_token": "RT"}}])

    exchange_code("CID", "SEC", "C", http, enable_jwt=True)

    assert reqs[0].headers["enable-jwt"] == "1"


def test_exchange_code_omits_the_jwt_header_by_default():
    http, reqs = build_http([{"json": {"access_token": "AT", "refresh_token": "RT"}}])

    exchange_code("CID", "SEC", "C", http)

    assert "enable-jwt" not in reqs[0].headers


def test_main_exchange_requests_a_jwt_unless_told_otherwise(monkeypatch):
    seen = []
    monkeypatch.setattr(
        authorize_module, "exchange_code",
        lambda *a, **k: seen.append(k) or {"refresh_token": "RT"},
    )

    main(["exchange", "--client-id", "CID", "--client-secret", "SEC", "--code", "C"])
    main(["exchange", "--client-id", "CID", "--client-secret", "SEC", "--code", "C", "--opaque"])

    assert seen[0]["enable_jwt"] is True
    assert seen[1]["enable_jwt"] is False
