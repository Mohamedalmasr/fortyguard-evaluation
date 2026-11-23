import importlib.util
from pathlib import Path

import dotenv
import pytest


CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.py"
ENV_NAMES = (
    "FORTYGUARD_API_KEY",
    "FORTYGUARD_API_URL",
    "FORTYGUARD_MCP_URL",
)


def load_config(monkeypatch, values):
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: False)

    spec = importlib.util.spec_from_file_location("config_under_test", CONFIG_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_config_loads_synthetic_environment_values(monkeypatch):
    values = {
        "FORTYGUARD_API_KEY": "synthetic-key",
        "FORTYGUARD_API_URL": "https://api.example.invalid",
        "FORTYGUARD_MCP_URL": "https://mcp.example.invalid",
    }

    config = load_config(monkeypatch, values)

    assert config.API_KEY == "synthetic-key"
    assert config.API_URL == "https://api.example.invalid"
    assert config.MCP_URL == "https://mcp.example.invalid"


@pytest.mark.parametrize(
    ("invalid_name", "invalid_value", "error_message"),
    [
        ("FORTYGUARD_API_KEY", None, "FORTYGUARD_API_KEY is missing from .env"),
        ("FORTYGUARD_API_KEY", "", "FORTYGUARD_API_KEY is missing from .env"),
        ("FORTYGUARD_API_KEY", "   ", "FORTYGUARD_API_KEY is missing from .env"),
        ("FORTYGUARD_API_URL", None, "FortyGuard URLs are missing from .env"),
        ("FORTYGUARD_API_URL", "", "FortyGuard URLs are missing from .env"),
        ("FORTYGUARD_API_URL", " \t ", "FortyGuard URLs are missing from .env"),
        ("FORTYGUARD_MCP_URL", None, "FortyGuard URLs are missing from .env"),
        ("FORTYGUARD_MCP_URL", "", "FortyGuard URLs are missing from .env"),
        ("FORTYGUARD_MCP_URL", " \t ", "FortyGuard URLs are missing from .env"),
    ],
)
def test_config_rejects_missing_or_blank_environment_values(
    monkeypatch, invalid_name, invalid_value, error_message
):
    values = {
        "FORTYGUARD_API_KEY": "synthetic-key",
        "FORTYGUARD_API_URL": "https://api.example.invalid",
        "FORTYGUARD_MCP_URL": "https://mcp.example.invalid",
    }
    if invalid_value is None:
        values.pop(invalid_name)
    else:
        values[invalid_name] = invalid_value

    with pytest.raises(ValueError, match=error_message):
        load_config(monkeypatch, values)
