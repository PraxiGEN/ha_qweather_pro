"""QWeather (和风天气) 集成入口."""
from __future__ import annotations

import asyncio
import inspect
import os
from dataclasses import dataclass, field
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.loader import async_get_integration
from homeassistant.components.http import StaticPathConfig
from homeassistant.components import frontend
from homeassistant.helpers.issue_registry import (
    async_create_issue,
    async_delete_issue,
    IssueSeverity,
)
from homeassistant.helpers.storage import Store

from .api import QWeatherAPI
from .const import (
    DOMAIN, PLATFORMS, LOGGER, CONF_USE_TOKEN, CONF_CUSTOM_UI,
    CONF_CUSTOM_MORE_INFO, CONF_API_KEY, CONF_PROJECT_ID,
    CONF_KEY_ID, CONF_PRIVATE_KEY, CONF_ISS,
    SUBENTRY_TYPE_LOCATION,
)
from .coordinator import QWeatherUpdateCoordinator, CACHE_STORE_VERSION
from .services import async_setup_services

# 本集成只能通过 UI 配置流添加，YAML 无配置项（hassfest CONFIG_SCHEMA 规范）
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
# Repairs 条目 ID 前缀：引导仍用 API KEY 的用户迁移 JWT
ISSUE_API_KEY_QUOTA = "api_key_quota"
# Repairs 条目 ID 前缀：v1 旧版条目拒绝提示（2.0.0 起不支持 1.2.x 直升）
ISSUE_LEGACY_ENTRY = "legacy_entry"

@dataclass
class QWeatherRuntimeData:
    """账号条目运行时数据：共享 API 客户端 + 各位置协调器."""
    api: QWeatherAPI
    coordinators: dict[str, QWeatherUpdateCoordinator] = field(default_factory=dict)

# 定义强类型别名，便于 IDE 补全 runtime_data
type QWeatherConfigEntry = ConfigEntry[QWeatherRuntimeData]

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

async def async_migrate_entry(hass: HomeAssistant, entry: QWeatherConfigEntry) -> bool:
    """拒绝 v1 旧版条目：2.0.0 起不支持 1.2.x 直升，须先经 1.3.x 完成迁移."""
    # version > 2 由 core 自拦（handler.VERSION=2）；version==2 不会进入迁移
    if entry.version >= 2:
        return True
    issue_id = f"{ISSUE_LEGACY_ENTRY}_{entry.entry_id}"
    # 2026.10+ issue 可归属条目随条目删除自动清理；2026.9 无此参数则全局留存，升级成功后由 setup 清理
    create_kwargs: dict[str, Any] = {}
    if "config_entry_id" in inspect.signature(async_create_issue).parameters:
        create_kwargs["config_entry_id"] = entry.entry_id
    async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=False,
        severity=IssueSeverity.ERROR,
        is_persistent=True,
        translation_key="legacy_entry",
        **create_kwargs,
    )
    LOGGER.error(
        "QWeather 条目 %s 为 v1 旧版数据：2.0.0 不再支持直接升级，请先安装 1.3.x 完成迁移后再升级",
        entry.title,
    )
    return False

async def async_setup_entry(hass: HomeAssistant, entry: QWeatherConfigEntry) -> bool:
    """设置配置条目（账号级：一次建 API 客户端，逐位置建协调器）."""
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
    # 前端 JS 按子条目 options 并集注入（add_extra_js_url 幂等）
    location_subentries = entry.get_subentries_of_type(SUBENTRY_TYPE_LOCATION)
    names: list[str] = []
    if any(s.data.get(CONF_CUSTOM_UI) for s in location_subentries):
        names += ["qweather-pro-card.js", "qweather-pro-i18n.js"]
    if any(s.data.get(CONF_CUSTOM_MORE_INFO) for s in location_subentries):
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

    api = QWeatherAPI(
        session=async_get_clientsession(hass),
        api_key=entry.data.get(CONF_API_KEY),
        use_token=entry.data.get(CONF_USE_TOKEN),
        project_id=entry.data.get(CONF_PROJECT_ID),
        key_id=entry.data.get(CONF_KEY_ID),
        private_key=entry.data.get(CONF_PRIVATE_KEY),
        iss=entry.data.get(CONF_ISS),
        host=entry.data.get("host"),
    )
    runtime = QWeatherRuntimeData(api=api)
    for subentry in entry.get_subentries_of_type(SUBENTRY_TYPE_LOCATION):
        coordinator = QWeatherUpdateCoordinator(hass, entry, subentry, api, version)
        await coordinator.async_load_cache()
        runtime.coordinators[subentry.subentry_id] = coordinator
    # 存量引导：仍用 API KEY 的用户推送 Repairs 条目，引导迁移 JWT。
    await _async_refresh_api_key_issue(hass, entry)
    # v1 拒绝 issue 在条目成功升级（1.3.x 迁移后升 2.0.0）时清理
    async_delete_issue(hass, DOMAIN, f"{ISSUE_LEGACY_ENTRY}_{entry.entry_id}")
    # 任一位置首刷失败 → 整条目 NotReady 重试（与单位置时代语义一致）
    for coordinator in runtime.coordinators.values():
        await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = runtime
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True

