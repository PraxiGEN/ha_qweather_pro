"""QWeather (和风天气) 集成入口."""
from __future__ import annotations

import asyncio
import inspect
import os
from dataclasses import dataclass, field

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryState,
    ConfigSubentry,
)
from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_HOST
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
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
    CONF_CUSTOM_MORE_INFO, CONF_LOCATION_ID, CONF_API_KEY, CONF_PROJECT_ID,
    CONF_KEY_ID, CONF_PRIVATE_KEY, CONF_ISS, ACCOUNT_DATA_KEYS,
    SUBENTRY_TYPE_LOCATION, get_location_subentries, location_options_data,
)
from .coordinator import QWeatherUpdateCoordinator, CACHE_STORE_VERSION
from .services import async_setup_services

# 本集成只能通过 UI 配置流添加，YAML 无配置项（hassfest CONFIG_SCHEMA 规范）
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
# Repairs 条目 ID 前缀：引导仍用 API KEY 的用户迁移 JWT
ISSUE_API_KEY_QUOTA = "api_key_quota"
# 同 host 合并迁移锁：同域条目启动加载并发，迁移主体须串行
MIGRATION_LOCK_KEY = f"{DOMAIN}_migration_lock"
# 延迟删除轮询需等待离开的状态（2026.6 迁移全程即 SETUP_IN_PROGRESS）
_MIGRATION_BUSY_STATES = (
    ConfigEntryState.SETUP_IN_PROGRESS,
    ConfigEntryState.UNLOAD_IN_PROGRESS,
)

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

def _async_move_entry_devices(
    hass: HomeAssistant, from_entry_id: str, to_entry_id: str, subentry_id: str
) -> None:
    """把条目设备显式移动到目标条目的 location 子条目（须在实体加载前，避免隐式迁移弃用警告）."""
    device_registry = dr.async_get(hass)
    params = inspect.signature(device_registry.async_update_device).parameters
    for device in dr.async_entries_for_config_entry(device_registry, from_entry_id):
        if (
            to_entry_id in device.config_entries
            and device.config_entries_subentries.get(to_entry_id) == subentry_id
        ):
            continue
        if "new_config_entry_id" in params:
            device_registry.async_update_device(
                device.id,
                new_config_entry_id=to_entry_id,
                new_config_subentry_id=subentry_id,
            )
        else:
            # 2026.1–2026.7：add 与 remove 必须分两次调用——同调用的 remove 分支
            # 按调用前映射表整体覆盖，会丢弃 add 分支刚写入的键（2026.1.0 core 行为实证）。
            device_registry.async_update_device(
                device.id,
                add_config_entry_id=to_entry_id,
                add_config_subentry_id=subentry_id,
            )
            device_registry.async_update_device(
                device.id,
                remove_config_entry_id=from_entry_id,
                remove_config_subentry_id=None,
            )

def _async_move_entry_entities(
    hass: HomeAssistant, from_entry_id: str, to_entry_id: str, subentry_id: str
) -> int:
    """把条目现有实体跨条目搬移到目标条目的 location 子条目（实体先于设备搬移）."""
    entity_registry = er.async_get(hass)
    count = 0
    for registry_entry in er.async_entries_for_config_entry(entity_registry, from_entry_id):
        entity_registry.async_update_entity(
            registry_entry.entity_id,
            config_entry_id=to_entry_id,
            config_subentry_id=subentry_id,
        )
        count += 1
    return count

def _location_subentry_uid(coords: str, entry_id: str, taken: set[str]) -> str:
    """位置子条目 unique_id，冲突时以 entry_id 片段兜底（重复位置条目合并场景）."""
    uid = f"qw_{coords.replace(',', '_')}"
    return uid if uid not in taken else f"{uid}_{entry_id[:8]}"

