"""diagnostics 单测：敏感字段脱敏、runtime_data 缺失兜底.

依赖 cryptography/aiohttp，本地无 homeassistant 时自动 skip，由 CI 跑。
运行：``pytest tests/test_diagnostics.py -v``。
"""
from __future__ import annotations

from unittest.mock import MagicMock, SimpleNamespace

import pytest

try:
    from custom_components.qweather_pro.diagnostics import (  # noqa: E402
        TO_REDACT,
        async_get_config_entry_diagnostics,
    )
    from custom_components.qweather_pro.const import (  # noqa: E402
        CONF_API_KEY,
        CONF_PRIVATE_KEY,
        CONF_PROJECT_ID,
        CONF_KEY_ID,
    )

    _HA_OK = True
except Exception:  # pragma: no cover - 本地缺依赖时跳过
    _HA_OK = False

pytestmark = pytest.mark.skipif(not _HA_OK, reason="requires homeassistant environment")


def test_to_redact_contains_credentials():
    assert {CONF_API_KEY, CONF_PRIVATE_KEY, CONF_PROJECT_ID, CONF_KEY_ID}.issubset(TO_REDACT)


async def test_runtime_data_none_returns_empty():
    entry = MagicMock()
    entry.runtime_data = None
    entry.as_dict.return_value = {"data": {CONF_API_KEY: "x"}, "title": "T"}
    result = await async_get_config_entry_diagnostics(None, entry)
    assert result["coordinator_data"] == {}
    assert result["entry"]["data"][CONF_API_KEY] == "********"


async def test_redacts_sensitive_fields():
    data = {
        CONF_API_KEY: "secret",
        CONF_PRIVATE_KEY: "pk",
        CONF_PROJECT_ID: "p",
        CONF_KEY_ID: "k",
        "location_id": "120,30",
        CONF_USE_TOKEN: True,
    }
    entry = MagicMock()
    entry.runtime_data = SimpleNamespace(data={"now": {"temp": 1}})
    entry.as_dict.return_value = {"data": data, "title": "T"}
    result = await async_get_config_entry_diagnostics(None, entry)
    assert result["entry"]["data"][CONF_API_KEY] == "********"
    assert result["entry"]["data"][CONF_PRIVATE_KEY] == "********"
    assert result["entry"]["data"][CONF_PROJECT_ID] == "********"
    # 非敏感字段保留
    assert result["entry"]["data"]["location_id"] == "120,30"
    assert result["coordinator_data"] == {"now": {"temp": 1}}
