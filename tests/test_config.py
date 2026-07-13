"""Tests for configuration loading and validation."""

import pytest

from bling_mcp.config import BlingConfig, ConfigError, load_config

VALID_ENV = {
    "BLING_CLIENT_ID": "abc",
    "BLING_CLIENT_SECRET": "secret",
    "BLING_REFRESH_TOKEN": "refresh",
}


def test_load_config_returns_values_from_env():
    cfg = load_config(VALID_ENV)

    assert cfg.client_id == "abc"
    assert cfg.client_secret == "secret"
    assert cfg.refresh_token == "refresh"


def test_load_config_applies_default_base_url_and_label():
    cfg = load_config(VALID_ENV)

    assert cfg.api_base_url == "https://api.bling.com.br/Api/v3"
    assert cfg.account_label == "default"


def test_load_config_applies_default_token_url():
    # The OAuth token endpoint lives on a different host than the data API.
    cfg = load_config(VALID_ENV)

    assert cfg.token_url == "https://www.bling.com.br/Api/v3/oauth/token"


def test_load_config_overrides_token_url():
    env = {**VALID_ENV, "BLING_TOKEN_URL": "https://example.test/oauth/token"}

    cfg = load_config(env)

    assert cfg.token_url == "https://example.test/oauth/token"


def test_load_config_overrides_base_url_and_label():
    env = {
        **VALID_ENV,
        "BLING_API_BASE_URL": "https://example.test/v3/",
        "BLING_ACCOUNT_LABEL": "loja-x",
    }

    cfg = load_config(env)

    # Trailing slash is stripped so endpoint joining is predictable.
    assert cfg.api_base_url == "https://example.test/v3"
    assert cfg.account_label == "loja-x"


@pytest.mark.parametrize(
    "missing",
    ["BLING_CLIENT_ID", "BLING_CLIENT_SECRET", "BLING_REFRESH_TOKEN"],
)
def test_load_config_raises_when_required_var_missing(missing):
    env = {k: v for k, v in VALID_ENV.items() if k != missing}

    with pytest.raises(ConfigError) as exc:
        load_config(env)

    assert missing in str(exc.value)


def test_load_config_raises_when_required_var_blank():
    env = {**VALID_ENV, "BLING_CLIENT_ID": "   "}

    with pytest.raises(ConfigError):
        load_config(env)


def test_config_is_immutable():
    cfg = load_config(VALID_ENV)

    with pytest.raises(Exception):
        cfg.client_id = "changed"  # type: ignore[misc]


def test_config_is_dataclass_instance():
    assert isinstance(load_config(VALID_ENV), BlingConfig)
