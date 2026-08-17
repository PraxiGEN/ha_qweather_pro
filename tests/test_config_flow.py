"""config_flow 单测：JWT 默认、API KEY 流程、创建条目、重新配置切换.

依赖 homeassistant 完整集成加载（enable_custom_integrations），本地无依赖时自动 skip，由 CI 跑。
运行：``pytest tests/test_config_flow.py -v``。
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

try:
    from homeassistant.config_entries import SOURCE_USER, SOURCE_RECONFIGURE

    from custom_components.qweather_pro.config_flow import QWeatherAPI
    from custom_components.qweather_pro.const import (  # noqa: E402
        DOMAIN,
        CONF_USE_TOKEN,
        CONF_API_KEY,
        CONF_HOST,
        CONF_LOCATION_ID,
        CONF_PROJECT_ID,
        CONF_KEY_ID,
        CONF_UPDATE_INTERVAL,
    )

    _HA_OK = True
except Exception:  # pragma: no cover - 本地缺依赖时跳过
    _HA_OK = False

pytestmark = [
    pytest.mark.skipif(not _HA_OK, reason="requires homeassistant environment"),
    pytest.mark.usefixtures("enable_custom_integrations"),
]

CITY_OK = {
    "code": "200",
    "location": [
        {
            "id": "123",
            "name": "测试",
            "lon": "120",
            "lat": "30",
            "adm1": "省",
            "adm2": "市",
            "country": "CN",
        }
    ],
}


@pytest.fixture
def _patch_citylookup():
    with patch.object(
        QWeatherAPI, "city_lookup", new=AsyncMock(return_value=CITY_OK)
    ) as mock_lookup:
        yield mock_lookup


async def test_user_first_entry_goes_to_setup(hass, _patch_citylookup):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] == "form"
    assert result["step_id"] == "setup"


async def test_setup_form_defaults_to_jwt(hass, _patch_citylookup):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    # setup 表单中 use_token 默认 True
    schema_keys = result["data_schema"].schema  # type: ignore[attr-defined]
    assert CONF_USE_TOKEN in schema_keys


async def test_full_jwt_setup_creates_entry(hass, _patch_citylookup):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: "https://api.qweather.com",
            CONF_LOCATION_ID: "120,30",
            CONF_USE_TOKEN: True,
            CONF_API_KEY: "k",
        },
    )
    # 选择 JWT → 进入 jwt_setup
    assert result["step_id"] == "jwt_setup"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_USE_TOKEN: True, CONF_PROJECT_ID: "p", CONF_KEY_ID: "k"},
    )
    assert result["type"] == "create_entry"
    assert result["data"][CONF_USE_TOKEN] is True
    # JWT 流程应注入自动生成的私钥
    assert result["data"][CONF_PRIVATE_KEY]
    # 默认 options
    assert result["options"][CONF_UPDATE_INTERVAL] == 15


async def test_api_key_setup_creates_entry(hass, _patch_citylookup):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: "https://api.qweather.com",
            CONF_LOCATION_ID: "120,30",
            CONF_USE_TOKEN: False,
            CONF_API_KEY: "k",
        },
    )
    # API KEY 模式不进入 jwt_setup，直接搜索并创建
    assert result["type"] == "create_entry"
    assert result["data"][CONF_USE_TOKEN] is False


async def test_reconfigure_can_switch_to_jwt(hass, mock_config_entry, _patch_citylookup):
    mock_config_entry.data[CONF_USE_TOKEN] = False
    mock_config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_RECONFIGURE, "entry_id": mock_config_entry.entry_id},
        data=mock_config_entry.data,
    )
    # 重新配置表单提交勾选 use_token
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: "https://api.qweather.com",
            CONF_LOCATION_ID: "120,30",
            CONF_USE_TOKEN: True,
            CONF_API_KEY: "k",
        },
    )
    # 切到 JWT → jwt_setup
    assert result["step_id"] == "jwt_setup"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_USE_TOKEN: True, CONF_PROJECT_ID: "p", CONF_KEY_ID: "k"},
    )
    assert result["type"] == "abort"
    assert result["reason"] == "reauth_successful"
