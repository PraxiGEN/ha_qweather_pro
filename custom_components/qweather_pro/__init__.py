"""QWeather (和风天气) 集成入口."""
from __future__ import annotations

import asyncio
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
# Repairs 条目 ID 前缀：引导仍用 API KEY 的用户迁移 JWT
ISSUE_API_KEY_QUOTA = "api_key_quota"

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """初始化集成（服务注册在 setup_entry 中幂等完成，随末条目卸载注销）"""
    return True

# 本集成注入前端的所有资源 URL 的公共前缀（含任意 ?v= 版本号）
_FRONTEND_URL_PREFIX = "/qweather_pro-local/"

def _list_stale_frontend_js(hass: HomeAssistant) -> list[str]:
    """枚举前端中本集成已注册的全部资源 URL（任意 ?v= 版本号）."""
    manager = getattr(frontend, "DATA_EXTRA_MODULE_URL", None)
    url_manager = hass.data.get(manager) if manager is not None else None
    urls = getattr(url_manager, "urls", None) or ()
    return [u for u in urls if isinstance(u, str) and u.startswith(_FRONTEND_URL_PREFIX)]

async def _async_remove_stale_frontend_js(hass: HomeAssistant) -> int:
    """按前缀清理前端残留的本集成 JS 资源（兼容历史 ?v= 版本号不匹配）."""
    stale = _list_stale_frontend_js(hass)
    for url in stale:
        try:
            # 2026.1.0 仅暴露同步 remove_extra_js_url；优先 async 以兼容未来版本
            if hasattr(frontend, "async_remove_extra_js_url"):
                await frontend.async_remove_extra_js_url(hass, url)
            else:
                frontend.remove_extra_js_url(hass, url)
        except Exception:  # noqa: BLE001 - 资源已不存在/未注册等情况可忽略
            LOGGER.debug("清理前端资源失败(可忽略): %s", url)
    return len(stale)

async def async_setup_entry(hass: HomeAssistant, entry: QWeatherConfigEntry) -> bool:
    """设置配置条目."""

    integration = await async_get_integration(hass, DOMAIN)
    version = str(integration.version) if integration.version else "1.0.0"

    # 自定义服务注册（幂等）：随条目加载注册、末条目卸载时注销
    await async_setup_services(hass)

    local_path = hass.config.path("custom_components", DOMAIN, "www")
    path_exists = await hass.async_add_executor_job(os.path.exists, local_path)

    # 静态资源路径只注册一次（重复注册同一 URL 会抛错、条目加载失败）。
    if path_exists:
        lock = hass.data.setdefault(f"{DOMAIN}_static_path_lock", asyncio.Lock())
        async with lock:
            if f"{DOMAIN}_static_path" not in hass.data:
                await hass.http.async_register_static_paths([
                    StaticPathConfig(_FRONTEND_URL_PREFIX.rstrip("/"), local_path, False)
                ])
                hass.data[f"{DOMAIN}_static_path"] = True
    # 按开关计算需要注入的前端 JS；add_extra_js_url 幂等（同 URL 不重复添加），
    names: list[str] = []
    if entry.options.get(CONF_CUSTOM_UI):
        names += ["qweather-pro-card.js", "qweather-pro-i18n.js"]
    if entry.options.get(CONF_CUSTOM_MORE_INFO):
        names += ["qweather-pro-more-info.js", "qweather-pro-i18n.js"]
    if path_exists and names:
        # 先清理历史版本残留（?v= 变化后旧 URL 精确移除会失配），再注册当前版本
        if stale := await _async_remove_stale_frontend_js(hass):
            LOGGER.debug("QWeather 已清理历史版本前端资源 %s 项", stale)
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

def _api_key_issue_id(entry: QWeatherConfigEntry) -> str:
    """按条目隔离的 API KEY 迁移引导 issue ID."""
    return f"{ISSUE_API_KEY_QUOTA}_{entry.entry_id}"

async def _async_refresh_api_key_issue(hass: HomeAssistant, entry: QWeatherConfigEntry) -> None:
    """仍用 API KEY 时推送 Repairs 引导迁移 JWT；已用 JWT 则清理本条目的引导."""
    # 旧版本使用全局固定 ID，跨版本升级后可能残留，无条件清理（幂等无害）
    async_delete_issue(hass, DOMAIN, ISSUE_API_KEY_QUOTA)
    issue_id = _api_key_issue_id(entry)
    if entry.data.get(CONF_USE_TOKEN):
        async_delete_issue(hass, DOMAIN, issue_id)
        return
    async_create_issue(
        hass,
        DOMAIN,
        issue_id,
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
    # 先卸载所有平台 (sensor, weather)，成功后再做全局清理
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False

    # 自定义 UI / 详情覆盖 是注入到整个 HA 前端的全局资源（add_extra_js_url 幂等注册）。
    # 本实例卸载时，若没有其他实例仍启用这些资源，则主动清理，避免全局资源残留污染所有前端。
    other_entries = [e for e in hass.config_entries.async_entries(DOMAIN) if e.entry_id != entry.entry_id]
    still_ui = any(
        e.options.get(CONF_CUSTOM_UI) or e.options.get(CONF_CUSTOM_MORE_INFO)
        for e in other_entries
    )
    if not still_ui:
        # 按前缀清理本集成的全部前端资源（覆盖 ?v= 版本号失配的历史残留）
        if stale := await _async_remove_stale_frontend_js(hass):
            LOGGER.info("QWeather 全局前端资源已聚合注销: %s 项", stale)
    # 若本实例是最后一个条目：注销自定义服务（下次任一条目加载时幂等重注册）
    if not other_entries and hass.services.has_service(DOMAIN, "get_weather"):
        hass.services.async_remove(DOMAIN, "get_weather")
        LOGGER.debug("QWeather get_weather 服务已随末条目卸载注销")
    # 清理本条目的 API KEY 迁移引导（禁用/卸载后不应残留；reload 时 setup 会重建）
    async_delete_issue(hass, DOMAIN, _api_key_issue_id(entry))
    return True
