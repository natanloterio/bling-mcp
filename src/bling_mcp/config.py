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

    return BlingConfig(
        client_id=env["BLING_CLIENT_ID"].strip(),
        client_secret=env["BLING_CLIENT_SECRET"].strip(),
        refresh_token=env["BLING_REFRESH_TOKEN"].strip(),
        api_base_url=base_url.rstrip("/"),
        token_url=token_url,
        account_label=label,
    )
