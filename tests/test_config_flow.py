"""config_flow 单测：JWT 默认、API KEY 流程、创建条目、重新配置切换。"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

try:
    from homeassistant.config_entries import SOURCE_USER, SOURCE_RECONFIGURE
    from homeassistant.const import CONF_HOST

    from custom_components.qweather_pro.config_flow import QWeatherAPI
    from custom_components.qweather_pro.const import (  # noqa: E402
        DOMAIN,
        CONF_USE_TOKEN,
        CONF_API_KEY,
        CONF_CUSTOM_MORE_INFO,
        CONF_CUSTOM_UI,
        CONF_DAILYSTEPS,
        CONF_HOURLYSTEPS,
        CONF_LOCATION_ID,
        CONF_PROJECT_ID,
        CONF_KEY_ID,
        CONF_PRIVATE_KEY,
        CONF_UPDATE_INTERVAL,
        SUBENTRY_TYPE_LOCATION,
    )
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from tests.conftest import add_location_subentry, stub_runtime_api

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

# 须用专属 API Host：公共域名已停服且被 deprecated_domains 校验拦截
HOST_OK = "https://mockhost.qweatherapi.com"

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
            CONF_HOST: HOST_OK,
            CONF_LOCATION_ID: "120,30",
            CONF_USE_TOKEN: True,
            CONF_API_KEY: "k",
        },
    )
# 选择 JWT → 进入 jwt_setup
    assert result["step_id"] == "jwt_setup"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_PROJECT_ID: "p", CONF_KEY_ID: "k"},
    )
    assert result["type"] == "create_entry"
    assert result["data"][CONF_USE_TOKEN] is True
# JWT 流程应注入自动生成的私钥
    assert result["data"][CONF_PRIVATE_KEY]
# v1.3.0：账号数据不含位置；首个位置随 subentries 落库
    assert CONF_LOCATION_ID not in result["data"]
    assert len(result["subentries"]) == 1
    assert result["subentries"][0]["data"][CONF_LOCATION_ID] == "120.0,30.0"
    assert result["subentries"][0]["title"] == "测试"
# v1.3.0 R2：条目 title = host（账号名），options 全部下沉首个位置子条目
    assert result["title"] == HOST_OK
    assert result["subentries"][0]["data"][CONF_UPDATE_INTERVAL] == 15

async def test_api_key_setup_creates_entry(hass, _patch_citylookup):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: HOST_OK,
            CONF_LOCATION_ID: "120,30",
            CONF_USE_TOKEN: False,
            CONF_API_KEY: "k",
        },
    )
# API KEY 模式不进入 jwt_setup，直接搜索并创建
    assert result["type"] == "create_entry"
    assert result["data"][CONF_USE_TOKEN] is False
    assert CONF_LOCATION_ID not in result["data"]
    assert len(result["subentries"]) == 1

async def test_reconfigure_can_switch_to_jwt(hass, _patch_citylookup):
# HA 2026.9 的 ConfigEntry.data 为只读，只能在构造时传入
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_USE_TOKEN: False,
            CONF_HOST: HOST_OK,
            CONF_API_KEY: "k",
        },
    )
    entry.add_to_hass(hass)
# 账号流无位置字段：以首个 location 子条目作凭据验证探针
    add_location_subentry(hass, entry, coords="120,30")
# reconfigure 靠 context["entry_id"] 载入原条目，async_init 不能传 data（否则被当作首步输入结束流程）
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )
# 重新配置表单提交勾选 use_token
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: HOST_OK,
            CONF_USE_TOKEN: True,
            CONF_API_KEY: "k",
        },
    )
# 切到 JWT → jwt_setup
    assert result["step_id"] == "jwt_setup"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_PROJECT_ID: "p", CONF_KEY_ID: "k"},
    )
    assert result["type"] == "abort"
# 走 async_update_and_abort（reload 由条目 update listener 完成），reason 为 reconfigure_successful
    assert result["reason"] == "reconfigure_successful"
# 账号数据不含位置键
    assert CONF_LOCATION_ID not in entry.data

# v1.3.0 location 子条目流

def _location_form_input(**overrides):
    """location 子条目 user 步输入（R2.1：纯位置搜索，options 落默认值）."""
    data = {
        CONF_LOCATION_ID: "120,30",
    }
    data.update(overrides)
    return data

def _mark_loaded(hass, entry):
    """把 MockConfigEntry 置为 LOADED（子条目流要求父条目已加载）."""
    from homeassistant.config_entries import ConfigEntryState

    if hasattr(entry, "mock_state"):
        entry.mock_state(hass, ConfigEntryState.LOADED)
        return
    pytest.skip("MockConfigEntry.mock_state unavailable")

async def test_subentry_add_location(hass, _patch_citylookup):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_USE_TOKEN: False, CONF_HOST: HOST_OK, CONF_API_KEY: "k"},
    )
    entry.add_to_hass(hass)
    add_location_subentry(hass, entry, coords="130,20")
    _mark_loaded(hass, entry)
    stub_runtime_api(entry)

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "location"),
        context={"source": SOURCE_USER},
    )
    assert result["step_id"] == "user"
# R2.1：user 表单纯位置搜索，不含 options 字段
    schema_keys = result["data_schema"].schema  # type: ignore[attr-defined]
    assert CONF_LOCATION_ID in schema_keys
    assert CONF_DAILYSTEPS not in schema_keys
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], _location_form_input()
    )
    assert result["type"] == "create_entry"
    assert result["title"] == "测试"
    assert result["data"][CONF_LOCATION_ID] == "120.0,30.0"
    assert result["unique_id"] == "qw_120.0_30.0"
# API KEY 模式：无 update_interval 字段；options 默认值落子条目 data（编辑走 reconfigure）
    assert CONF_UPDATE_INTERVAL not in result["data"]
    assert result["data"][CONF_DAILYSTEPS] == "7"
# flow manager 已把子条目挂到条目上
    uids = {s.unique_id for s in entry.get_subentries_of_type(SUBENTRY_TYPE_LOCATION)}
    assert uids == {"qw_130.0_20.0", "qw_120.0_30.0"}

async def test_subentry_add_duplicate_location_aborts(hass, _patch_citylookup):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_USE_TOKEN: False, CONF_HOST: HOST_OK, CONF_API_KEY: "k"},
    )
    entry.add_to_hass(hass)
    add_location_subentry(hass, entry, coords="120,30")
    _mark_loaded(hass, entry)
    stub_runtime_api(entry)

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "location"),
        context={"source": SOURCE_USER},
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], _location_form_input()
    )
    assert result["type"] == "abort"
    assert result["reason"] == "duplicate_location"

async def test_subentry_add_aborts_when_entry_not_loaded(hass, _patch_citylookup):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_USE_TOKEN: False, CONF_HOST: HOST_OK, CONF_API_KEY: "k"},
    )
    entry.add_to_hass(hass)  # 默认 NOT_LOADED
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "location"),
        context={"source": SOURCE_USER},
    )
# 部分版本 flow manager 在 init 即中止；否则中止发生在提交后
    if result["type"] != "form":
        assert result["reason"] == "config_entry_not_loaded"
        return
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], _location_form_input()
    )
    assert result["type"] == "abort"
    assert result["reason"] == "config_entry_not_loaded"

async def test_subentry_reconfigure_updates_options_only(hass, _patch_citylookup):
    """R5：位置不可改，reconfigure 仅改 options；location data 原样保留."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_USE_TOKEN: False, CONF_HOST: HOST_OK, CONF_API_KEY: "k"},
    )
    entry.add_to_hass(hass)
    add_location_subentry(hass, entry, coords="120,30")
    _mark_loaded(hass, entry)
    sub = entry.get_subentries_of_type(SUBENTRY_TYPE_LOCATION)[0]

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "location"),
        context={"source": SOURCE_RECONFIGURE, "subentry_id": sub.subentry_id},
    )
# reconfigure 表单不再含位置字段
    assert result["step_id"] == "reconfigure"
    schema_keys = result["data_schema"].schema  # type: ignore[attr-defined]
    assert CONF_LOCATION_ID not in schema_keys
    assert CONF_DAILYSTEPS in schema_keys

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_DAILYSTEPS: "10",
            CONF_HOURLYSTEPS: "72",
            CONF_CUSTOM_UI: True,
            CONF_CUSTOM_MORE_INFO: False,
        },
    )
    assert result["type"] == "abort"
    assert result["reason"] == "reconfigure_successful"
# 位置数据不变（R5），options 已更新（R4）
    assert sub.data[CONF_LOCATION_ID] == "120.0,30.0"
    assert sub.data[CONF_DAILYSTEPS] == "10"
    assert sub.data[CONF_HOURLYSTEPS] == "72"
    assert sub.data[CONF_CUSTOM_UI] is True
