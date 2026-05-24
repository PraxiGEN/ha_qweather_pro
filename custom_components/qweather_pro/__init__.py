"""QWeather (和风天气) 集成入口."""
from __future__ import annotations
import os
import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration
from homeassistant.components.http import StaticPathConfig
from homeassistant.components import frontend
from .const import DOMAIN, PLATFORMS
from .coordinator import QWeatherUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

type QWeatherConfigEntry = ConfigEntry[QWeatherUpdateCoordinator]

async def async_setup_entry(hass: HomeAssistant, entry: QWeatherConfigEntry) -> bool:
    # 1. 获取版本
    integration = await async_get_integration(hass, DOMAIN)
    version = str(integration.version) if integration.version else "1.0.0"

    # 2. 注册静态资源 (仅在 HA 启动后执行一次)
    if f"{DOMAIN}_assets" not in hass.data:
        # 使用 hass.config.path 动态定位物理路径
        local_path = hass.config.path("custom_components", DOMAIN, "local")
        
        if os.path.exists(local_path):
            # 注册静态文件夹映射
            await hass.http.async_register_static_paths([
                StaticPathConfig("/qweather-local", local_path, False)
            ])
            
            assets = [
                f"/qweather-local/qweather-card/qweather-card.js?v={version}",
                f"/qweather-local/qweather-card/qweather-more-info.js?v={version}"
            ]
            
            for url in assets:
                frontend.add_extra_js_url(hass, url)
                
            hass.data[f"{DOMAIN}_assets"] = True
            _LOGGER.info("QWeather 资源已注册: 卡片与详情页 JS 已就绪 (v%s)", version)

    # 3. 初始化并刷新 (此时 entry.title 已经是城市名了)
    coordinator = QWeatherUpdateCoordinator(hass, entry, version)
    await coordinator.async_config_entry_first_refresh()

    # 4. 挂载数据并加载平台
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True

async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: QWeatherConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)