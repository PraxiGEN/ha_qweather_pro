"""QWeather (和风天气) 集成入口."""
from __future__ import annotations

import os

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration
from homeassistant.components.http import StaticPathConfig
from homeassistant.components import frontend

from .const import DOMAIN, PLATFORMS, LOGGER
from .coordinator import QWeatherUpdateCoordinator

# 定义强类型别名，便于 IDE 补全 runtime_data
type QWeatherConfigEntry = ConfigEntry[QWeatherUpdateCoordinator]

async def async_setup_entry(hass: HomeAssistant, entry: QWeatherConfigEntry) -> bool:
    """设置配置条目."""
    
    # 1. 动态获取集成元数据（版本号用于前端缓存刷新）
    integration = await async_get_integration(hass, DOMAIN)
    version = str(integration.version) if integration.version else "1.0.0"

    # 2. 注册静态资源 (跨 Entry 全局任务，仅在 HA 启动后执行一次)
    if f"{DOMAIN}_assets" not in hass.data:
        # 动态获取物理路径
        local_path = hass.config.path("custom_components", DOMAIN, "local")
        
        if os.path.exists(local_path):
            # 注册静态路径映射
            await hass.http.async_register_static_paths([
                StaticPathConfig("/qweather-local", local_path, False)
            ])
            
            # 注入资源：主卡片与详情页 JS
            assets = [
                f"/qweather-local/qweather-card/qweather-card.js?v={version}",
                f"/qweather-local/qweather-card/qweather-more-info.js?v={version}"
            ]
            
            for url in assets:
                frontend.add_extra_js_url(hass, url)
                
            hass.data[f"{DOMAIN}_assets"] = True
            LOGGER.info("QWeather Lovelace 资源注册成功 (v%s)", version)

    # 3. 初始化协调器
    # 此时 entry.title 已经在 config_flow 阶段被锁定为城市名
    coordinator = QWeatherUpdateCoordinator(hass, entry, version)
    
    # 执行初次刷新获取数据
    await coordinator.async_config_entry_first_refresh()

    # 4. 存储 runtime_data 并加载平台
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # 5. 注册选项更新监听器
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True

async def async_reload_entry(hass: HomeAssistant, entry: QWeatherConfigEntry) -> None:
    """当用户在 UI 修改配置选项时，重新加载整个集成."""
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: QWeatherConfigEntry) -> bool:
    """卸载集成实例."""
    # 卸载所有平台 (sensor, weather)
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)