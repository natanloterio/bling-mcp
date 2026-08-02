"""Smoke tests: the server registers the full endpoint surface via the factory."""

from pathlib import Path

from bling_mcp.config import BlingConfig
from bling_mcp.server import build_token_store, build_tools, create_server, enabled_endpoints
from bling_mcp.token_store import JsonFileTokenStore, default_store_path
from bling_mcp.tools.registry import ALL_ENDPOINTS, MODULES


class _Cfg:
    account_label = "default"
    modules = None
    api_base_url = "https://api.test/v3"


class FakeClient:
    def get(self, path, params=None):
        return {}

    def post(self, path, json=None, params=None):
        return {}

    def put(self, path, json=None, params=None):
        return {}

    def patch(self, path, json=None, params=None):
        return {}

    def delete(self, path, params=None):
        return None


def _server(config=None):
    return create_server(FakeClient(), config or _Cfg())


def test_registers_all_endpoints_plus_meta():
    names = {t.name for t in _server()._tool_manager.list_tools()}
    assert "bling_list_accounts" in names
    assert len(names) == len(ALL_ENDPOINTS) + 1


def test_all_tools_are_bling_prefixed():
    names = [t.name for t in _server()._tool_manager.list_tools()]
    assert all(n.startswith("bling_") for n in names)


def test_each_tool_has_a_description():
    for tool in _server()._tool_manager.list_tools():
        assert tool.description, f"{tool.name} is missing a description"


def test_legacy_tools_still_present():
    names = {t.name for t in _server()._tool_manager.list_tools()}
    for legacy in (
        "bling_list_produtos",
        "bling_get_produto",
        "bling_list_pedidos_vendas",
        "bling_get_pedido_venda",
        "bling_list_contatos",
    ):
        assert legacy in names, legacy


def test_module_filter_reduces_surface():
    class C(_Cfg):
        modules = ("produtos",)

    names = {t.name for t in _server(C())._tool_manager.list_tools()}
    assert len(names) == len(MODULES["produtos"]) + 1


def test_enabled_endpoints_defaults_to_all():
    assert enabled_endpoints(_Cfg()) == ALL_ENDPOINTS


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


def test_build_token_store_honours_the_configured_path():
    store = build_token_store(make_config(token_store_path="/custom/token.json"))

    assert isinstance(store, JsonFileTokenStore)
    assert store.path == Path("/custom/token.json")


def test_build_token_store_falls_back_to_the_platform_default():
    assert build_token_store(make_config()).path == default_store_path()


def test_build_tools_injects_the_token_store(tmp_path):
    cfg = make_config(token_store_path=str(tmp_path / "token.json"))

    client = build_tools(cfg)

    assert isinstance(client._tokens._store, JsonFileTokenStore)
