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
    def __init__(self, token="TOK", refreshed="TOK2"):
        self.token = token
        self.refreshed = refreshed
        self.calls = 0
        self.forced = 0

    def get_access_token(self):
        self.calls += 1
        return self.token

    def force_refresh(self):
        self.forced += 1
        self.token = self.refreshed
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


def test_post_sends_json_body_and_content_type():
    http, reqs = build_client([{"status": 201, "json": {"data": {"id": 9}}}])
    client = BlingClient(make_config(), FakeTokens(), http)

    out = client.post("produtos", json={"nome": "X"})

    assert reqs[0].method == "POST"
    assert str(reqs[0].url) == "https://api.test/v3/produtos"
    assert "application/json" in reqs[0].headers["content-type"]
    assert b'"nome"' in reqs[0].content
    assert out == {"data": {"id": 9}}


def test_delete_204_returns_none():
    http, reqs = build_client([{"status": 204}])
    client = BlingClient(make_config(), FakeTokens(), http)

    assert client.delete("produtos/5") is None
    assert reqs[0].method == "DELETE"


def test_put_and_patch_use_correct_verb():
    http, reqs = build_client([{"json": {}}, {"json": {}}])
    client = BlingClient(make_config(), FakeTokens(), http)

    client.put("logisticas/1", json={"a": 1})
    client.patch("produtos/1", json={"b": 2})

    assert [r.method for r in reqs] == ["PUT", "PATCH"]


def test_write_error_raises_bling_api_error():
    http, _ = build_client([{"status": 422, "json": {"error": "bad"}}])
    client = BlingClient(make_config(), FakeTokens(), http)

    with pytest.raises(BlingApiError) as exc:
        client.post("produtos", json={})

    assert exc.value.status_code == 422


def test_401_forces_a_refresh_and_retries_once():
    http, reqs = build_client([{"status": 401, "json": {}}, {"json": {"data": [1]}}])
    tokens = FakeTokens("STALE", refreshed="FRESH")
    client = BlingClient(make_config(), tokens, http)

    assert client.get("produtos") == {"data": [1]}
    assert tokens.forced == 1
    assert len(reqs) == 2
    assert reqs[0].headers["Authorization"] == "Bearer STALE"
    assert reqs[1].headers["Authorization"] == "Bearer FRESH"


def test_second_401_raises_bling_api_error():
    http, reqs = build_client([{"status": 401, "json": {"error": "unauthorized"}}])
    tokens = FakeTokens()
    client = BlingClient(make_config(), tokens, http)

    with pytest.raises(BlingApiError) as exc:
        client.get("produtos")

    assert exc.value.status_code == 401
    assert tokens.forced == 1  # retried exactly once, not in a loop
    assert len(reqs) == 2


def test_successful_request_never_forces_a_refresh():
    http, _ = build_client([{"json": {}}])
    tokens = FakeTokens()
    client = BlingClient(make_config(), tokens, http)

    client.get("produtos")

    assert tokens.forced == 0


def test_403_and_500_do_not_retry():
    for status in (403, 500):
        http, reqs = build_client([{"status": status, "json": {}}])
        tokens = FakeTokens()
        client = BlingClient(make_config(), tokens, http)

        with pytest.raises(BlingApiError):
            client.get("produtos")

        assert tokens.forced == 0
        assert len(reqs) == 1


def test_retry_replays_method_body_and_params():
    http, reqs = build_client([{"status": 401, "json": {}}, {"status": 201, "json": {}}])
    client = BlingClient(make_config(), FakeTokens(), http)

    client.post("produtos", json={"nome": "X"}, params={"loja": 7})

    assert [r.method for r in reqs] == ["POST", "POST"]
    assert b'"nome"' in reqs[1].content
    assert reqs[1].url.params.get("loja") == "7"


def test_retry_applies_to_delete_too():
    http, reqs = build_client([{"status": 401, "json": {}}, {"status": 204}])
    client = BlingClient(make_config(), FakeTokens(), http)

    assert client.delete("produtos/5") is None
    assert [r.method for r in reqs] == ["DELETE", "DELETE"]