def _async_absorb_entry(
    hass: HomeAssistant, base: QWeatherConfigEntry, member: QWeatherConfigEntry
) -> bool:
    """把同 host 成员条目吸收为 base 的 location 子条目."""
    ce = hass.config_entries
    taken_uids = {
        s.unique_id for s in get_location_subentries(base) if s.unique_id
    }

    if member.version >= 2:
        # 已迁移父条目：子条目原样并入（data 已含位置+options）
        for sub in get_location_subentries(member):
            uid = sub.unique_id
            if uid and uid in taken_uids:
                uid = f"{uid}_{sub.subentry_id[:8]}"
            ce.async_add_subentry(
                base,
                ConfigSubentry(
                    subentry_type=sub.subentry_type,
                    title=sub.title,
                    data=dict(sub.data),
                    unique_id=uid,
                    subentry_id=sub.subentry_id,
                ),
            )
            taken_uids.add(uid)
    else:
        location_id = member.data.get(CONF_LOCATION_ID)
        if not location_id:
            LOGGER.error(
                "QWeather 同 host 合并：条目 %s 缺少位置数据，无法吸收；请删除后重新添加",
                member.title,
            )
            return False
        uid = _location_subentry_uid(location_id, member.entry_id, taken_uids)
        ce.async_add_subentry(
            base,
            ConfigSubentry(
                subentry_type=SUBENTRY_TYPE_LOCATION,
                title=member.title,
                data={
                    CONF_LOCATION_ID: location_id,
                    **location_options_data(
                        bool(member.data.get(CONF_USE_TOKEN)), member.options
                    ),
                },
                unique_id=uid,
                subentry_id=member.entry_id,
            ),
        )
        taken_uids.add(uid)

    # 实体先搬、设备后搬（跨条目；均为同步注册表操作）
    _async_move_entry_entities(hass, member.entry_id, base.entry_id, member.entry_id)
    _async_move_entry_devices(hass, member.entry_id, base.entry_id, member.entry_id)

    if member.version < 2:
        # 置 v2 使其自身并发迁移短路，空壳设置完成后再由延迟任务移除
        ce.async_update_entry(member, version=2, minor_version=1)

    hass.async_create_task(_async_remove_absorbed_entry(hass, member.entry_id))
    LOGGER.info(
        "QWeather 同 host 合并：条目 %s 的位置已并入账号条目 %s",
        member.title, base.title,
    )
    return True

async def _async_remove_absorbed_entry(hass: HomeAssistant, entry_id: str) -> None:
    """延迟移除被吸收的冗余条目（等待其自身设置流程退出后再删，避免 setup_lock 死锁）."""
    ce = hass.config_entries
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 120
    while (entry := ce.async_get_entry(entry_id)) is not None:
        if entry.state not in _MIGRATION_BUSY_STATES:
            try:
                await ce.async_remove(entry_id)
                LOGGER.info("QWeather 同 host 合并：已移除被吸收的冗余条目 %s", entry.title)
            except Exception:  # noqa: BLE001 - 删除失败不阻断迁移，交由用户手动清理
                LOGGER.exception(
                    "QWeather 同 host 合并：移除冗余条目 %s 失败，请手动删除", entry_id
                )
            return
        if loop.time() > deadline:
            LOGGER.warning(
                "QWeather 同 host 合并：等待条目 %s 完成设置超时，未自动删除，请手动删除",
                entry_id,
            )
            return
        await asyncio.sleep(0.5)

def _async_upgrade_base_to_parent(hass: HomeAssistant, base: QWeatherConfigEntry) -> bool:
    """把 v1 条目原地升级为账号父条目（uid/title=host，凭据留 data，位置进子条目）."""
    ce = hass.config_entries
    host = base.data.get(CONF_HOST, "").strip()
    location_id = base.data.get(CONF_LOCATION_ID)
    if not host or not location_id:
        LOGGER.error(
            "QWeather 条目 %s 缺少 host 或位置数据，无法迁移；请删除后重新添加", base.title
        )
        return False
    subentry = ConfigSubentry(
        subentry_type=SUBENTRY_TYPE_LOCATION,
        title=base.title,
        data={
            CONF_LOCATION_ID: location_id,
            **location_options_data(bool(base.data.get(CONF_USE_TOKEN)), base.options),
        },
        unique_id=_location_subentry_uid(location_id, base.entry_id, set()),
        subentry_id=base.entry_id,
    )
    try:
        ce.async_add_subentry(base, subentry)
    except Exception:  # noqa: BLE001 - 迁移失败不静默：记日志并置 MIGRATION_ERROR
        LOGGER.exception("QWeather 条目 %s 迁移失败（创建子条目）", base.title)
        return False
    try:
        _async_move_entry_devices(hass, base.entry_id, base.entry_id, base.entry_id)
    except Exception:  # noqa: BLE001 - 设备移动失败不阻断迁移（实体加载仍会隐式迁移）
        LOGGER.exception("QWeather 条目 %s 迁移：设备显式移动到子条目失败", base.title)
    ce.async_update_entry(
        base,
        # 凭据白名单：剥离位置与 legacy 死键（如 reuse_from）
        data={k: v for k, v in base.data.items() if k in ACCOUNT_DATA_KEYS},
        options={},  # R4：options 全部下沉子条目，父条目 options 清空
        unique_id=host,  # R1：账号身份 = host
        title=host,  # R3：账号名 = host
        version=2,
        minor_version=1,
    )
    return True

