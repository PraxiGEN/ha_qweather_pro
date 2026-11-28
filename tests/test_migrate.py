"""async_migrate_entry 拒绝桩单测：v1 拒绝 + persistent Repairs 引导，v2 直通。2.0.0 起不支持 1.2.x 直升。 运行：``pytest tests/test_migrate.py -v``。"""
from __future__ import annotations

import inspect
from unittest.mock import MagicMock, patch

import pytest

try:
    from custom_components.qweather_pro import async_migrate_entry, ISSUE_LEGACY_ENTRY
    from custom_components.qweather_pro.const import (
        DOMAIN,
        CONF_API_KEY,
        CONF_HOST,
        CONF_LOCATION_ID,
        CONF_USE_TOKEN,
    )
    from homeassistant.helpers.issue_registry import async_create_issue as _real_create_issue
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    _HA_OK = True
except Exception:  # pragma: no cover - 本地缺依赖时跳过
    _HA_OK = False

pytestmark = [
    pytest.mark.skipif(not _HA_OK, reason="requires homeassistant environment"),
    pytest.mark.usefixtures("enable_custom_integrations"),
]

HOST = "https://mockhost.qweatherapi.com"

def _v1_entry():
    return MockConfigEntry(
        domain=DOMAIN, version=1, title="深圳",
        data={
            CONF_HOST: HOST,
            CONF_USE_TOKEN: False,
            CONF_API_KEY: "k",
            CONF_LOCATION_ID: "114.05,22.54",
        },
    )

async def test_migrate_v1_refused_with_issue(hass):
    """v1 条目：拒绝迁移（版本数据不动）+ 推送 persistent 非 fixable Repairs 引导."""
    entry = _v1_entry()
    entry.add_to_hass(hass)
    with patch(
        "custom_components.qweather_pro.async_create_issue", new=MagicMock()
    ) as create:
        assert await async_migrate_entry(hass, entry) is False

    create.assert_called_once()
    assert create.call_args.args[:3] == (hass, DOMAIN, f"{ISSUE_LEGACY_ENTRY}_{entry.entry_id}")
    kwargs = create.call_args.kwargs
    assert kwargs["is_fixable"] is False
    assert kwargs["is_persistent"] is True
    assert kwargs["severity"].value == "error"
    assert kwargs["translation_key"] == "legacy_entry"
# 2026.10+ issue 归属条目随条目删除自动清理；2026.9 无此参数（能力探测）
    if "config_entry_id" in inspect.signature(_real_create_issue).parameters:
        assert kwargs["config_entry_id"] == entry.entry_id
    assert entry.version == 1

async def test_migrate_v2_noop_without_issue(hass):
    """v2 条目（core 对 minor 版本差异也会调桩）：直通，不建 issue，数据不动."""
    entry = _v1_entry()
    entry.version = 2
    entry.minor_version = 1
    entry.add_to_hass(hass)
    with patch(
        "custom_components.qweather_pro.async_create_issue", new=MagicMock()
    ) as create:
        assert await async_migrate_entry(hass, entry) is True

    create.assert_not_called()
    assert entry.data.get(CONF_LOCATION_ID) == "114.05,22.54"

async def test_setup_entry_clears_stale_legacy_issue(hass):
    """1.3.x 迁移完成再升 2.0.0：setup 幂等清理历史 v1 拒绝 issue."""
    from unittest.mock import AsyncMock

    from custom_components.qweather_pro import async_setup_entry, ISSUE_API_KEY_QUOTA
    from custom_components.qweather_pro.coordinator import QWeatherUpdateCoordinator

    entry = _v1_entry()
    entry.version = 2
    entry.minor_version = 1
    entry.add_to_hass(hass)

    delete = MagicMock()
    with patch(
        "custom_components.qweather_pro.async_create_issue", new=MagicMock()
    ), patch(
        "custom_components.qweather_pro.async_delete_issue", new=delete
    ), patch.object(
        QWeatherUpdateCoordinator, "async_load_cache", new=AsyncMock()
    ), patch.object(
        QWeatherUpdateCoordinator, "async_config_entry_first_refresh", new=AsyncMock()
    ), patch.object(
        hass.config_entries, "async_forward_entry_setups", new=AsyncMock()
    ):
        assert await async_setup_entry(hass, entry) is True

    delete.assert_any_call(hass, DOMAIN, f"{ISSUE_LEGACY_ENTRY}_{entry.entry_id}")
    delete.assert_any_call(hass, DOMAIN, ISSUE_API_KEY_QUOTA)
