"""集成入口单测：服务注册、setup_entry 全链路与 Repairs 迁移引导逻辑.

依赖 homeassistant 完整集成加载，本地无依赖时自动 skip，由 CI 跑。
运行：``pytest tests/test_init.py -v``。
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

try:
    from custom_components.qweather_pro import (  # noqa: E402
        async_setup,
        async_setup_entry,
        ISSUE_API_KEY_QUOTA,
    )
    from custom_components.qweather_pro.const import (  # noqa: E402
        DOMAIN,
        CONF_USE_TOKEN,
        CONF_API_KEY,
        CONF_LOCATION_ID,
        CONF_PROJECT_ID,
        CONF_KEY_ID,
        CONF_PRIVATE_KEY,
    )
    from custom_components.qweather_pro.coordinator import (  # noqa: E402
        QWeatherUpdateCoordinator,
    )
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    _HA_OK = True
except Exception:  # pragma: no cover - 本地缺依赖时跳过
    _HA_OK = False

pytestmark = [
    pytest.mark.skipif(not _HA_OK, reason="requires homeassistant environment"),
    pytest.mark.usefixtures("enable_custom_integrations"),
]


async def test_setup_entry_registers_get_weather_service(hass):
    """服务随条目加载注册（幂等）；async_setup 不再注册服务."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_USE_TOKEN: False, CONF_API_KEY: "test", CONF_LOCATION_ID: "120,30"},
        entry_id="test",
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.qweather_pro.async_create_issue", new=MagicMock()
    ), patch(
        "custom_components.qweather_pro.async_delete_issue", new=MagicMock()
    ), patch.object(
        QWeatherUpdateCoordinator, "async_load_cache", new=AsyncMock()
    ), patch.object(
        QWeatherUpdateCoordinator, "async_config_entry_first_refresh", new=AsyncMock()
    ), patch.object(
        hass.config_entries, "async_forward_entry_setups", new=AsyncMock()
    ):
        assert await async_setup(hass, {}) is True
        # 服务注册已移至 setup_entry（随末条目卸载注销）
        assert not hass.services.has_service(DOMAIN, "get_weather")
        assert await async_setup_entry(hass, entry) is True

    assert hass.services.has_service(DOMAIN, "get_weather")


async def test_setup_entry_api_key_creates_repairs_issue(hass):
    """仍用 API KEY：应推送按条目隔离的 Repairs 引导迁移 JWT（is_fixable=False）。"""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_USE_TOKEN: False, CONF_API_KEY: "test", CONF_LOCATION_ID: "120,30"},
        entry_id="test",
    )
    entry.add_to_hass(hass)

    create = MagicMock()
    delete = MagicMock()
    with patch(
        "custom_components.qweather_pro.async_create_issue", new=create
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

    create.assert_called_once()
    call_args = create.call_args
    assert call_args.args[1] == DOMAIN
    # issue ID 按条目隔离：api_key_quota_<entry_id>
    assert call_args.args[2] == f"{ISSUE_API_KEY_QUOTA}_{entry.entry_id}"
    # 旧版本全局固定 ID 会被无条件清理（跨版本升级兼容，幂等无害）
    delete.assert_called_once_with(hass, DOMAIN, ISSUE_API_KEY_QUOTA)


async def test_setup_entry_jwt_deletes_repairs_issue(hass):
    """已用 JWT：应清理旧全局 ID 与本条目隔离 ID 两处 Repairs 引导."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_USE_TOKEN: True,
            CONF_PROJECT_ID: "p",
            CONF_KEY_ID: "k",
            CONF_PRIVATE_KEY: "pk",
            CONF_LOCATION_ID: "120,30",
        },
        entry_id="test",
    )
    entry.add_to_hass(hass)

    create = MagicMock()
    delete = MagicMock()
    with patch(
        "custom_components.qweather_pro.async_create_issue", new=create
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

    # 两次清理：旧版本全局固定 ID（兼容残留）+ 本条目隔离 ID
    delete.assert_any_call(hass, DOMAIN, ISSUE_API_KEY_QUOTA)
    delete.assert_any_call(hass, DOMAIN, f"{ISSUE_API_KEY_QUOTA}_{entry.entry_id}")
    assert delete.call_count == 2
    create.assert_not_called()
