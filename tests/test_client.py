"""Tests for the Bling v3 HTTP client (read-only GET wrapper)."""

import httpx
import pytest

from bling_mcp.client import BlingApiError, BlingClient
from bling_mcp.config import BlingConfig


def make_config(**over):
    base = dict(
        client_id="id",
        client_secret="sec",
        refresh_token="r0",
        api_base_url="https://api.test/v3",
        token_url="https://auth.test/token",
        account_label="default",
    )
    base.update(over)
    return BlingConfig(**base)


class FakeTokens:
    def __init__(self, token="TOK"):
        self.token = token
        self.calls = 0

    def get_access_token(self):
        self.calls += 1
        return self.token


def build_client(responses):
    requests = []

    def handler(request):
        requests.append(request)
        spec = responses[min(len(requests) - 1, len(responses) - 1)]
        return httpx.Response(
            spec.get("status", 200), json=spec.get("json"), request=request
        )

    return httpx.Client(transport=httpx.MockTransport(handler)), requests


def test_get_returns_parsed_json():
    http, _ = build_client([{"json": {"data": [{"id": 1}]}}])
    client = BlingClient(make_config(), FakeTokens(), http)

    assert client.get("produtos") == {"data": [{"id": 1}]}


def test_get_sends_bearer_token_from_token_manager():
    http, reqs = build_client([{"json": {}}])
    tokens = FakeTokens("ABC123")
    client = BlingClient(make_config(), tokens, http)

    client.get("produtos")

    assert reqs[0].headers["Authorization"] == "Bearer ABC123"
    assert tokens.calls == 1


def test_get_joins_base_url_and_path_regardless_of_leading_slash():
    http, reqs = build_client([{"json": {}}, {"json": {}}])
    client = BlingClient(make_config(), FakeTokens(), http)

    client.get("produtos")
    client.get("/pedidos/vendas/123")

    assert str(reqs[0].url) == "https://api.test/v3/produtos"
    assert str(reqs[1].url) == "https://api.test/v3/pedidos/vendas/123"


def test_get_passes_params_and_drops_none_values():
    http, reqs = build_client([{"json": {}}])
    client = BlingClient(make_config(), FakeTokens(), http)

    client.get("produtos", {"pagina": 1, "limite": 100, "nome": None})

    params = reqs[0].url.params
    assert params.get("pagina") == "1"
    assert params.get("limite") == "100"
    assert "nome" not in params


def test_get_raises_bling_api_error_on_non_2xx():
    http, _ = build_client([{"status": 404, "json": {"error": {"type": "NOT_FOUND"}}}])
    client = BlingClient(make_config(), FakeTokens(), http)

    with pytest.raises(BlingApiError) as exc:
        client.get("produtos/999")

    assert exc.value.status_code == 404
