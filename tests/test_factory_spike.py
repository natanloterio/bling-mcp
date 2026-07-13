import inspect

from mcp.server.fastmcp import FastMCP


def _make(name, params_types):
    def impl(**kwargs):
        return kwargs

    impl.__name__ = name
    impl.__signature__ = inspect.Signature(
        [
            inspect.Parameter(
                p,
                inspect.Parameter.KEYWORD_ONLY,
                annotation=t,
                default=(inspect.Parameter.empty if req else None),
            )
            for p, (t, req) in params_types.items()
        ]
    )
    impl.__annotations__ = {p: t for p, (t, _req) in params_types.items()}
    impl.__doc__ = "spike tool"
    return impl


def test_dynamic_signature_registers_and_schemas():
    mcp = FastMCP("spike")
    fn = _make("bling_spike", {"id": (int, True), "nome": (str, False)})
    mcp.add_tool(fn, name="bling_spike")
    tools = {t.name: t for t in mcp._tool_manager.list_tools()}
    assert "bling_spike" in tools
    schema = tools["bling_spike"].parameters
    assert "id" in schema["properties"]
    assert "nome" in schema["properties"]
    assert schema["properties"]["id"]["type"] == "integer"
    assert "id" in schema.get("required", [])