async def async_migrate_entry(hass: HomeAssistant, entry: QWeatherConfigEntry) -> bool:
    """v1→v2：按 host 分组合并，旧条目升级为账号父条目 + location 子条目."""
    if entry.version > 2:
        LOGGER.error(
            "QWeather 条目 %s 的数据版本 %s 高于当前支持的版本，无法降级加载",
            entry.title, entry.version,
        )
        return False
    if entry.version < 1:
        return False
    if entry.version == 2:
        return True

    lock = hass.data.setdefault(MIGRATION_LOCK_KEY, asyncio.Lock())
    async with lock:
        # 并发迁移下可能已被同组 base 吸收并移除，或其 version 已被置为 2
        if hass.config_entries.async_get_entry(entry.entry_id) is None:
            return True
        if entry.version == 2:
            return True
        try:
            ok = await _async_migrate_v1_to_v2(hass, entry)
        except Exception:  # noqa: BLE001 - 迁移失败不静默：记日志并置 MIGRATION_ERROR
            LOGGER.exception("QWeather 条目 %s 迁移失败", entry.title)
            ok = False
        return ok


async def _async_migrate_v1_to_v2(hass: HomeAssistant, entry: QWeatherConfigEntry) -> bool:
    """R2 合并主体（调用方已持迁移锁）。"""
    ce = hass.config_entries
    host = (entry.data.get(CONF_HOST) or "").strip()
    if not host:
        LOGGER.error("QWeather 条目 %s 缺少 API Host，无法迁移；请删除后重新添加", entry.title)
        return False

    # 1. 按 host 分组（同域条目的迁移因锁串行，组内 v1 数据读取是稳定的）
    group = [
        e for e in ce.async_entries(DOMAIN)
        if e.source != "ignore" and (e.data.get(CONF_HOST) or "").strip() == host
    ]

    # 2. 选 base：已迁移 v2 父条目优先 → JWT 凭据优先（R6：API KEY+JWT 并存也合并）
    base = next(
        (e for e in group if e.version >= 2),
        next((e for e in group if e.data.get(CONF_USE_TOKEN)), group[0]),
    )

    # 3. base 升级为父条目（仍为 v1 时）
    if base.version < 2 and not _async_upgrade_base_to_parent(hass, base):
        return False

    # 4. 组内其余条目逐个吸收（含已迁移父条目的子条目整体并入）
    for member in group:
        if member.entry_id == base.entry_id:
            continue
        if not _async_absorb_entry(hass, base, member):
            return False

    # 运行期并入已加载的 base 需重载；启动期则自然以全量子条目首设
    if base.state is ConfigEntryState.LOADED:
        ce.async_schedule_reload(base.entry_id)
    return True

async def async_setup_entry(hass: HomeAssistant, entry: QWeatherConfigEntry) -> bool:
    """设置配置条目（账号级：一次建 API 客户端，逐位置建协调器）."""

    # 幽灵条目守卫：已被合并移除的条目跳过设置（排队任务仍可能执行到此处）
    if hass.config_entries.async_get_entry(entry.entry_id) is None:
        LOGGER.debug("QWeather 条目 %s 已被同 host 合并移除，跳过空壳设置", entry.entry_id)
        return True

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
    location_subentries = get_location_subentries(entry)
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
    for subentry in get_location_subentries(entry):
        coordinator = QWeatherUpdateCoordinator(hass, entry, subentry, api, version)
        await coordinator.async_load_cache()
        runtime.coordinators[subentry.subentry_id] = coordinator
    # 存量引导：仍用 API KEY 的用户推送 Repairs 条目，引导迁移 JWT。
    await _async_refresh_api_key_issue(hass, entry)
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
    """条目/子条目变更时重载；顺带清理已删除位置的孤儿缓存（core 只清设备实体 issue）."""
    runtime = getattr(entry, "runtime_data", None)
    if isinstance(runtime, QWeatherRuntimeData):
        current_ids = {s.subentry_id for s in get_location_subentries(entry)}
        for removed_id in runtime.coordinators.keys() - current_ids:
            store = Store(hass, CACHE_STORE_VERSION, f"{DOMAIN}_cache_{removed_id}")
            await store.async_remove()
            LOGGER.debug("QWeather 已清理已删除位置的缓存: %s", removed_id)
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: QWeatherConfigEntry) -> bool:
    """卸载集成实例；自定义 UI 为注入到整个前端的全局资源，仅当无其他实例启用时聚合注销。"""
    # 先卸载所有平台 (sensor, weather)，成功后再做全局清理
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False

    # 全局前端资源：本条目卸载时若无其他条目启用则清理，避免污染全部前端
    def _entry_wants_frontend(e: QWeatherConfigEntry) -> bool:
        return any(
            s.data.get(CONF_CUSTOM_UI) or s.data.get(CONF_CUSTOM_MORE_INFO)
            for s in get_location_subentries(e)
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
    # 清理本条目的 API KEY 迁移引导（禁用/卸载后不应残留；reload 时 setup 会重建）
    async_delete_issue(hass, DOMAIN, _api_key_issue_id(entry))
    return True