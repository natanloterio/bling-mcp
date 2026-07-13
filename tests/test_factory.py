"""Tests for the endpoint -> MCP tool factory."""

import inspect

from bling_mcp.tools.factory import build_tool
from bling_mcp.tools.spec import Endpoint, Param


class FakeClient:
    def __init__(self):
        self.calls = []

    def get(self, path, params=None):
        self.calls.append(("GET", path, params, None))
        return {"g": 1}

    def post(self, path, json=None, params=None):
        self.calls.append(("POST", path, params, json))
        return {"p": 1}

    def put(self, path, json=None, params=None):
        self.calls.append(("PUT", path, params, json))
        return {"pu": 1}

    def patch(self, path, json=None, params=None):
        self.calls.append(("PATCH", path, params, json))
        return {"pa": 1}

    def delete(self, path, params=None):
        self.calls.append(("DELETE", path, params, None))
        return None


def test_get_one_formats_path_and_calls_get():
    c = FakeClient()
    fn = build_tool(
        Endpoint(
            "get_produto",
            "GET",
            "produtos/{idProduto}",
            "d",
            path_params=(Param("idProduto", int),),
        ),
        c,
    )
    assert fn.__name__ == "bling_get_produto"
    out = fn(idProduto=7)
    assert c.calls == [("GET", "produtos/7", None, None)]
    assert out == {"g": 1}
    sig = inspect.signature(fn)
    assert sig.parameters["idProduto"].annotation is int
    assert sig.parameters["idProduto"].default is inspect.Parameter.empty


def test_list_passes_query_params_dropping_unset():
    c = FakeClient()
    fn = build_tool(
        Endpoint(
            "list_produtos",
            "GET",
            "produtos",
            "d",
            query_params=(Param("pagina", int), Param("nome", str)),
        ),
        c,
    )
    fn(pagina=2)
    assert c.calls == [("GET", "produtos", {"pagina": 2, "nome": None}, None)]


def test_create_passes_body():
    c = FakeClient()
    fn = build_tool(Endpoint("create_produto", "POST", "produtos", "d", has_body=True), c)
    fn(body={"nome": "X"})
    assert c.calls == [("POST", "produtos", None, {"nome": "X"})]


def test_put_and_patch_dispatch_to_verb():
    c = FakeClient()
    put = build_tool(
        Endpoint(
            "update_logistica",
            "PUT",
            "logisticas/{id}",
            "d",
            path_params=(Param("id", int),),
            has_body=True,
        ),
        c,
    )
    patch = build_tool(
        Endpoint(
            "update_produto",
            "PATCH",
            "produtos/{id}",
            "d",
            path_params=(Param("id", int),),
            has_body=True,
        ),
        c,
    )
    put(id=1, body={"a": 1})
    patch(id=2, body={"b": 2})
    assert c.calls[0][0] == "PUT"
    assert c.calls[1][0] == "PATCH"


def test_delete_calls_delete_verb():
    c = FakeClient()
    fn = build_tool(
        Endpoint(
            "delete_produto",
            "DELETE",
            "produtos/{idProduto}",
            "d",
            path_params=(Param("idProduto", int),),
        ),
        c,
    )
    assert fn(idProduto=3) is None
    assert c.calls == [("DELETE", "produtos/3", None, None)]
