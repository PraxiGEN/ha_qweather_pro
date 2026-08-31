"""QWeather (和风天气) 集成入口."""
from __future__ import annotations

import os

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration
from homeassistant.components.http import StaticPathConfig
from homeassistant.components import frontend
from homeassistant.helpers.issue_registry import (
    async_create_issue,
    async_delete_issue,
    IssueSeverity,
)

from .const import DOMAIN, PLATFORMS, LOGGER, CONF_USE_TOKEN, CONF_CUSTOM_UI, CONF_CUSTOM_MORE_INFO
from .coordinator import QWeatherUpdateCoordinator
from .services import async_setup_services

# 定义强类型别名，便于 IDE 补全 runtime_data
type QWeatherConfigEntry = ConfigEntry[QWeatherUpdateCoordinator]

# 本集成只能通过 UI 配置流添加，YAML 无配置项（hassfest CONFIG_SCHEMA 规范）
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
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

    local_path = hass.config.path("custom_components", DOMAIN, "www")
    path_exists = await hass.async_add_executor_job(os.path.exists, local_path)

    # 静态资源路径只注册一次（重复注册会抛错），用独立标志，避免被「资源注入」
    if path_exists and f"{DOMAIN}_static_path" not in hass.data:
        await hass.http.async_register_static_paths([
            StaticPathConfig("/qweather_pro-local", local_path, False)
        ])
        hass.data[f"{DOMAIN}_static_path"] = True
    # 按开关计算需要注入的前端 JS；add_extra_js_url 幂等（同 URL 不重复添加），
    names: list[str] = []
    if entry.options.get(CONF_CUSTOM_UI):
        names += ["qweather-pro-card.js", "qweather-pro-i18n.js"]
    if entry.options.get(CONF_CUSTOM_MORE_INFO):
        names += ["qweather-pro-more-info.js", "qweather-pro-i18n.js"]
    if path_exists and names:
        # 注册资源 URL 携带集成版本号：升版后 URL 随之变化，自然绕开浏览器旧缓存
        for name in dict.fromkeys(names):
            frontend.add_extra_js_url(hass, f"/qweather_pro-local/{name}?v={version}")
        LOGGER.info("QWeather Lovelace 资源已注册: %s", ", ".join(dict.fromkeys(names)))
    elif not names:
        # 两个开关均未启用：不向全局前端注入资源（HACS 合规，避免无条件污染所有前端）
        LOGGER.debug("自定义 UI / 原生详情覆盖均未启用，跳过 Lovelace 资源注册")

    coordinator = QWeatherUpdateCoordinator(hass, entry, version)
    await coordinator.async_load_cache()
    # 存量引导：仍用 API KEY 的用户推送 Repairs 条目，引导迁移 JWT。
    await _async_refresh_api_key_issue(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
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
        is_persistent=True,
        translation_key="api_key_quota",
    )

async def async_reload_entry(hass: HomeAssistant, entry: QWeatherConfigEntry) -> None:
    """当用户在 UI 修改配置选项时，重新加载整个集成."""
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: QWeatherConfigEntry) -> bool:
    """卸载集成实例；自定义 UI 为注入到整个前端的全局资源，仅当无其他实例启用时聚合注销。"""
    # 自定义 UI / 详情覆盖 是注入到整个 HA 前端的全局资源（add_extra_js_url 幂等注册）。
    # 本实例卸载时，若没有其他实例仍启用这些资源，则主动清理，避免全局资源残留污染所有前端。
    other_entries = [e for e in hass.config_entries.async_entries(DOMAIN) if e.entry_id != entry.entry_id]
    still_ui = any(
        e.options.get(CONF_CUSTOM_UI) or e.options.get(CONF_CUSTOM_MORE_INFO)
        for e in other_entries
    )
    if not still_ui:
        names: list[str] = []
        if entry.options.get(CONF_CUSTOM_UI):
            names += ["qweather-pro-card.js", "qweather-pro-i18n.js"]
        if entry.options.get(CONF_CUSTOM_MORE_INFO):
            names += ["qweather-pro-more-info.js", "qweather-pro-i18n.js"]
        if names:
            integration = await async_get_integration(hass, DOMAIN)
            version = str(integration.version) if integration.version else "1.0.0"
            # 2026.1.0 仅暴露同步 remove_extra_js_url（无 async 变体）；优先 async 若存在以兼容未来版本。
            for name in dict.fromkeys(names):
                url = f"/qweather_pro-local/{name}?v={version}"
                try:
                    if hasattr(frontend, "async_remove_extra_js_url"):
                        await frontend.async_remove_extra_js_url(hass, url)
                    else:
                        frontend.remove_extra_js_url(hass, url)
                except Exception:  # noqa: BLE001 - 资源已不存在/未注册等情况可忽略
                    LOGGER.debug("清理前端资源失败(可忽略): %s", name)
            LOGGER.info("QWeather 全局前端资源已聚合注销: %s", ", ".join(dict.fromkeys(names)))
    # 卸载所有平台 (sensor, weather)
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)