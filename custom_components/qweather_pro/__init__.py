"""QWeather (和风天气) 集成入口."""
from __future__ import annotations

import os

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration
from homeassistant.components.http import StaticPathConfig
from homeassistant.components import frontend
from homeassistant.helpers.issue_registry import (
    async_create_issue,
    async_delete_issue,
    IssueSeverity,
)

from .const import DOMAIN, PLATFORMS, LOGGER, CONF_USE_TOKEN
from .coordinator import QWeatherUpdateCoordinator
from .services import async_setup_services

# 定义强类型别名，便于 IDE 补全 runtime_data
type QWeatherConfigEntry = ConfigEntry[QWeatherUpdateCoordinator]

# Repairs 条目 ID：引导仍用 API KEY 的用户迁移 JWT
ISSUE_API_KEY_QUOTA = "api_key_quota"

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """初始化集成"""
    await async_setup_services(hass)
    return True

async def async_setup_entry(hass: HomeAssistant, entry: QWeatherConfigEntry) -> bool:
    """设置配置条目."""
    
    integration = await async_get_integration(hass, DOMAIN)
    version = str(integration.version) if integration.version else "1.0.0"

    if f"{DOMAIN}_assets" not in hass.data:
        local_path = hass.config.path("custom_components", DOMAIN, "www")
        if os.path.exists(local_path):
            await hass.http.async_register_static_paths([
                StaticPathConfig("/qweather_pro-local", local_path, False)
            ])
            assets = [
                f"/qweather_pro-local/qweather-pro-card.js?v={version}",
                f"/qweather_pro-local/qweather-pro-more-info.js?v={version}",
                f"/qweather_pro-local/qweather-pro-i18n.js?v={version}"
            ]
            for url in assets:
                frontend.add_extra_js_url(hass, url)
                
            hass.data[f"{DOMAIN}_assets"] = True
            LOGGER.info("QWeather Lovelace 资源注册成功 (v%s)", version)

    coordinator = QWeatherUpdateCoordinator(hass, entry, version)
    await coordinator.async_load_cache()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    # 存量引导：仍用 API KEY 的用户推送 Repairs 条目，引导迁移 JWT
    await _async_refresh_api_key_issue(hass, entry)
    return True

async def _async_refresh_api_key_issue(hass: HomeAssistant, entry: QWeatherConfigEntry) -> None:
    """仍用 API KEY 时推送 Repairs 引导迁移 JWT；已用 JWT 则清理该条目。"""
    if entry.data.get(CONF_USE_TOKEN):
        async_delete_issue(hass, DOMAIN, ISSUE_API_KEY_QUOTA)
        return
    async_create_issue(
        hass,
        DOMAIN,
        ISSUE_API_KEY_QUOTA,
        is_fixable=False,
        severity=IssueSeverity.WARNING,
        translation_key="api_key_quota",
    )

async def async_reload_entry(hass: HomeAssistant, entry: QWeatherConfigEntry) -> None:
    """当用户在 UI 修改配置选项时，重新加载整个集成."""
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: QWeatherConfigEntry) -> bool:
    """卸载集成实例."""
    # 卸载所有平台 (sensor, weather)
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)