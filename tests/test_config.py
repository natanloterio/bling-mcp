"""Tests for configuration loading and validation."""

import pytest

from bling_mcp.config import BlingConfig, ConfigError, load_config


def _base_env(**extra):
    env = {
        "BLING_CLIENT_ID": "a",
        "BLING_CLIENT_SECRET": "b",
        "BLING_REFRESH_TOKEN": "c",
    }
    env.update(extra)
    return env


def test_modules_none_when_unset():
    assert load_config(_base_env()).modules is None


def test_modules_parsed_and_trimmed():
    cfg = load_config(_base_env(BLING_MODULES=" produtos , pedidos "))
    assert cfg.modules == ("produtos", "pedidos")

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


def test_token_store_path_defaults_to_none():
    assert load_config(_base_env()).token_store_path is None


def test_token_store_path_is_read_from_env():
    cfg = load_config(_base_env(BLING_TOKEN_STORE="/custom/token.json"))
    assert cfg.token_store_path == "/custom/token.json"


def test_blank_token_store_path_is_treated_as_unset():
    cfg = load_config(_base_env(BLING_TOKEN_STORE="   "))
    assert cfg.token_store_path is None


# --- OAuth callback port -----------------------------------------------------------
def test_oauth_callback_port_defaults_to_8765():
    cfg = load_config(_base_env())
    assert cfg.oauth_callback_port == 8765


def test_oauth_callback_port_is_read_from_env():
    cfg = load_config({**_base_env(), "BLING_OAUTH_CALLBACK_PORT": "9001"})
    assert cfg.oauth_callback_port == 9001


def test_oauth_callback_port_rejects_non_numeric_values():
    with pytest.raises(ConfigError, match="BLING_OAUTH_CALLBACK_PORT"):
        load_config({**_base_env(), "BLING_OAUTH_CALLBACK_PORT": "abc"})


def test_oauth_callback_port_rejects_out_of_range_values():
    with pytest.raises(ConfigError, match="BLING_OAUTH_CALLBACK_PORT"):
        load_config({**_base_env(), "BLING_OAUTH_CALLBACK_PORT": "70000"})


# --- OAuth redirect host -------------------------------------------------------------
def test_oauth_redirect_host_defaults_to_localhost():
    assert load_config(_base_env()).oauth_redirect_host == "localhost"


def test_oauth_redirect_host_is_read_and_trimmed_from_env():
    cfg = load_config({**_base_env(), "BLING_OAUTH_REDIRECT_HOST": " 127.0.0.1 "})
    assert cfg.oauth_redirect_host == "127.0.0.1"


def test_oauth_redirect_host_rejects_a_value_with_a_scheme_or_path():
    with pytest.raises(ConfigError, match="BLING_OAUTH_REDIRECT_HOST"):
        load_config({**_base_env(), "BLING_OAUTH_REDIRECT_HOST": "http://x/"})


# --- JWT opt-in (Bling migração JWT) --------------------------------------------------
def test_enable_jwt_defaults_to_true():
    assert load_config(_base_env()).enable_jwt is True


@pytest.mark.parametrize("raw", ["0", "false", "no", "off", "False"])
def test_enable_jwt_can_be_disabled(raw):
    assert load_config({**_base_env(), "BLING_ENABLE_JWT": raw}).enable_jwt is False


@pytest.mark.parametrize("raw", ["1", "true", "yes", "on", "TRUE"])
def test_enable_jwt_accepts_truthy_spellings(raw):
    assert load_config({**_base_env(), "BLING_ENABLE_JWT": raw}).enable_jwt is True


def test_enable_jwt_rejects_garbage():
    with pytest.raises(ConfigError, match="BLING_ENABLE_JWT"):
        load_config({**_base_env(), "BLING_ENABLE_JWT": "maybe"})
