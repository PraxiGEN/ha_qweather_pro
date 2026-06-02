"""QWeather (和风天气) 数据协调器."""
from __future__ import annotations

import asyncio
import time
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.util.dt as dt_util

from .api import QWeatherAPI
from .const import (
    DOMAIN, CONF_API_KEY, CONF_LOCATION_ID, CONF_USE_TOKEN,
    CONF_PROJECT_ID, CONF_KEY_ID, CONF_PRIVATE_KEY, CONF_UPDATE_INTERVAL,
    SUGGESTION_TYPE_MAP, CONF_DAILYSTEPS, CONF_HOURLYSTEPS, 
    CONF_GIRD, DEFAULT_UPDATE_INTERVAL, LANGUAGE_MAP, LOGGER
)
from .condition import CONDITION_MAP

# --- 数据缓存有效期控制 (单位: 秒) ---
# 每日预报：7200秒 (2小时)
# 理由：每日预报的宏观气象模型更新缓慢，2小时刷新一次完全足够。
TTL_DAILY = 7200

# 逐小时预报：3600秒 (1小时)
# 理由：逐小时预报通常也是基于几小时更新一次的模型，15-30分钟刷新并不会带来新数据。
TTL_HOURLY = 3600

# 空气质量：3600秒 (1小时)
# 理由：环保部门的空气监测站通常是整点发布数据，每小时抓取一次最科学。
TTL_AIR = 3600

# 生活指数：10800秒 (3小时)
# 理由：建议类数据（洗车、穿衣等）全天更新频率极低，3小时更新一次即可。
TTL_INDICES = 10800

# 分钟级降水：900秒 (15分钟)
# 理由：这是最消耗额度的接口。将其从5分钟改为15分钟，可节省 66% 的请求量。
TTL_MINUTELY = 900

class QWeatherUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """QWeather 数据异步调度中心."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, version: str) -> None:
        """初始化协调器."""
        self.entry = entry
        self.version = version
        self.location = entry.data.get(CONF_LOCATION_ID)
        self.city_name = entry.title
        self._consecutive_failures = 0 # 追踪连续失败次数

        update_min = entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        self._base_interval = timedelta(minutes=update_min)

        # 初始化 API 客户端
        self.api = QWeatherAPI(
            session=async_get_clientsession(hass), 
            api_key=entry.data.get(CONF_API_KEY),
            use_token=entry.data.get(CONF_USE_TOKEN),
            project_id=entry.data.get(CONF_PROJECT_ID),
            key_id=entry.data.get(CONF_KEY_ID),
            private_key=entry.data.get(CONF_PRIVATE_KEY),
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

    def _to_f(self, val: Any, default: float | None = None) -> float | None:
        """数值安全转换工具."""
        try:
            return float(val)
        except (TypeError, ValueError):
            return default

    async def _async_update_data(self) -> dict[str, Any]:
        """主抓取任务：调用 api.py 进行多端点并发请求."""

        # 国际化语言适配
        ha_lang = self.hass.config.language # 例如 "zh-Hans" 或 "fr"
        qweather_lang = LANGUAGE_MAP.get(ha_lang, "en") # 匹配不到则默认英文        
        restricted_lang = "zh" if ha_lang.startswith("zh") else "en"
        is_zh = ha_lang.startswith("zh")
        is_en = ha_lang.startswith("en")

        now_ts = time.time()
        tasks = []
        task_map = []

        options = self.entry.options
        use_grid = options.get(CONF_GIRD, False)
        api_type = "grid-weather" if options.get(CONF_GIRD, False) else "weather"

        # 预处理坐标参数
        try:
            lon, lat = [c.strip() for c in self.location.split(',')]
        except Exception:
            raise UpdateFailed(f"Invalid location format: {self.location}")

        # ---构建并发请求队列 ---
        
        # 实况天气 (根据开关选择格点或标准)
        if use_grid:
            tasks.append(self.api.get_grid_weather_now(lat, lon, qweather_lang))
        else:
            tasks.append(self.api.get_weather_now(lat, lon, qweather_lang))
        task_map.append("now")

        # 逐日预报 (带 TTL 保护)
        if self._should_update("daily", TTL_DAILY):
            d_val = int(options.get(CONF_DAILYSTEPS, 7))
            if use_grid:
                tasks.append(self.api.get_grid_forecast(lat, lon, f"{d_val}d", qweather_lang))
            else:
                tasks.append(self.api.get_forecast(lat, lon, f"{d_val}d", qweather_lang))
            task_map.append("daily")

        # 逐小时预报 (带 TTL 保护)
        if self._should_update("hourly", TTL_HOURLY):
            h_val = int(options.get(CONF_HOURLYSTEPS, 24))
            if use_grid:
                tasks.append(self.api.get_grid_hourly(lat, lon, f"{h_val}h", qweather_lang))
            else:
                tasks.append(self.api.get_hourly(lat, lon, f"{h_val}h", qweather_lang))
            task_map.append("hourly")

        # 分钟降水
        if self._should_update("minutely", TTL_MINUTELY):
            tasks.append(self.api.get_minutely(lat, lon, restricted_lang))
            task_map.append("minutely")

        # 预警
        tasks.append(self.api.get_warning_v1(lat, lon, qweather_lang))
        task_map.append("warning")

        # 专业空气质量 (格点模式下通常由实况提供基础AQI，此处强制调用V1专业接口)
        if not use_grid and self._should_update("air", TTL_AIR):
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
                if isinstance(res, dict) and (res.get("code") == "200" or "metadata" in res):
                    self._cache_data[category] = res
                    self._last_update_times[category] = now_ts
                    success_any = True
                elif isinstance(res, Exception):
                    LOGGER.debug("和风天气：端点 %s 刷新异常: %s", category, res)

            if success_any:
                if self._consecutive_failures > 0:
                    LOGGER.info("和风天气：通信已恢复正常，回归标准刷新频率")
                self._consecutive_failures = 0
                self.update_interval = self._base_interval
            else:
                raise UpdateFailed("所有 API 抓取任务均失败")

        except Exception as err:
            self._consecutive_failures += 1
            # 冷启动保护逻辑
            if self._cache_data.get("now") and self._consecutive_failures >= 2:
                self.update_interval = timedelta(hours=1)
                LOGGER.warning("和风天气：持续连接失败，进入退让模式（1小时/次）")
            else:
                self.update_interval = timedelta(minutes=2)
                LOGGER.debug("和风天气：通信失败，将在 2 分钟后重试...")

        # ---数据解析 (组装返回字典) ---
        c = self._cache_data
        
        # 安全提取各列表变量 (确保变量在任何语言下都已定义)
        now_raw = c.get("now", {}).get("now", {})
        daily_list = c.get("daily", {}).get("daily", [])
        hourly_list = c.get("hourly", {}).get("hourly", [])
        air_raw = c.get("air", {})
        warning_raw = c.get("warning", {}).get("alerts", [])
        indices_list = c.get("indices", {}).get("daily", [])
        minutely_raw = c.get("minutely", {})

        # 预警深度解析
        parsed_warnings = []
        for a in warning_raw:
            parsed_warnings.append({
                "id": a.get("id"),
                "sender": a.get("senderName"),
                "issued": a.get("issuedTime"),
                "title": a.get("headline"),
                "text": a.get("description"),
                "instruction": a.get("instruction"),
                "level": a.get("severity"),
                "color": a.get("color", {}).get("code"),
                "type_name": a.get("eventType", {}).get("name"),
            })

        # 小时级摘要合成
        if is_zh:
            hourly_summary = "近期天气平稳"
            prefix = "未来6小时："
            separator = "转"
        else:
            # 默认为英文，即使是法语等也会准备英文摘要，但 sensor 层会拦截不显示
            hourly_summary = "The weather will remain stable"
            prefix = "Next 6 hours: "
            separator = " to "

        # ---只有中英文才执行耗时的字符串合成 ---
        if (is_zh or is_en) and hourly_list:
            unique_texts = []
            # 只取未来 6 小时的数据
            for h in hourly_list[:6]:
                txt = h.get("text")
                if txt and txt not in unique_texts:
                    unique_texts.append(txt)
            
            if unique_texts:
                hourly_summary = f"{prefix}{separator.join(unique_texts)}"
        elif not (is_zh or is_en):
            # 非中英语言，不生成摘要
            hourly_summary = None

        # 针对 V1 空气质量的深度解析逻辑
        parsed_air = {}
        if "indexes" in air_raw and air_raw["indexes"]:
            idx = air_raw["indexes"][0] # 默认取第一项（通常是本地标准）
            
            # 安全获取首要污染物
            primary_info = idx.get("primaryPollutant")
            primary_name = primary_info.get("name") if isinstance(primary_info, dict) else None
            
            # 安全获取健康建议
            health_info = idx.get("health")
            health_effect = health_info.get("effect") if isinstance(health_info, dict) else None
            health_advice = None
            if isinstance(health_info, dict):
                advice_info = health_info.get("advice")
                if isinstance(advice_info, dict):
                    health_advice = advice_info.get("generalPopulation")

            parsed_air = {
                "aqi": idx.get("aqi"),
                "category": idx.get("category"),
                "level": idx.get("level"),
                "primary": primary_name,
                "health_effect": health_effect,
                "health_advice": health_advice,
            }
            
            # 污染物浓度
            for p in air_raw.get("pollutants", []):
                code = p.get("code", "").replace(".", "p")
                conc = p.get("concentration", {})
                if code and isinstance(conc, dict):
                    parsed_air[code] = conc.get("value")
                    parsed_air[f"{code}_unit"] = conc.get("unit")

        # 组装最终返回结构 (确保 0 丢失)
        return {
            "now": {
                "temp": self._to_f(now_raw.get("temp")),
                "text_cn": now_raw.get("text", "Unknown"),
                "condition": CONDITION_MAP.get(now_raw.get("icon"), "exceptional"),
                "humidity": self._to_f(now_raw.get("humidity")),
                "pressure": self._to_f(now_raw.get("pressure")),
                "windSpeed": self._to_f(now_raw.get("windSpeed")),
                "wind360": self._to_f(now_raw.get("wind360")),
                "windDir": now_raw.get("windDir", "Unknown"),
                "windScale": now_raw.get("windScale"),
                "feelsLike": self._to_f(now_raw.get("feelsLike")),
                "icon": now_raw.get("icon"),
                "obsTime": now_raw.get("obsTime"),
                "vis": self._to_f(now_raw.get("vis"), 0.0),
                "precip": self._to_f(now_raw.get("precip"), 0.0),
                "cloud": self._to_f(now_raw.get("cloud"), 0.0),
                "dew": self._to_f(now_raw.get("dew")),
            },
            "daily": self._parse_daily(daily_list),
            "hourly": self._parse_hourly(hourly_list),
            "aqi": parsed_air,
            "warning": parsed_warnings,
            "indices": self._parse_indices(indices_list),
            "city": self.city_name,
            "minutely_summary": minutely_raw.get("summary", "No precipitation in the next two hours"),
            "minutely_detail": minutely_raw.get("minutely", []),
            "hourly_summary": hourly_summary,
            "update_time": dt_util.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    # --- 解析辅助方法 (逻辑下沉) ---

    def _parse_daily(self, data: list) -> list:
        return [{
            "datetime": f"{d.get('fxDate')}T00:00:00",
            "native_temperature": self._to_f(d.get("tempMax"), 0.0),
            "native_templow": self._to_f(d.get("tempMin"), 0.0),
            "condition": CONDITION_MAP.get(d.get("iconDay"), "exceptional"),
            "condition_night": CONDITION_MAP.get(d.get("iconNight"), "exceptional"),
            "icon": d.get("iconDay"),
            "text": d.get("textDay", "Unknown"),
            "native_precipitation": self._to_f(d.get("precip"), 0.0),
            "native_wind_speed": self._to_f(d.get("windSpeedDay"), 0.0),
            "humidity": self._to_f(d.get("humidity"), 0.0),
            "uv_index": d.get("uvIndex"),
            "moon_phase": d.get("moonPhase"),
            "moon_phase_icon": d.get("moonPhaseIcon"),
            "sunrise": d.get("sunrise"),
            "sunset": d.get("sunset"),
            "moonrise": d.get("moonrise"),
            "moonset": d.get("moonset"),
        } for d in data]

    def _parse_hourly(self, data: list) -> list:
        return [{
            "datetime": d.get("fxTime"),
            "native_temperature": self._to_f(d.get("temp"), 0.0),
            "condition": CONDITION_MAP.get(d.get("icon"), "exceptional"),
            "icon": d.get("icon"),
            "text": d.get("text", "Unknown"),
            "precipitation_probability": self._to_f(d.get("pop"), 0.0),
        } for d in data]

    def _parse_indices(self, data: list) -> list:
        return [{
            "type": SUGGESTION_TYPE_MAP.get(d.get("type"), "unknown"),
            "title": d.get("name"),
            "title_cn": d.get("name"),
            "brf": d.get("category"),
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