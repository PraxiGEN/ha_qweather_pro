"""QWeather (和风天气) 数据协调器."""
from __future__ import annotations

import asyncio
import logging
import time
import math
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
import homeassistant.util.dt as dt_util

from cryptography.hazmat.primitives import serialization
import jwt

from .const import (
    DOMAIN, CONF_API_KEY, CONF_LOCATION_ID, CONF_USE_TOKEN,
    CONF_PROJECT_ID, CONF_KEY_ID, CONF_PRIVATE_KEY, CONF_UPDATE_INTERVAL,
    SUGGESTION_TYPE_MAP, CONF_DAILYSTEPS, CONF_HOURLYSTEPS, 
    CONF_ALERT, CONF_GIRD, CONF_LIFEINDEX,
)
from .condition import CONDITION_MAP

_LOGGER = logging.getLogger(__name__)

# 缓存有效期 (秒)
TTL_DAILY = 3600     # 1小时
TTL_HOURLY = 1800    # 30分钟
TTL_INDICES = 10800  # 3小时
TTL_AIR = 1800       # 30分钟
TTL_MINUTELY = 600   # 10分钟

class QWeatherUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """QWeather 数据异步调度中心."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, version: str) -> None:
        """初始化."""
        self.entry = entry
        self.version = version
        self.location = entry.data.get(CONF_LOCATION_ID)
        self.city_name: str | None = None
        
        update_interval = self.entry.options.get(CONF_UPDATE_INTERVAL, 15)
        super().__init__(
            hass, _LOGGER, name=DOMAIN,
            update_interval=timedelta(minutes=update_interval),
        )
        
        self.session = async_get_clientsession(hass)
        
        # 初始化全量本地缓存，确保冷启动不报错
        self._cache_data: dict[str, Any] = {
            "now": {}, "daily": {}, "hourly": {}, "air": {}, 
            "indices": {}, "warning": {}, "minutely": {}
        }
        self._last_update_times: dict[str, float] = {}

    def _should_update(self, category: str, ttl: int) -> bool:
        """检查 TTL 是否过期."""
        last_time = self._last_update_times.get(category, 0)
        return (time.time() - last_time) > ttl

    def _to_f(self, val: Any, default: float | None = None) -> float | None:
        """数值安全转换器."""
        try:
            return float(val)
        except (TypeError, ValueError):
            return default

    async def _async_update_data(self) -> dict[str, Any]:
        """主抓取任务：多端点并发请求 + 智能 TTL 缓存."""
        now_ts = time.time()
        tasks = []
        task_map = []

        # 获取配置参数并强制符合 API 限制
        options = self.entry.options
        d_val = int(options.get(CONF_DAILYSTEPS, 7))
        daily_steps = d_val if d_val in [3, 7, 10, 15] else 7
        
        h_val = int(options.get(CONF_HOURLYSTEPS, 24))
        hourly_steps = h_val if h_val in [24, 72, 168] else 24

        show_alert = options.get(CONF_ALERT, True)
        show_life = options.get(CONF_LIFEINDEX, True)
        use_grid = options.get(CONF_GIRD, False)
        api_type = "grid-weather" if use_grid else "weather"

        # 构建异步任务队列
        tasks.append(self._async_fetch_data(f"{api_type}/now"))
        task_map.append("now")

        if self._should_update("daily", TTL_DAILY):
            tasks.append(self._async_fetch_data(f"{api_type}/{daily_steps}d"))
            task_map.append("daily")

        if self._should_update("hourly", TTL_HOURLY):
            tasks.append(self._async_fetch_data(f"{api_type}/{hourly_steps}h"))
            task_map.append("hourly")

        if not use_grid and self._should_update("air", TTL_AIR):
            tasks.append(self._async_fetch_data("air/now"))
            task_map.append("air")

        if show_life and self._should_update("indices", TTL_INDICES):
            tasks.append(self._async_fetch_data("indices/1d", {"type": "0"}))
            task_map.append("indices")

        if show_alert:
            tasks.append(self._async_fetch_data("warning/now"))
            task_map.append("warning")

        if self._should_update("minutely", TTL_MINUTELY):
            tasks.append(self._async_fetch_data("minutely/5m"))
            task_map.append("minutely")

        if not self.city_name:
            tasks.append(self._async_fetch_city_name_internal())
            task_map.append("city")

        # ... 并发执行请求 ...
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, res in enumerate(results):
            category = task_map[i]
            
            # 核心改进：严谨的判断逻辑
            if isinstance(res, dict) and res.get("code") == "200":
                self._cache_data[category] = res
                self._last_update_times[category] = now_ts
            else:
                # 如果请求失败（如 403 频率超限），记录日志但不要清空旧的缓存
                error_code = res.get("code") if isinstance(res, dict) else "Timeout/Error"
                _LOGGER.warning("和风天气：抓取 %s 失败 (代码: %s)。尝试保持旧数据。", category, error_code)

        # 数据解析与合成
        c = self._cache_data
        raw_now = c.get("now", {}).get("now", {})
        daily_list = c.get("daily", {}).get("daily", [])
        hourly_list = c.get("hourly", {}).get("hourly", [])
        air_now = c.get("air", {}).get("now", {})
        warning_list = c.get("warning", {}).get("warning", [])
        indices_list = c.get("indices", {}).get("daily", [])
        minutely_raw = c.get("minutely", {})

        # 摘要合成
        hourly_summary = "暂无小时级天气概况"
        if hourly_list:
            unique_texts = []
            for h in hourly_list[:6]:
                txt = h.get("text")
                if txt and txt not in unique_texts: unique_texts.append(txt)
            hourly_summary = f"未来6小时：{'转'.join(unique_texts)}"

        return {
            "now": {
                "temp": self._to_f(raw_now.get("temp")),
                "text_cn": raw_now.get("text", "未知"),
                "condition": CONDITION_MAP.get(raw_now.get("icon"), "exceptional"),
                "humidity": self._to_f(raw_now.get("humidity")),
                "pressure": self._to_f(raw_now.get("pressure")),
                "windSpeed": self._to_f(raw_now.get("windSpeed")),
                "wind360": self._to_f(raw_now.get("wind360")),
                "windDir": raw_now.get("windDir", "未知"),
                "windScale": raw_now.get("windScale"),
                "feelsLike": self._to_f(raw_now.get("feelsLike")),
                "icon": raw_now.get("icon"),
                "obsTime": raw_now.get("obsTime"),
                "vis": self._to_f(raw_now.get("vis"), 0.0),
                "precip": self._to_f(raw_now.get("precip"), 0.0),
                "cloud": self._to_f(raw_now.get("cloud"), 0.0),
                "dew": self._to_f(raw_now.get("dew")),
            },
            "daily": self._parse_daily(daily_list),
            "hourly": self._parse_hourly(hourly_list),
            "aqi": air_now,
            "warning": warning_list,
            "indices": self._parse_indices(indices_list),
            "city": self.city_name or "未知地点",
            "minutely_summary": minutely_raw.get("summary", "暂无降水预报"),
            "hourly_summary": hourly_summary,
            "update_time": dt_util.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    def _parse_daily(self, data: list) -> list:
        return [{
            "datetime": f"{d.get('fxDate')}T00:00:00",
            "native_temperature": self._to_f(d.get("tempMax"), 0.0),
            "native_templow": self._to_f(d.get("tempMin"), 0.0),
            "condition": CONDITION_MAP.get(d.get("iconDay"), "exceptional"),
            "icon": d.get("iconDay"),
            "text": d.get("textDay", "未知"),
            "native_precipitation": self._to_f(d.get("precip"), 0.0),
            "native_wind_speed": self._to_f(d.get("windSpeedDay"), 0.0),
            "humidity": self._to_f(d.get("humidity"), 0.0),
        } for d in data]

    def _parse_hourly(self, data: list) -> list:
        return [{
            "datetime": d.get("fxTime"),
            "native_temperature": self._to_f(d.get("temp"), 0.0),
            "condition": CONDITION_MAP.get(d.get("icon"), "exceptional"),
            "icon": d.get("icon"),
            "text": d.get("text", "未知"),
        } for d in data]

    def _parse_indices(self, data: list) -> list:
        return [{
            "type": SUGGESTION_TYPE_MAP.get(d.get("type"), "unknown"),
            "title": d.get("name"),
            "title_cn": d.get("name"),
            "brf": d.get("category"),
            "txt": d.get("text"),
        } for d in data]

    async def _async_fetch_data(self, endpoint: str, params: dict | None = None) -> dict:
        url_params = {"location": self.location, "lang": "zh"}
        if params: url_params.update(params)

        headers = {}
        if self.entry.data.get(CONF_USE_TOKEN):
            token = self._generate_jwt()
            if token: headers["Authorization"] = f"Bearer {token}"
        else:
            url_params["key"] = self.entry.data.get(CONF_API_KEY)

        host = self.entry.data.get("host", "devapi.qweather.com")
        url = f"https://{host}/v7/{endpoint}"

        try:
            async with asyncio.timeout(15):
                resp = await self.session.get(url, params=url_params, headers=headers)
                return await resp.json()
        except Exception as err:
            _LOGGER.debug("和风天气：请求 %s 异常: %s", endpoint, err)
            return {}

    async def _async_fetch_city_name_internal(self) -> str | None:
        url = "https://geoapi.qweather.com/v2/city/lookup"
        params = {"location": self.location}
        headers = {}
        if self.entry.data.get(CONF_USE_TOKEN):
            token = self._generate_jwt()
            if token: headers["Authorization"] = f"Bearer {token}"
        else:
            params["key"] = self.entry.data.get(CONF_API_KEY)

        try:
            async with self.session.get(url, params=params, headers=headers) as resp:
                data = await resp.json()
                if data.get("code") == "200":
                    return data["location"][0]["name"]
        except:
            pass
        return None

    def _generate_jwt(self) -> str | None:
        try:
            key_content = self.entry.data.get(CONF_PRIVATE_KEY)
            if not key_content: return None
            private_key_obj = serialization.load_pem_private_key(key_content.encode('utf-8'), password=None)
            now_ts = int(time.time())
            payload = {'iat': now_ts - 30, 'exp': now_ts + 900, 'sub': self.entry.data.get(CONF_PROJECT_ID)}
            return jwt.encode(payload, private_key_obj, algorithm='EdDSA', headers={'kid': self.entry.data.get(CONF_KEY_ID)})
        except:
            return None