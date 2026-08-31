"""QWeather Pro 自定义服务.

提供 `qweather_pro.get_weather`：返回实体的完整天气数据集（coordinator.data），
支持通过 `keys` 按需筛选顶层数据块，承载 AQI / 预警 / 生活指数 / 摘要等非预报数据。
"""
from __future__ import annotations

import json
import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import (
    area_registry as ar,
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
)

from .const import DOMAIN, LOGGER

VALID_KEYS: frozenset[str] = frozenset(
    {
        "city",
        "now",
        "daily",
        "hourly",
        "aqi",
        "warning",
        "indices",
        "weather_abstract",
        "minutely_detail",
        "minutely_summary",
        "update_time",
        "attributions",
    }
)

# 纯内部诊断字段，不对外暴露
INTERNAL_KEYS: frozenset[str] = frozenset({"cache_freshness"})
SERVICE_GET_WEATHER_SCHEMA = vol.Schema(
    {
        vol.Optional("entity_id"): cv.entity_ids,
        vol.Optional("device_id"): vol.Any(str, [str]),
        vol.Optional("area_id"): vol.Any(str, [str]),
        vol.Optional("keys"): vol.All(
            vol.Any(str, [str]),
            lambda v: [v] if isinstance(v, str) else v,
            [vol.In(VALID_KEYS)],
        ),
    }
)

def _as_list(value) -> list:
    """归一化 target 字段为列表（兼容 UI 的 list 与手写 YAML 的单字符串）."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return value
    return list(value)

async def _resolve_entity_id(hass: HomeAssistant, call: ServiceCall) -> str | None:
    """从 target 字段解析出单个 QWeather Pro 实体。"""
    raw: dict = {}
    for key in ("entity_id", "device_id", "area_id"):
        if key in call.data:
            raw[key] = call.data[key]
    target = getattr(call, "target", None)
    if isinstance(target, dict):
        for key in ("entity_id", "device_id", "area_id"):
            if key in target and key not in raw:
                raw[key] = target[key]

    # 已展开的 entity_id 直接返回
    eid = raw.get("entity_id")
    if eid:
        return eid[0] if isinstance(eid, list) else eid

    dr_reg = dr.async_get(hass)
    er_reg = er.async_get(hass)
    ar_reg = ar.async_get(hass)

    candidates: list[str] = []
    # 设备 → 其下全部实体
    for did in _as_list(raw.get("device_id")):
        if dr_reg.async_get(did) is None:
            continue
        for ent in er_reg.entities.values():
            if ent.device_id == did:
                candidates.append(ent.entity_id)
    # 区域 → 区域内设备 → 其下实体
    for aid in _as_list(raw.get("area_id")):
        area = ar_reg.async_get_area(aid)
        if area is None:
            continue
        for dev in dr_reg.devices.values():
            if dev.area_id != aid:
                continue
            for ent in er_reg.entities.values():
                if ent.device_id == dev.id:
                    candidates.append(ent.entity_id)

    # 仅保留属于本集成 qweather_pro 的实体
    for ent_id in candidates:
        ent = er_reg.async_get(ent_id)
        if ent is None or ent.config_entry_id is None:
            continue
        entry = hass.config_entries.async_get_entry(ent.config_entry_id)
        if entry is not None and entry.domain == DOMAIN:
            return ent_id
    return None

async def async_setup_services(hass: HomeAssistant) -> None:
    """注册集成自定义服务."""

    async def get_weather(call: ServiceCall) -> dict | None:

        if not call.return_response:
            return None
        entity_id = await _resolve_entity_id(hass, call)
        if not entity_id:
            raise ServiceValidationError(
                "entity_id is required (select a QWeather Pro weather entity or its device/area)"
            )

        registry = er.async_get(hass)
        entity = registry.async_get(entity_id)
        if entity is None or entity.config_entry_id is None:
            raise ServiceValidationError(f"Entity {entity_id} not found")

        entry = hass.config_entries.async_get_entry(entity.config_entry_id)
        if entry is None or entry.domain != DOMAIN:
            raise ServiceValidationError(
                f"Entity {entity_id} is not a {DOMAIN} entity"
            )

        coordinator = entry.runtime_data
        if coordinator is None or not coordinator.data:
            raise ServiceValidationError(
                f"Coordinator for {entity_id} is not ready"
            )

        data = coordinator.data

        # 按需筛选顶层数据块（schema 已保证 keys 均为合法成员；
        # 此处再用 _as_list 归一化，兼容绕过 schema 直接调用的场景）
        requested = call.data.get("keys")
        if requested:
            requested = _as_list(requested)
            payload = {k: data[k] for k in requested if k in data}
        else:
            payload = {
                k: v for k, v in data.items() if k not in INTERNAL_KEYS
            }

        # JSON 安全化：datetime / 任意不可序列化对象兜底为字符串
        return json.loads(json.dumps(payload, default=str))

    LOGGER.debug("Registering %s.get_weather service", DOMAIN)
    hass.services.async_register(
        DOMAIN,
        "get_weather",
        get_weather,
        schema=SERVICE_GET_WEATHER_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
