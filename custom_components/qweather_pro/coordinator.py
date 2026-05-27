"""QWeather (和风天气) 数据协调器."""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta
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
    CONF_ALERT, CONF_GIRD, CONF_LIFEINDEX, LOGGER
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

        update_min = entry.options.get(CONF_UPDATE_INTERVAL, 15)
        self._base_interval = timedelta(minutes=update_min)

        # 1. 初始化 API 客户端
        self.api = QWeatherAPI(
            session=async_get_clientsession(hass), 
            api_key=entry.data.get(CONF_API_KEY),
            use_token=entry.data.get(CONF_USE_TOKEN),
            project_id=entry.data.get(CONF_PROJECT_ID),
            key_id=entry.data.get(CONF_KEY_ID),
            private_key=entry.data.get(CONF_PRIVATE_KEY),
            host=entry.data.get("host", "api.qweather.com")
        )

        super().__init__(
            hass, LOGGER, name=DOMAIN,
            update_interval=self._base_interval,
        )
        
        # 2. 初始化本地持久化缓存
        self._cache_data: dict[str, Any] = {
            "now": {}, "daily": {}, "hourly": {}, "air": {}, 
            "indices": {}, "warning": {}, "minutely": {}
        }
        self._last_update_times: dict[str, float] = {}

    def _should_update(self, category: str, ttl: int) -> bool:
        """
        检查特定类别的数据是否需要更新。
        包含深夜（00:00 - 05:00）自动降频逻辑，以节省 API 额度。
        """
        now_ts = time.time()
        now_dt = dt_util.now()
        
        # 1. 定义深夜降频时段：凌晨 0 点整 到 5 点之前（04:59:59）
        # 5 点一到，此判断为 False，立即恢复正常 TTL
        is_night = 0 <= now_dt.hour < 5
        
        # 2. 计算实际生效的 TTL (有效期)
        # 如果是深夜，将传入的 TTL 延长 2 倍
        # 例如：分钟降水 15分钟 -> 30分钟；每日预报 2小时 -> 4小时
        actual_ttl = ttl * 2 if is_night else ttl
        
        # 3. 获取该类别数据上一次成功更新的时间戳
        last_time = self._last_update_times.get(category, 0)
        
        # 4. 核心判定：当前时间与上次更新时间的差值是否超过了实际 TTL
        result = (now_ts - last_time) > actual_ttl

        # 调试日志：可以帮助您在日志中观察降频是否生效
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
        now_ts = time.time()
        tasks = []
        task_map = []

        options = self.entry.options

        use_grid = options.get(CONF_GIRD, False)
        api_type = "grid-weather" if use_grid else "weather"

        # --- A. 构建并发请求队列 ---
        
        # 1. 实况 (始终抓取)
        tasks.append(self.api.get_weather_now(self.location, api_type))
        task_map.append("now")

        # 2. 逐日预报 (带 TTL 保护)
        if self._should_update("daily", TTL_DAILY):
            d_val = int(options.get(CONF_DAILYSTEPS, 7))
            tasks.append(self.api.get_forecast(self.location, f"{d_val}d", api_type))
            task_map.append("daily")

        # 3. 逐小时预报 (带 TTL 保护)
        if self._should_update("hourly", TTL_HOURLY):
            h_val = int(options.get(CONF_HOURLYSTEPS, 24))
            tasks.append(self.api.get_hourly(self.location, f"{h_val}h", api_type))
            task_map.append("hourly")

        # 4. 分钟降水
        if self._should_update("minutely", TTL_MINUTELY):
            tasks.append(self.api.get_minutely(self.location))
            task_map.append("minutely")

        # 5. 预警
        if options.get(CONF_ALERT, True):
            tasks.append(self.api.get_warning_v1(self.location))
            task_map.append("warning")

        # 6. 空气质量与生活指数 （V1接口）
        if not use_grid and self._should_update("air", TTL_AIR):
            tasks.append(self.api.get_air_v1(self.location))
            task_map.append("air")

        if options.get(CONF_LIFEINDEX, True) and self._should_update("indices", TTL_INDICES):
            tasks.append(self.api.get_indices(self.location))
            task_map.append("indices")

        # --- B. 并发执行与结果合并 ---
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
                    LOGGER.debug("和风天气：端点 %s 刷新跳过或失败: %s", category, res)

            if success_any:
                if self._consecutive_failures > 0:
                    LOGGER.info("和风天气：通信已恢复正常，回归标准刷新频率")
                self._consecutive_failures = 0
                self.update_interval = self._base_interval
            else:
                raise UpdateFailed("所有 API 抓取任务均失败")

        except Exception as err:
            self._consecutive_failures += 1
            # 连续失败 2 次以上进入 1 小时退让期
            if self._consecutive_failures >= 2:
                self.update_interval = timedelta(hours=1)
                LOGGER.warning("和风天气：持续连接失败，进入退让模式（1小时/次），错误: %s", err)

        # --- C. 数据解析 (组装返回字典) ---
        c = self._cache_data
        
        # 1. 预警深度解析
        alert_raw = c.get("warning", {}).get("alerts", [])
        parsed_warnings = []
        for a in alert_raw:
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

        # 2. 小时级摘要合成
        hourly_list = c.get("hourly", {}).get("hourly", [])
        hourly_summary = "近期天气平稳"
        if hourly_list:
            unique_texts = []
            for h in hourly_list[:6]:
                txt = h.get("text")
                if txt and txt not in unique_texts: unique_texts.append(txt)
            hourly_summary = f"未来6小时：{'转'.join(unique_texts)}"

        now_raw = c.get("now", {}).get("now", {})
        minutely_raw = c.get("minutely", {})

        # --- 针对 V1 空气质量的深度解析逻辑 ---
        air_raw = c.get("air", {})
        parsed_air = {}
        if "indexes" in air_raw and air_raw["indexes"]:
            idx = air_raw["indexes"][0] # 默认取第一项（通常是本地标准）
            
            # 安全获取首要污染物
            primary_info = idx.get("primaryPollutant")
            primary_name = primary_info.get("name") if isinstance(primary_info, dict) else "无"
            
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

        return {
            "now": {
                "temp": self._to_f(now_raw.get("temp")),
                "text_cn": now_raw.get("text", "未知"),
                "condition": CONDITION_MAP.get(now_raw.get("icon"), "exceptional"),
                "humidity": self._to_f(now_raw.get("humidity")),
                "pressure": self._to_f(now_raw.get("pressure")),
                "windSpeed": self._to_f(now_raw.get("windSpeed")),
                "wind360": self._to_f(now_raw.get("wind360")),
                "windDir": now_raw.get("windDir", "未知"),
                "windScale": now_raw.get("windScale"),
                "feelsLike": self._to_f(now_raw.get("feelsLike")),
                "icon": now_raw.get("icon"),
                "obsTime": now_raw.get("obsTime"),
                "vis": self._to_f(now_raw.get("vis"), 0.0),
                "precip": self._to_f(now_raw.get("precip"), 0.0),
                "cloud": self._to_f(now_raw.get("cloud"), 0.0),
                "dew": self._to_f(now_raw.get("dew")),
            },
            "daily": self._parse_daily(c.get("daily", {}).get("daily", [])),
            "hourly": self._parse_hourly(hourly_list),
            "aqi": parsed_air,
            "warning": parsed_warnings,
            "indices": self._parse_indices(c.get("indices", {}).get("daily", [])),
            "city": self.city_name,
            "minutely_summary": minutely_raw.get("summary", "未来两小时无降水"),
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
            "text": d.get("textDay", "未知"),
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
            "text": d.get("text", "未知"),
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
        """定义此条目对应的设备信息."""
        return DeviceInfo(

            identifiers={(DOMAIN, self.entry.entry_id)},
            name=f"QWeather Pro {self.entry.title}",
            # translation_key="qweather_pro",
            manufacturer="QWeather Pro",
            model="Advanced Weather Engine",
            sw_version=str(self.version),
            configuration_url="https://console.qweather.com",
            entry_type=DeviceEntryType.SERVICE,
        )