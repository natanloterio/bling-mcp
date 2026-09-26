"""Configuration loading and validation for the Bling MCP server.

Configuration is read from a string-keyed mapping (typically ``os.environ``) and
validated up front so the server fails fast with a clear message when a required
credential is missing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

DEFAULT_API_BASE_URL = "https://api.bling.com.br/Api/v3"
# The OAuth token endpoint lives on www.bling.com.br, a different host than the
# data API base above.
DEFAULT_TOKEN_URL = "https://www.bling.com.br/Api/v3/oauth/token"
DEFAULT_ACCOUNT_LABEL = "default"
# Loopback port the in-chat re-authorization listens on for Bling's redirect.
# Must match the "link de redirecionamento" registered in the Bling app.
DEFAULT_OAUTH_CALLBACK_PORT = 8765
# Host name written into the redirect URI (the listener always binds 127.0.0.1).
# Switch to "127.0.0.1" where "localhost" resolves only to IPv6.
DEFAULT_OAUTH_REDIRECT_HOST = "localhost"
_PORT_RANGE = range(1, 65536)
_HOST_FORBIDDEN = ("/", ":", " ", "?", "#")

_REQUIRED = ("BLING_CLIENT_ID", "BLING_CLIENT_SECRET", "BLING_REFRESH_TOKEN")


class ConfigError(ValueError):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class BlingConfig:
    """Immutable, validated configuration for the Bling MCP server."""

    client_id: str
    client_secret: str
    refresh_token: str
    api_base_url: str = DEFAULT_API_BASE_URL
    token_url: str = DEFAULT_TOKEN_URL
    account_label: str = DEFAULT_ACCOUNT_LABEL
    modules: tuple[str, ...] | None = None
    token_store_path: str | None = None
    oauth_callback_port: int = DEFAULT_OAUTH_CALLBACK_PORT
    oauth_redirect_host: str = DEFAULT_OAUTH_REDIRECT_HOST


def load_config(env: Mapping[str, str]) -> BlingConfig:
    """Build a :class:`BlingConfig` from an environment mapping.

    Raises :class:`ConfigError` if any required variable is missing or blank.
    """
    missing = [
        name for name in _REQUIRED if not (env.get(name) or "").strip()
    ]
    if missing:
        raise ConfigError(
            "Missing or blank required configuration: " + ", ".join(missing)
        )

    base_url = (env.get("BLING_API_BASE_URL") or DEFAULT_API_BASE_URL).strip()
    token_url = (env.get("BLING_TOKEN_URL") or DEFAULT_TOKEN_URL).strip()
    label = (env.get("BLING_ACCOUNT_LABEL") or DEFAULT_ACCOUNT_LABEL).strip()
    raw_modules = (env.get("BLING_MODULES") or "").strip()
    modules = tuple(m.strip() for m in raw_modules.split(",") if m.strip()) or None
    store_path = (env.get("BLING_TOKEN_STORE") or "").strip() or None
    callback_port = _parse_port(env.get("BLING_OAUTH_CALLBACK_PORT"))
    redirect_host = _parse_host(env.get("BLING_OAUTH_REDIRECT_HOST"))

    return BlingConfig(
        client_id=env["BLING_CLIENT_ID"].strip(),
        client_secret=env["BLING_CLIENT_SECRET"].strip(),
        refresh_token=env["BLING_REFRESH_TOKEN"].strip(),
        api_base_url=base_url.rstrip("/"),
        token_url=token_url,
        account_label=label,
        modules=modules,
        token_store_path=store_path,
        oauth_callback_port=callback_port,
        oauth_redirect_host=redirect_host,
    )


def _parse_port(raw: str | None) -> int:
    """Parse ``BLING_OAUTH_CALLBACK_PORT``; blank means the default."""
    text = (raw or "").strip()
    if not text:
        return DEFAULT_OAUTH_CALLBACK_PORT
    try:
        port = int(text)
    except ValueError as exc:
        raise ConfigError(
            f"BLING_OAUTH_CALLBACK_PORT must be an integer, got {text!r}"
        ) from exc
    if port not in _PORT_RANGE:
        raise ConfigError(f"BLING_OAUTH_CALLBACK_PORT must be 1-65535, got {port}")
    return port


def _parse_host(raw: str | None) -> str:
    """Parse ``BLING_OAUTH_REDIRECT_HOST``: a bare host name or IP, no scheme/port/path."""
    text = (raw or "").strip()
    if not text:
        return DEFAULT_OAUTH_REDIRECT_HOST
    if any(ch in text for ch in _HOST_FORBIDDEN):
        raise ConfigError(
            f"BLING_OAUTH_REDIRECT_HOST must be a bare host name or IP, got {text!r}"
        )
    return text
