"""Tests for the three re-authorization MCP tools (thin wrappers over ReauthService)."""

import httpx

from bling_mcp.auth import TokenManager
from bling_mcp.config import BlingConfig
from bling_mcp.reauth import ReauthService
from bling_mcp.tools.auth_tools import build_auth_tools

TOKENS = {"access_token": "AT-NEW", "refresh_token": "r-new", "expires_in": 21600}


def make_service():
    cfg = BlingConfig(
        client_id="id", client_secret="sec", refresh_token="r0",
        token_url="https://auth.test/token", oauth_callback_port=0,
    )
    http = httpx.Client(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, json=TOKENS, request=req))
    )
    tm = TokenManager(cfg, http, clock=lambda: 1000.0)
    return ReauthService(cfg, http, tm, clock=lambda: 1000.0), tm


def by_name(tools):
    return {t.__name__: t for t in tools}


def test_builds_exactly_the_three_tools_with_bling_names():
    svc, _ = make_service()
    try:
        names = set(by_name(build_auth_tools(svc)))
    finally:
        svc.close()
    assert names == {"bling_authorize", "bling_auth_status", "bling_authorize_with_code"}


def test_every_tool_has_a_docstring_mentioning_the_30_day_expiry_or_its_role():
    svc, _ = make_service()
    try:
        tools = build_auth_tools(svc)
    finally:
        svc.close()
    for tool in tools:
        assert tool.__doc__ and len(tool.__doc__.strip()) > 40, tool.__name__


def test_authorize_returns_the_link_and_status_follows():
    svc, _ = make_service()
    try:
        tools = by_name(build_auth_tools(svc))
        result = tools["bling_authorize"]()
        status = tools["bling_auth_status"]()
    finally:
        svc.close()

    assert result["authorize_url"].startswith("https://www.bling.com.br/")
    assert status["status"] == "pending"


def test_authorize_with_code_installs_the_tokens():
    svc, tm = make_service()
    try:
        tools = by_name(build_auth_tools(svc))
        result = tools["bling_authorize_with_code"](code="C1")
    finally:
        svc.close()

    assert result["status"] == "completed"
    assert tm.get_access_token() == "AT-NEW"


def test_authorize_with_code_exposes_a_required_string_code_in_its_schema():
    from mcp.server.fastmcp import FastMCP

    svc, _ = make_service()
    try:
        mcp = FastMCP("t")
        for tool in build_auth_tools(svc):
            mcp.add_tool(tool, name=tool.__name__)
        schema = {t.name: t.parameters for t in mcp._tool_manager.list_tools()}
    finally:
        svc.close()

    code = schema["bling_authorize_with_code"]
    assert code["properties"]["code"]["type"] == "string"
    assert code["required"] == ["code"]
    assert schema["bling_authorize"].get("properties", {}) == {}
