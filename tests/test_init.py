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


async def test_setup_registers_get_weather_service(hass):
    assert await async_setup(hass, {}) is True
    assert hass.services.has_service(DOMAIN, "get_weather")


async def test_setup_entry_api_key_creates_repairs_issue(hass):
    """仍用 API KEY：应推送 Repairs 引导迁移 JWT（is_fixable=False）。"""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_USE_TOKEN: False, CONF_API_KEY: "test", CONF_LOCATION_ID: "120,30"},
        entry_id="test",
    )
    entry.add_to_hass(hass)
    hass.data[f"{DOMAIN}_assets"] = True  # 跳过静态资源注册（非本测试关注点）

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
    assert call_args.args[2] == ISSUE_API_KEY_QUOTA
    # 未使用 JWT，不应删除 issue
    delete.assert_not_called()


async def test_setup_entry_jwt_deletes_repairs_issue(hass):
    """已用 JWT：应清理历史遗留的 API KEY Repairs 条目。"""
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
    hass.data[f"{DOMAIN}_assets"] = True  # 跳过静态资源注册（非本测试关注点）

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

    delete.assert_called_once()
    create.assert_not_called()