def _api_key_issue_id(entry: QWeatherConfigEntry) -> str:
    """按条目隔离的 API KEY 迁移引导 issue ID（账号级）."""
    return f"{ISSUE_API_KEY_QUOTA}_{entry.entry_id}"

async def _async_refresh_api_key_issue(hass: HomeAssistant, entry: QWeatherConfigEntry) -> None:
    """仍用 API KEY 时推送 Repairs 引导迁移 JWT；已用 JWT 则清理本条目的引导."""
    # 旧版本使用全局固定 ID，跨版本升级后可能残留，无条件清理（幂等无害）
    async_delete_issue(hass, DOMAIN, ISSUE_API_KEY_QUOTA)
    issue_id = _api_key_issue_id(entry)
    if entry.data.get(CONF_USE_TOKEN):
        async_delete_issue(hass, DOMAIN, issue_id)
        return
    # 2026.11+ issue 可归属条目，由 core 随条目删除自动清理（unload 不再删）；旧版仍须手动清理
    create_kwargs: dict[str, Any] = {}
    if "config_entry_id" in inspect.signature(async_create_issue).parameters:
        create_kwargs["config_entry_id"] = entry.entry_id
    async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=False,
        severity=IssueSeverity.WARNING,
        is_persistent=True,
        translation_key="api_key_quota",
        **create_kwargs,
    )

async def async_reload_entry(hass: HomeAssistant, entry: QWeatherConfigEntry) -> None:
    """条目/子条目变更时重载；顺带清理已删除位置的孤儿缓存（core 只清设备实体 issue）."""
    runtime = getattr(entry, "runtime_data", None)
    if isinstance(runtime, QWeatherRuntimeData):
        current_ids = {s.subentry_id for s in entry.get_subentries_of_type(SUBENTRY_TYPE_LOCATION)}
        for removed_id in runtime.coordinators.keys() - current_ids:
            store = Store(hass, CACHE_STORE_VERSION, f"{DOMAIN}_cache_{removed_id}")
            await store.async_remove()
            LOGGER.debug("QWeather 已清理已删除位置的缓存: %s", removed_id)
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: QWeatherConfigEntry) -> bool:
    """卸载集成实例；自定义 UI 为注入到整个前端的全局资源，仅当无其他实例启用时聚合注销。"""
    # 先卸载所有平台 (sensor, weather)，成功后再做全局清理
    # 2026.11+ 用 or_raise 抛翻译化 ConfigEntryError；旧版保留布尔返回
    ce = hass.config_entries
    if hasattr(ce, "async_unload_platforms_or_raise"):
        await ce.async_unload_platforms_or_raise(entry, PLATFORMS)
    elif not await ce.async_unload_platforms(entry, PLATFORMS):
        return False

    # 全局前端资源：本条目卸载时若无其他条目启用则清理，避免污染全部前端
    def _entry_wants_frontend(e: QWeatherConfigEntry) -> bool:
        return any(
            s.data.get(CONF_CUSTOM_UI) or s.data.get(CONF_CUSTOM_MORE_INFO)
            for s in e.get_subentries_of_type(SUBENTRY_TYPE_LOCATION)
        )

    other_entries = [e for e in hass.config_entries.async_entries(DOMAIN) if e.entry_id != entry.entry_id]
    still_ui = any(_entry_wants_frontend(e) for e in other_entries)
    if not still_ui:
        # 按前缀清理本集成的全部前端资源（覆盖 ?v= 版本号失配的历史残留）
        if stale := await _async_remove_stale_frontend_js(hass):
            LOGGER.info("QWeather 全局前端资源已聚合注销: %s 项", stale)
    # 若本实例是最后一个条目：注销自定义服务（下次任一条目加载时幂等重注册）
    if not other_entries and hass.services.has_service(DOMAIN, "get_weather"):
        hass.services.async_remove(DOMAIN, "get_weather")
        LOGGER.debug("QWeather get_weather 服务已随末条目卸载注销")
    # 旧版本 issue 不归属条目，须手动清理；2026.11+ 由 core 随条目删除自动管理，unload 不删
    if "config_entry_id" not in inspect.signature(async_create_issue).parameters:
        async_delete_issue(hass, DOMAIN, _api_key_issue_id(entry))
    return True