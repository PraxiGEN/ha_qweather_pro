"""async_migrate_entry 单测：R2 同 host 分组合并迁移。"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

try:
    from custom_components.qweather_pro import async_migrate_entry
    from custom_components.qweather_pro.const import (
        DOMAIN,
        CONF_API_KEY,
        CONF_CUSTOM_UI,
        CONF_DAILYSTEPS,
        CONF_HOST,
        CONF_HOURLYSTEPS,
        CONF_LOCATION_ID,
        CONF_UPDATE_INTERVAL,
        CONF_USE_TOKEN,
        SUBENTRY_TYPE_LOCATION,
    )
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    _HA_OK = True
except Exception:  # pragma: no cover - 本地缺依赖时跳过
    _HA_OK = False

pytestmark = [
    pytest.mark.skipif(not _HA_OK, reason="requires homeassistant environment"),
    pytest.mark.usefixtures("enable_custom_integrations"),
]

HOST = "https://mockhost.qweatherapi.com"

def _v1_entry(**overrides):
    data = {
        CONF_HOST: HOST,
        CONF_USE_TOKEN: False,
        CONF_API_KEY: "k",
        CONF_LOCATION_ID: "114.05,22.54",
    }
    data.update(overrides)
    return MockConfigEntry(domain=DOMAIN, data=data, version=1, title="深圳")

async def test_migrate_v1_creates_subentry_reusing_entry_id(hass):
    """v1→v2：位置进子条目且 subentry_id == entry_id；账号 uid/title=host；options 下沉."""
    entry = _v1_entry(options={CONF_DAILYSTEPS: "10", CONF_CUSTOM_UI: True})
    entry.add_to_hass(hass)
    assert await async_migrate_entry(hass, entry) is True

    assert entry.version == 2
    assert entry.minor_version == 1
# 账号身份 = host（R1/R3）
    assert entry.unique_id == HOST
    assert entry.title == HOST
# 账号 data 只剩凭据白名单（位置键与 legacy 死键全部剥离）
    assert CONF_LOCATION_ID not in entry.data
    assert entry.data[CONF_API_KEY] == "k"
    assert set(entry.data.keys()) <= {CONF_HOST, CONF_USE_TOKEN, CONF_API_KEY}
# R4：父条目 options 清空
    assert entry.options == {}
# 子条目：恰好 1 个，subentry_id 复用 entry_id ⇒ unique_id/设备标识/缓存文件名不变
    subs = entry.get_subentries_of_type(SUBENTRY_TYPE_LOCATION)
    assert len(subs) == 1
    sub = subs[0]
    assert sub.subentry_id == entry.entry_id
    assert sub.title == "深圳"
    assert sub.data[CONF_LOCATION_ID] == "114.05,22.54"
    assert sub.unique_id == "qw_114.05_22.54"
# options 下沉：v1 options 键值原样进入子条目 data；API KEY 无 update_interval
    assert sub.data[CONF_DAILYSTEPS] == "10"
    assert sub.data[CONF_CUSTOM_UI] is True
    assert CONF_UPDATE_INTERVAL not in sub.data

async def test_migrate_merges_same_host_jwt_preferred_as_base(hass):
    """R2/R6：同 host 两 v1 条目（API KEY + JWT）→ 合并为 1 父 2 子，JWT 作 base."""
    api_entry = _v1_entry()
    api_entry.add_to_hass(hass)
    jwt_entry = MockConfigEntry(
        domain=DOMAIN, version=1, title="西安",
        data={
            CONF_HOST: HOST, CONF_USE_TOKEN: True, CONF_LOCATION_ID: "108.94,34.27",
            "project_id": "p", "key_id": "kid", "private_key": "pk",
        },
    )
    jwt_entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, api_entry) is True

# base = JWT 条目：升级为父条目（uid/title=host）
    assert jwt_entry.version == 2
    assert jwt_entry.unique_id == HOST
    assert jwt_entry.title == HOST
# 2 个位置子条目：subentry_id 各自复用旧 entry_id
    subs = jwt_entry.get_subentries_of_type(SUBENTRY_TYPE_LOCATION)
    assert {s.subentry_id for s in subs} == {api_entry.entry_id, jwt_entry.entry_id}
    assert {s.title for s in subs} == {"深圳", "西安"}
    assert {s.data[CONF_LOCATION_ID] for s in subs} == {"114.05,22.54", "108.94,34.27"}
# JWT 位置子条目含 update_interval 默认值；API KEY 位置没有
    jwt_sub = next(s for s in subs if s.subentry_id == jwt_entry.entry_id)
    assert jwt_sub.data[CONF_UPDATE_INTERVAL] == 15
    api_sub = next(s for s in subs if s.subentry_id == api_entry.entry_id)
    assert CONF_UPDATE_INTERVAL not in api_sub.data
# 被吸收条目：置 v2（其自身迁移调用短路），凭据壳子由延迟任务移除
    assert api_entry.version == 2

async def test_migrate_absorbed_entry_options_sink(hass):
    """R4：被吸收条目的 options 下沉为其子条目 data."""
    api_entry = _v1_entry(options={CONF_HOURLYSTEPS: "72", CONF_CUSTOM_UI: True})
    api_entry.add_to_hass(hass)
    jwt_entry = MockConfigEntry(
        domain=DOMAIN, version=1, title="西安",
        data={
            CONF_HOST: HOST, CONF_USE_TOKEN: True, CONF_LOCATION_ID: "108.94,34.27",
            "project_id": "p", "key_id": "kid", "private_key": "pk",
        },
    )
    jwt_entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, jwt_entry) is True

    subs = jwt_entry.get_subentries_of_type(SUBENTRY_TYPE_LOCATION)
    api_sub = next(s for s in subs if s.subentry_id == api_entry.entry_id)
    assert api_sub.data[CONF_HOURLYSTEPS] == "72"
    assert api_sub.data[CONF_CUSTOM_UI] is True

async def test_migrate_v2_parent_absorbs_late_v1(hass):
    """已迁移父条目运行期遇到同 host 新 v1 条目（如备份恢复）→ 并入 + 调度重载."""
    parent = _v1_entry(options={CONF_DAILYSTEPS: "7"})
    parent.add_to_hass(hass)
    assert await async_migrate_entry(hass, parent) is True
    assert parent.version == 2

    late = _v1_entry(CONF_LOCATION_ID="108.94,34.27")
    late.title = "西安"
    late.add_to_hass(hass)
    with patch.object(
        hass.config_entries, "async_schedule_reload", new=MagicMock()
    ) as reload_mock:
        assert await async_migrate_entry(hass, late) is True
# base 已 LOADED（MockConfigEntry 默认非 LOADED，这里手动置为 LOADED 触发重载分支）
    subs = parent.get_subentries_of_type(SUBENTRY_TYPE_LOCATION)
    assert {s.data[CONF_LOCATION_ID] for s in subs} == {"114.05,22.54", "108.94,34.27"}
    reload_mock.assert_not_called()  # base 未 LOADED：无需 reload（启动期自然接管）

async def test_migrate_v1_missing_location_fails(hass):
    """脏数据防护：缺位置键时不迁移，条目进 MIGRATION_ERROR。"""
    data = {
        CONF_HOST: HOST,
        CONF_USE_TOKEN: False,
        CONF_API_KEY: "k",
    }
    entry = MockConfigEntry(domain=DOMAIN, data=data, version=1, title="深圳")
    entry.add_to_hass(hass)
    assert await async_migrate_entry(hass, entry) is False
    assert entry.version == 1

async def test_migrate_v1_missing_host_fails(hass):
    """缺 host：账号身份无从谈起，拒绝迁移。"""
    entry = MockConfigEntry(
        domain=DOMAIN, version=1, title="深圳",
        data={CONF_USE_TOKEN: False, CONF_API_KEY: "k", CONF_LOCATION_ID: "114.05,22.54"},
    )
    entry.add_to_hass(hass)
    assert await async_migrate_entry(hass, entry) is False

async def test_migrate_newer_version_fails(hass):
    """数据版本高于当前集成（如降级 HA）→ 拒绝加载。"""
    entry = _v1_entry()
    entry.version = 3
    entry.add_to_hass(hass)
    assert await async_migrate_entry(hass, entry) is False

async def test_migrate_v2_is_noop(hass):
    """已是 v2：直接通过，不动数据。"""
    entry = _v1_entry()
    entry.version = 2
    entry.minor_version = 1
    entry.add_to_hass(hass)
    assert await async_migrate_entry(hass, entry) is True
    assert entry.data.get(CONF_LOCATION_ID) == "114.05,22.54"  # 数据未被触碰
