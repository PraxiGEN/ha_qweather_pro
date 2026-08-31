"""QWeather (和风天气) 数据协调器."""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
import homeassistant.util.dt as dt_util

from .api import QWeatherAPI
from .const import (
    DOMAIN, CONF_API_KEY, CONF_LOCATION_ID, CONF_USE_TOKEN,
    CONF_PROJECT_ID, CONF_KEY_ID, CONF_PRIVATE_KEY, CONF_ISS,
    SUGGESTION_TYPE_MAP, CONF_DAILYSTEPS, CONF_HOURLYSTEPS,
    resolve_update_interval, LANGUAGE_MAP, LOGGER
)
from .condition import CONDITION_MAP

# 各数据缓存有效期（秒）
TTL_DAILY = 7200        # 每日预报：模型更新慢，2h 足够
TTL_HOURLY = 3600       # 逐小时预报：1h 足够
TTL_AIR = 3600          # 空气质量：监测站整点发布
TTL_INDICES = 3600      # 生活指数：官方 1h 更新，对齐频率
TTL_MINUTELY = 900      # 分钟级降水：最耗额度，15min 一次
TTL_WARNING = 300        # 预警：官方 5min 更新

# 持久化缓存存储版本（.storage/<DOMAIN>_cache_<entry_id>）
CACHE_STORE_VERSION = 1

class QWeatherUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """QWeather 数据异步调度中心."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, version: str) -> None:
        """初始化协调器."""
        self.entry = entry
        self.version = version
        self.location = entry.data.get(CONF_LOCATION_ID)
        self.city_name = entry.title
        self._consecutive_failures = 0 # 追踪连续失败次数

        update_min = resolve_update_interval(
            entry.options, bool(entry.data.get(CONF_USE_TOKEN))
        )
        self._base_interval = timedelta(minutes=update_min)
        # 跨重启持久化缓存（避免重启瞬间全端点重拉；纯缓存，不限制请求）
        self._store = Store(hass, CACHE_STORE_VERSION, f"{DOMAIN}_cache_{entry.entry_id}")

        # 初始化 API 客户端
        self.api = QWeatherAPI(
            session=async_get_clientsession(hass), 
            api_key=entry.data.get(CONF_API_KEY),
            use_token=entry.data.get(CONF_USE_TOKEN),
            project_id=entry.data.get(CONF_PROJECT_ID),
            key_id=entry.data.get(CONF_KEY_ID),
            private_key=entry.data.get(CONF_PRIVATE_KEY),
            iss=entry.data.get(CONF_ISS),
            host=entry.data.get("host")
        )

        super().__init__(
            hass, LOGGER, name=DOMAIN,
            update_interval=self._base_interval,
        )

        # 初始化本地持久化缓存
        self._cache_data: dict[str, Any] = {
            "now": {}, "daily": {}, "hourly": {}, "air": {}, 
            "indices": {}, "warning": {}, "minutely": {}
        }
        self._last_update_times: dict[str, float] = {}
        # 缓存新鲜度元数据: {category: {"fetched_at": 时间戳, "fresh": 本轮是否成功更新}}
        self._cache_meta: dict[str, dict] = {}

    def _should_update(self, category: str, ttl: int) -> bool:
        """分时更新判断."""
        now_ts = time.time()
        now_dt = dt_util.now()
        is_night = 0 <= now_dt.hour < 5
        actual_ttl = ttl * 2 if is_night else ttl
        last_time = self._last_update_times.get(category, 0)
        result = (now_ts - last_time) > actual_ttl

        if result and is_night:
            LOGGER.debug("QWeather 深夜降频模式生效: %s 将在 %s 秒后更新", category, actual_ttl)

        return result

    # --- 持久化缓存 ---
    async def async_load_cache(self) -> None:
        """启动时从 .storage 恢复缓存（含各端点时间戳），避免重启全拉。"""
        try:
            data = await self._store.async_load()
        except Exception as err:  # noqa: BLE001 - 加载失败不应阻断启动
            LOGGER.debug("QWeather 持久化缓存加载失败: %s", err)
            return
        if not isinstance(data, dict):
            return
        cache = data.get("cache")
        if isinstance(cache, dict):
            self._cache_data.update(cache)
        updated_at = data.get("updated_at")
        if isinstance(updated_at, dict):
            self._last_update_times.update(updated_at)

    async def async_save_cache(self) -> None:
        """刷新成功后把缓存与时间戳落盘，供下次重启复用。"""
        payload = {
            "cache": dict(self._cache_data),
            "updated_at": dict(self._last_update_times),
        }
        try:
            await self._store.async_save(payload)
        except Exception as err:  # noqa: BLE001 - 保存失败仅记日志
            LOGGER.debug("QWeather 持久化缓存保存失败: %s", err)

    def _to_f(self, val: Any, default: float | None = None) -> float | None:
        """数值安全转换工具."""
        try:
            return float(val)
        except (TypeError, ValueError):
            return default

    # --- V1 单位换算与本地化辅助 ---
    def _percent(self, val: Any, default: float | None = None) -> float | None:
        """V1 比例字段 (0~1) → 百分数 (0-100). 湿度/云量/降水概率通用.

        源值为浮点比例, 直接 ``v * 100`` 会产生 57.9999… 这类精度伪影,
        故对结果取整 (百分比天然为整数粒度, 如 0.58 → 58).
        """
        v = self._to_f(val, default)
        return round(v * 100) if v is not None else None

    def _speed_kmh(self, val: Any, default: float | None = None) -> float | None:
        """V1 风速 (m/s) → km/h (×3.6)，匹配 WeatherEntity 声明的 km/h 单位."""
        v = self._to_f(val, default)
        return round(v * 3.6, 1) if v is not None else None

    def _vis_km(self, val: Any, default: float | None = None) -> float | None:
        """V1 能见度 (m) → km (÷1000)，匹配 WeatherEntity 声明的 km 单位."""
        v = self._to_f(val, default)
        return round(v / 1000) if v is not None else None

    def _to_utc_iso(self, dt_str: str | None) -> str | None:
        """V1 时间字段 (UTC date-time，可能带 Z 后缀) → UTC RFC3339 ISO 字符串."""
        if not dt_str:
            return None
        try:
            parsed = dt_util.parse_datetime(dt_str.replace("Z", "+00:00"))
            if parsed is None:
                return None
            return dt_util.as_utc(parsed).isoformat()
        except (TypeError, ValueError):
            return None

    def _to_local_hm(self, dt_str: str | None) -> str | None:
        """V1 天文时间 (UTC date-time) → HA 本地时区 HH:MM 字符串 (兼容 v7 展示格式)."""
        if not dt_str:
            return None
        try:
            parsed = dt_util.parse_datetime(dt_str.replace("Z", "+00:00"))
            if parsed is None:
                return None
            return dt_util.as_local(parsed).strftime("%H:%M")
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _collect_attributions(cache: dict) -> list[str]:
        """汇总各端点 attributions (V1 规范要求随数据展示)."""
        seen: list[str] = []
        for key in ("now", "daily", "hourly", "air", "warning"):
            meta = cache.get(key, {}).get("metadata", {})
            for url in meta.get("attributions", []):
                if url and url not in seen:
                    seen.append(url)
        return seen

    def _merge_now(self, now_raw: dict, daily_first: dict | None, now_dt: datetime) -> dict:
        """合并实况：current 优先，缺失时以 daily 当前时段兜底并标记 degraded."""
        degraded = False
        now_raw = now_raw or {}
        daily_first = daily_first or {}
        if not now_raw:
            # current 请求失败/完全缺失：整段视为降级数据（即使 daily 也无值可兜）
            degraded = True

        # 时段选择：与 V1 时段定义一致 (本地 07:00-19:00 为白天)
        is_day = 7 <= now_dt.hour < 19
        seg = daily_first.get("daytime" if is_day else "nighttime", {})
        seg = seg if isinstance(seg, dict) else {}

        def pick(cur_val: Any, daily_val: Any, default: Any = None) -> Any:
            """current 优先；缺失时用 daily 兜底并标记 degraded."""
            nonlocal degraded
            if cur_val is not None:
                return cur_val
            if daily_val is not None:
                degraded = True
                return daily_val
            return default

        now_condition = now_raw.get("condition", {})
        now_wind = now_raw.get("wind", {})
        now_wind_dir = now_wind.get("direction", {})
        seg_cond = seg.get("condition", {})
        seg_wind = seg.get("wind", {})
        seg_wind_dir = seg_wind.get("direction", {})

        # 当前温度：current 优先，缺失时用 daily 日均温近似 (temperatureAvg)
        cur_temp = self._to_f(now_raw.get("temperature", {}).get("value"))
        if cur_temp is not None:
            temp = cur_temp
        elif self._to_f(daily_first.get("temperatureAvg", {}).get("value")) is not None:
            temp = self._to_f(daily_first.get("temperatureAvg", {}).get("value"))
            degraded = True
        else:
            temp = None

        # 输出字段顺序与 current API 文档保持一致 (便于对照维护)：
        merged = {
            # condition: {text, code}
            "text_cn": pick(
                now_condition.get("text"), seg_cond.get("text"), "Unknown"),
            "condition": pick(
                CONDITION_MAP.get(now_condition.get("code")),
                CONDITION_MAP.get(seg_cond.get("code")), "exceptional"),
            "icon": pick(now_condition.get("code"), seg_cond.get("code")),
            # temperature: {value, unit}
            "temp": temp,
            # feelsLike: {value, unit}
            "feelsLike": self._to_f(now_raw.get("feelsLike", {}).get("value")),
            # humidity: [0,1]
            "humidity": self._percent(pick(now_raw.get("humidity"), seg.get("humidity")), 0.0),
            # wind: {direction{degree,compass}, speed{value,unit}, scale}
            "wind360": self._to_f(pick(
                now_wind_dir.get("degree"), seg_wind_dir.get("degree")), 0.0),
            "windDir": pick(now_wind_dir.get("compass"), seg_wind_dir.get("compass")),
            "windSpeed": self._speed_kmh(pick(
                now_wind.get("speed", {}).get("value"),
                seg_wind.get("speed", {}).get("value")), 0.0),
            "windScale": pick(now_wind.get("scale"), seg_wind.get("scale")),
            # windGust: {value, unit} (m/s → km/h)
            "windGust": self._speed_kmh(now_raw.get("windGust", {}).get("value"), 0.0),
            # precipitation: {amount{value,unit}, intensity{value,unit}, type}
            "precip": self._to_f(pick(
                now_raw.get("precipitation", {}).get("amount", {}).get("value"),
                seg.get("precipitation", {}).get("amount", {}).get("value")), 0.0),
            "precipIntensity": self._to_f(now_raw.get("precipitation", {}).get("intensity", {}).get("value"), 0.0),
            "precipType": now_raw.get("precipitation", {}).get("type"),
            # pressure: {value, unit}
            "pressure": self._to_f(now_raw.get("pressure", {}).get("value")),
            # visibility: {value, unit} (m → km)
            "vis": self._vis_km(now_raw.get("visibility", {}).get("value")),
            # dewPoint: {value, unit}
            "dew": self._to_f(now_raw.get("dewPoint", {}).get("value")),
            # cloudCover: [0,1]
            "cloud": self._percent(pick(now_raw.get("cloudCover"), seg.get("cloudCover")), 0.0),
            # uvIndex: [0,15]
            "uv_index": pick(now_raw.get("uvIndex"), daily_first.get("uvIndexMax")),
            # --- 集成自有字段 (非 API 返回) ---
            # (V1 实况无观测时间戳 obsTime，已随属性重构剔除)
            "degraded": degraded,
        }
        return merged

    async def _async_update_data(self) -> dict[str, Any]:
        """主抓取任务：调用 api.py 进行多端点并发请求."""
        # 国际化语言适配
        ha_lang = self.hass.config.language # 例如 "zh-Hans" 或 "fr"
        qweather_lang = LANGUAGE_MAP.get(ha_lang, "en") # 匹配不到则默认英文        
        restricted_lang = "zh" if ha_lang.startswith("zh") else "en"
        now_ts = time.time()
        now_dt = dt_util.now()
        # 本轮刷新开始：全部缓存条目标记为"未在本轮更新"，成功写缓存时再置 True
        for meta in self._cache_meta.values():
            meta["fresh"] = False
        tasks = []
        task_map = []
        options = self.entry.options
        # 预处理坐标参数 (配置存储格式: "{lon},{lat}")
        try:
            lon, lat = [c.strip() for c in self.location.split(',')]
        except Exception:
            raise UpdateFailed(f"Invalid location format: {self.location}")

        # --- 各端点按 TTL 保护并发抓取（夜间自动×2，不人为限制请求）---
        # 实况天气（关键端点，始终拉取）
        tasks.append(self.api.get_weather_now(lat, lon, qweather_lang))
        task_map.append("now")

        # 逐日预报 (带 TTL 保护；V1 仅支持 1-10 天，旧配置可能残留 15/30，需钳制)
        if self._should_update("daily", TTL_DAILY):
            d_val = min(int(options.get(CONF_DAILYSTEPS, 7)), 10)
            tasks.append(self.api.get_forecast(lat, lon, d_val, qweather_lang))
            task_map.append("daily")

        # 逐小时预报 (带 TTL 保护)
        if self._should_update("hourly", TTL_HOURLY):
            h_val = int(options.get(CONF_HOURLYSTEPS, 24))
            tasks.append(self.api.get_hourly(lat, lon, h_val, qweather_lang))
            task_map.append("hourly")

        # 分钟降水
        if self._should_update("minutely", TTL_MINUTELY):
            tasks.append(self.api.get_minutely(lat, lon, restricted_lang))
            task_map.append("minutely")

        # 预警
        if self._should_update("warning", TTL_WARNING):
            tasks.append(self.api.get_warning_v1(lat, lon, qweather_lang))
            task_map.append("warning")

        # 专业空气质量
        if self._should_update("air", TTL_AIR):
            tasks.append(self.api.get_air_v1(lat, lon, qweather_lang))
            task_map.append("air")

        # 生活指数
        if self._should_update("indices", TTL_INDICES):
            tasks.append(self.api.get_indices(lat, lon, restricted_lang))
            task_map.append("indices")

        # ---并发执行与结果合并 ---
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            success_any = False

            for i, res in enumerate(results):
                category = task_map[i]
                if isinstance(res, dict) and res.get("code") in ("401", "403"):
                    # API 明确返回认证/权限错误：凭据失效，进入 reauth
                    raise ConfigEntryAuthFailed(
                        f"QWeather API 认证失败 ({res.get('code')}): "
                        f"{res.get('error_detail', 'unauthorized')}"
                    ) from None
                if isinstance(res, dict) and (res.get("code") == "200" or "metadata" in res):
                    self._cache_data[category] = res
                    self._last_update_times[category] = now_ts
                    self._cache_meta[category] = {"fetched_at": now_ts, "fresh": True}
                    success_any = True
                elif isinstance(res, Exception):
                    LOGGER.debug("和风天气：端点 %s 刷新异常: %s", category, res)

            if success_any:
                if self._consecutive_failures > 0:
                    LOGGER.info("和风天气：通信已恢复正常，回归标准刷新频率")
                self._consecutive_failures = 0
                self.update_interval = self._base_interval
                # 落盘缓存（含时间戳），供下次重启复用
                await self.async_save_cache()
            else:
                raise UpdateFailed("所有 API 抓取任务均失败")

        except ConfigEntryAuthFailed:
            # 认证失效：不进入退避逻辑，直接上抛以触发 reauth 流程
            raise
        except Exception as err:
            self._consecutive_failures += 1
            # 冷启动保护逻辑
            if self._cache_data.get("now") and self._consecutive_failures >= 2:
                self.update_interval = timedelta(hours=1)
                LOGGER.warning("和风天气：持续连接失败，进入退让模式（1小时/次）")
            else:
                self.update_interval = timedelta(minutes=2)
                LOGGER.debug("和风天气：通信失败，将在 2 分钟后重试...")
            # 重新抛出异常：让 DataUpdateCoordinator 标记 last_update_success=False，
            # 实体进入 unavailable（官方 entity-unavailable 规则要求），
            # 同时 self.data 保留上次成功数据供实体降级显示。
            raise

        # ---数据解析 (组装返回字典) ---
        c = self._cache_data
        # 安全提取各列表变量 (确保变量在任何语言下都已定义)
        # V1 响应结构：实况顶层即数据；每日为 days 数组；逐小时为 hours 数组
        now_raw = c.get("now", {})
        daily_list = c.get("daily", {}).get("days", [])
        hourly_list = c.get("hourly", {}).get("hours", [])
        air_raw = c.get("air", {})
        warning_raw = c.get("warning", {}).get("alerts", [])
        indices_list = c.get("indices", {}).get("daily", [])
        minutely_raw = c.get("minutely", {})

        # 预警深度解析 (输出字段顺序与 warning-alert API 文档保持一致：
        # id → senderName → issuedTime → eventType → severity → color → headline → description → instruction)
        parsed_warnings = []
        for a in warning_raw:
            parsed_warnings.append({
                "id": a.get("id"),
                "sender": a.get("senderName"),
                "issued": a.get("issuedTime"),
                "type_code": a.get("eventType", {}).get("code"),
                "type_name": a.get("eventType", {}).get("name"),
                "level": a.get("severity"),
                "color": a.get("color", {}).get("code"),
                "title": a.get("headline"),
                "text": a.get("description"),
                "instruction": a.get("instruction"),
            })

        # 针对 V1 空气质量的深度解析逻辑
        parsed_air = {}
        if "indexes" in air_raw and air_raw["indexes"]:
            idx = air_raw["indexes"][0]  # 默认取首项（通常为本地标准）
            primary_info = idx.get("primaryPollutant") or {}
            health_info = idx.get("health") or {}
            advice_info = health_info.get("advice") or {}

            # 污染物：优先 indexes[0].pollutants，回退顶层 pollutants（兼容不同响应结构）
            pollutant_src = idx.get("pollutants") or air_raw.get("pollutants") or []
            parsed_air = {
                # 输出顺序与 air-current API indexes[] 一致：
                # code → name → aqi → aqiDisplay → category → level → color
                # → primaryPollutant → health → pollutants
                "code": idx.get("code"),
                "name": idx.get("name"),
                "aqi": idx.get("aqi"),
                "aqi_display": idx.get("aqiDisplay"),
                "category": idx.get("category"),
                "level": idx.get("level"),
                "color": idx.get("color"),
                "primary": primary_info.get("name"),
                "primary_code": primary_info.get("code"),
                "primary_fullname": primary_info.get("fullName"),
                "health_effect": health_info.get("effect"),
                "health_advice": advice_info.get("generalPopulation") if isinstance(advice_info, dict) else None,
                "health_advice_sensitive": advice_info.get("sensitivePopulation") if isinstance(advice_info, dict) else None,
            }

            # 污染物浓度 + 名称
            for p in pollutant_src:
                if not isinstance(p, dict):
                    continue
                code = (p.get("code") or "").replace(".", "p")
                if not code:
                    continue
                conc = p.get("concentration") or {}
                parsed_air[code] = conc.get("value") if isinstance(conc, dict) else None
                parsed_air[f"{code}_unit"] = conc.get("unit") if isinstance(conc, dict) else None
                parsed_air[f"{code}_name"] = p.get("name")
                parsed_air[f"{code}_fullname"] = p.get("fullName")

        merged_now = self._merge_now(
            now_raw, daily_list[0] if daily_list else None, now_dt)

        return {
            "now": merged_now,
            "daily": self._parse_daily(daily_list),
            "hourly": self._parse_hourly(hourly_list),
            "aqi": parsed_air,
            "warning": parsed_warnings,
            "indices": self._parse_indices(indices_list),
            "city": self.city_name,
            "minutely_summary": minutely_raw.get("summary", ""),
            "minutely_detail": minutely_raw.get("minutely", []),
            "attributions": self._collect_attributions(c),
            "weather_abstract": self._generate_smart_abstract(merged_now, daily_list, now_dt),
            # 缓存新鲜度报告：age_seconds = 距上次成功抓取的秒数；fresh = 本轮是否拿到新数据
            "cache_freshness": {
                cat: {
                    "age_seconds": int(now_ts - meta.get("fetched_at", now_ts)),
                    "fresh": meta.get("fresh", False),
                }
                for cat, meta in self._cache_meta.items()
            },
            "update_time": dt_util.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    def _generate_smart_abstract(self, now_merged: dict, daily: list, now_dt: datetime) -> dict[str, Any]:
        """生成智能天气摘要 (显示状态/温差/风力/AQI 等级)."""
        air_raw = self._cache_data.get("air", {})
        # 防御：indexes 可能为缺失或空数组 (V1 air 接口无监测站数据时返回 [])
        idx = (air_raw.get("indexes") or [{}])[0]
        
        if not daily or len(daily) < 2:
            return {"display_state": now_merged.get("text_cn", "Loading"), "status": "loading"}

        today = daily[0]
        tomorrow = daily[1]
        hour = now_dt.hour
        
        # ---时段感知 (Time Period) ---
        if 5 <= hour < 11:
            period = "morning"
        elif 11 <= hour < 17:
            period = "afternoon"
        elif 17 <= hour < 23:
            period = "evening"
        else:
            period = "night"

        # ---智能显示状态判定 (Display State Logic) ---
        # 5:00 - 17:00 (白天/下午)：状态显示【今日实况】(合并层值，已含 daily 兜底)
        # 17:00 - 05:00 (傍晚/深夜)：状态显示【明日白天预报】
        if 5 <= hour < 17:
            display_state = now_merged.get("text_cn", "Unknown")
        else:
            display_state = tomorrow.get("daytime", {}).get("condition", {}).get("text", "Unknown")

        # ---气温趋势监控 (基于今日与明日最高温对比) ---
        t_max_today = self._to_f(today.get("temperatureMax", {}).get("value"), 0.0)
        t_max_tomorrow = self._to_f(tomorrow.get("temperatureMax", {}).get("value"), 0.0)
        diff = t_max_tomorrow - t_max_today
        
        if diff >= 5:
            temp_type = "heat_surge"    # 气温剧升
        elif diff >= 2:
            temp_type = "warmer"        # 明显升温
        elif diff <= -5:
            temp_type = "cold_snap"     # 断崖式降温
        elif diff <= -2:
            temp_type = "colder"        # 明显降温
        else:
            temp_type = "steady"        # 气温平稳

        # --- 风力判定 (Wind Scale) ---
        # 3级以上视为"有风"
        # 注意：V1 wind.scale 是 number，但保留安全转换以兼容缺失场景
        wind_scale = int(self._to_f(now_merged.get("windScale"), 0))

        if wind_scale == 0:
            wind_status = "no_wind"
        elif wind_scale < 3:
            wind_status = "calm"
        else:
            wind_status = "windy"

        # --- 空气质量等级 (AQI Level) ---
        # 即使 category 是中文，我们也可以根据 aqi 数值输出逻辑 key
        aqi_val = self._to_f(idx.get("aqi"), 0.0)

        if aqi_val <= 50:
            aqi_level = "good"
        elif aqi_val <= 100:
            aqi_level = "moderate"
        elif aqi_val <= 150:
            aqi_level = "unhealthy"
        elif aqi_val <= 200:
            aqi_level = "very_unhealthy"
        else:
            aqi_level = "hazardous"

        # --- 组装逻辑包 (全部使用英文 Key) ---
        return {
            "period": period, 
            "tonight_text": display_state,
            "temp_change_type": temp_type,
            "current_temp": int(self._to_f(now_merged.get("temp"), 0)),
            "wind_status": wind_status, 
            "aqi_level": aqi_level, 
        }

    # --- 解析辅助方法 (逻辑下沉) ---
    def _parse_daily(self, data: list) -> list:
        """V1 每日预报解析 (days[] → 嵌套结构)."""
        result: list[dict] = []
        for d in data:
            astro = d.get("astro", {})
            result.append({
                # forecastStartTime (UTC RFC3339：V1 forecastStartTime 即查询地点本地
                # 当天 00:00 的 UTC 时刻，语义与 v7 fxDate 一致且跨时区更准确)
                "datetime": self._to_utc_iso(d.get("forecastStartTime")),
                # forecastEndTime
                "forecast_end": self._to_utc_iso(d.get("forecastEndTime")),
                # astro (时间统一转本地 HH:MM；顺序与文档 astro 对象一致)
                "astro": {
                    "sunrise": self._to_local_hm(astro.get("sunrise")),
                    "sunset": self._to_local_hm(astro.get("sunset")),
                    "astronomical_dawn": self._to_local_hm(astro.get("astronomicalDawn")),
                    "nautical_dawn": self._to_local_hm(astro.get("nauticalDawn")),
                    "civil_dawn": self._to_local_hm(astro.get("civilDawn")),
                    "astronomical_dusk": self._to_local_hm(astro.get("astronomicalDusk")),
                    "nautical_dusk": self._to_local_hm(astro.get("nauticalDusk")),
                    "civil_dusk": self._to_local_hm(astro.get("civilDusk")),
                    "solar_noon": self._to_local_hm(astro.get("solarNoon")),
                    "solar_midnight": self._to_local_hm(astro.get("solarMidnight")),
                    "moonrise": self._to_local_hm(astro.get("moonrise")),
                    "moonset": self._to_local_hm(astro.get("moonset")),
                    "moon_transit": self._to_local_hm(astro.get("moonTransit")),
                    "moon_underfoot": self._to_local_hm(astro.get("moonUnderfoot")),
                    # moonPhase (V1 英文枚举，前端经 i18n mp.* 翻译)
                    "moon_phase": astro.get("moonPhase"),
                    # (V1 无 moonPhaseIcon 字段，图标由前端按 moon_phase 推导)
                },
                # temperatureMax / temperatureMin / temperatureAvg
                "temp_max": self._to_f(d.get("temperatureMax", {}).get("value"), 0.0),
                "temp_min": self._to_f(d.get("temperatureMin", {}).get("value"), 0.0),
                "temp_avg": self._to_f(d.get("temperatureAvg", {}).get("value"), 0.0),
                # uvIndexMax
                "uv_index_max": d.get("uvIndexMax"),
                # daytime / nighttime (时段结构同构)
                "daytime": self._parse_daily_period(d.get("daytime", {})),
                "nighttime": self._parse_daily_period(d.get("nighttime", {})),
            })
        return result

    def _parse_daily_period(self, seg: dict) -> dict:
        """V1 每日预报 daytime/nighttime 时段解析."""
        cond = seg.get("condition", {})
        wind = seg.get("wind", {})
        precip = seg.get("precipitation", {})
        return {
            # forecastStartTime / forecastEndTime (时段真实边界，UTC ISO)
            "start": self._to_utc_iso(seg.get("forecastStartTime")),
            "end": self._to_utc_iso(seg.get("forecastEndTime")),
            # condition: {text, code, icon} (icon 为独立字段，夜间与 code 不同，如 102/152)
            "text": cond.get("text", "Unknown"),
            "condition": CONDITION_MAP.get(cond.get("code"), "exceptional"),
            "icon": cond.get("icon") or cond.get("code"),
            # temperatureMax / temperatureMin (时段级温度区间)
            "temp_max": self._to_f(seg.get("temperatureMax", {}).get("value"), 0.0),
            "temp_min": self._to_f(seg.get("temperatureMin", {}).get("value"), 0.0),
            # wind: direction{degree, compass} / speed{value, unit} / scale
            "wind_degree": self._to_f(wind.get("direction", {}).get("degree"), 0.0),
            "wind_compass": wind.get("direction", {}).get("compass"),
            "wind_speed": self._speed_kmh(wind.get("speed", {}).get("value"), 0.0),
            "wind_scale": wind.get("scale"),
            # windGustMax (m/s → km/h)
            "wind_gust_max": self._speed_kmh(seg.get("windGustMax", {}).get("value"), 0.0),
            # precipitation: amount / probability (0~1 → %) / type (rain/snow/none)
            "precip_amount": self._to_f(precip.get("amount", {}).get("value"), 0.0),
            "precip_probability": self._percent(precip.get("probability"), 0.0),
            "precip_type": precip.get("type"),
            # cloudCover / humidity (0~1 → %)
            "cloud": self._percent(seg.get("cloudCover"), 0.0),
            "humidity": self._percent(seg.get("humidity"), 0.0),
        }

    def _parse_hourly(self, data: list) -> list:
        """V1 逐小时预报解析 (hours[] → 完整字段，键名与 daily_period 约定一致)."""
        out = []
        for d in data:
            cond = d.get("condition", {})
            temp = d.get("temperature", {})
            feels = d.get("feelsLike", {})
            wind = d.get("wind", {})
            wdir = wind.get("direction", {})
            wspeed = wind.get("speed", {})
            wgust = wind.get("windGust", {})
            precip = d.get("precipitation", {})
            amount = precip.get("amount", {})
            intensity = precip.get("intensity", {})
            pressure = d.get("pressure", {})
            vis = d.get("visibility", {})
            dew = d.get("dewPoint", {})
            out.append({
                # forecastTime
                "datetime": self._to_utc_iso(d.get("forecastTime")),
                # condition: {text, code}
                "text": cond.get("text", "Unknown"),
                "condition": CONDITION_MAP.get(cond.get("code"), "exceptional"),
                "icon": cond.get("code"),
                # temperature: {value, unit}
                "native_temperature": self._to_f(temp.get("value"), 0.0),
                # feelsLike: {value, unit}
                "native_apparent_temperature": self._to_f(feels.get("value"), 0.0),
                # humidity (0~1 → %)
                "native_humidity": self._percent(d.get("humidity"), 0.0),
                # wind: direction{degree, compass} / speed{value, unit, scale} / windGust{value, unit}
                "native_wind_bearing": self._to_f(wdir.get("degree"), 0.0),
                "wind_compass": wdir.get("compass"),
                "native_wind_speed": self._speed_kmh(wspeed.get("value"), 0.0),
                "wind_scale": wspeed.get("scale"),
                "native_wind_gust_speed": self._speed_kmh(wgust.get("value"), 0.0),
                # precipitation: amount{value,unit} / intensity{value,unit} / type / probability(0~1→%)
                "native_precipitation": self._to_f(amount.get("value"), 0.0),
                "precipitation_intensity": self._to_f(intensity.get("value"), 0.0),
                "precipitation_type": precip.get("type"),
                "precipitation_probability": self._percent(precip.get("probability"), 0.0),
                # pressure: {value, unit}
                "native_pressure": self._to_f(pressure.get("value"), 0.0),
                # visibility: {value, unit} (m → km)
                "native_visibility": self._vis_km(vis.get("value"), 0.0),
                # dewPoint: {value, unit}
                "native_dew_point": self._to_f(dew.get("value"), 0.0),
                # cloudCover (0~1 → %) / uvIndex
                "native_cloud_coverage": self._percent(d.get("cloudCover"), 0.0),
                "uv_index": d.get("uvIndex"),
            })
        return out

    def _parse_indices(self, data: list) -> list:
        """生活指数解析 (v7 indices: date / type / name / level / category / text)."""
        return [{
            "date": d.get("date"),
            "type": SUGGESTION_TYPE_MAP.get(d.get("type"), "unknown"),
            "title": d.get("name"),
            "title_cn": d.get("name"),
            "brf": d.get("category"),
            "level": d.get("level"),
            "txt": d.get("text"),
        } for d in data]
    
    @property
    def device_info(self) -> DeviceInfo:
        """设备信息."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.entry.entry_id)},
            name=f"QWeather Pro {self.entry.title}",
            manufacturer="QWeather Pro",
            model="Advanced Weather Engine",
            sw_version=str(self.version),
            configuration_url="https://console.qweather.com",
            entry_type=DeviceEntryType.SERVICE,
        )