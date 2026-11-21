"""QWeather (和风天气) 集成诊断支持."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import QWeatherRuntimeData
from .const import CONF_API_KEY, CONF_PRIVATE_KEY, CONF_PROJECT_ID, CONF_KEY_ID

# 敏感字段：凭据与账户信息一律脱敏
TO_REDACT = {
    CONF_API_KEY,
    CONF_PRIVATE_KEY,
    CONF_PROJECT_ID,
    CONF_KEY_ID,
}

async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """返回配置条目的诊断信息 (供 HA 问题上报使用)."""
    # setup 失败/重试中的 entry runtime_data 可能为 None，需判空
    runtime: QWeatherRuntimeData | None = entry.runtime_data
    payload: dict[str, Any] = {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "locations": {},
    }
    if isinstance(runtime, QWeatherRuntimeData):
        for subentry_id, coordinator in runtime.coordinators.items():
            payload["locations"][subentry_id] = (
                coordinator.data if coordinator.data else {}
            )
    return payload
