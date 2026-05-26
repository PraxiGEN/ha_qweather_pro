"""QWeather (和风天气) 集成常量定义."""
from __future__ import annotations

import logging
from typing import Final
from homeassistant.const import (
    Platform,
    CONF_API_KEY,
)

# --- 基础信息 ---
DOMAIN: Final = "qweather_pro"
LOGGER = logging.getLogger(__package__)
MANUFACTURER: Final = "QWeather Pro"
ATTRIBUTION: Final = "Data provided by QWeather Pro"

# --- 支持的平台 ---
PLATFORMS: Final = [
    Platform.WEATHER,
    Platform.SENSOR,
]

# --- 配置键名 (Config & Options) ---
CONF_API_KEY: Final = CONF_API_KEY
CONF_LOCATION_ID: Final = "location_id"
CONF_LOCATION_NAME: Final = "location_name"
CONF_USE_TOKEN: Final = "use_token"
CONF_PROJECT_ID: Final = "project_id"
CONF_KEY_ID: Final = "key_id"
CONF_PRIVATE_KEY: Final = "private_key"

CONF_UPDATE_INTERVAL: Final = "update_interval"
CONF_HOURLYSTEPS: Final = "hourlysteps"
CONF_DAILYSTEPS: Final = "dailysteps"
CONF_LIFEINDEX: Final = "lifeindex"
CONF_ALERT: Final = "alert"
CONF_GIRD: Final = "gird"
CONF_CUSTOM_UI: Final = "custom_ui"

# --- 属性扩展键名 ---
ATTR_UPDATE_TIME: Final = "update_time"
ATTR_AQI: Final = "aqi"
ATTR_SUGGESTION: Final = "suggestion"

# --- 默认值 ---
DEFAULT_NAME: Final = "和风天气Pro"
DEFAULT_HOST: Final = "api.qweather.com"
DEFAULT_UPDATE_INTERVAL: Final = 15

# --- 生活指数类型映射 (QWeather API v7) ---
SUGGESTION_TYPE_MAP: Final[dict[str, str]] = {
    "1": "sport",    "2": "cw",       "3": "drsg",     "4": "fishing",
    "5": "uv",       "6": "trav",     "7": "ag",       "8": "comf",
    "9": "flu",      "10": "air",     "11": "ac",      "12": "gls",
    "13": "mu",      "14": "dc",      "15": "ptfc",    "16": "fsh",
}

# --- 天气状况图标映射 (QWeather Icon -> HA Weather State) ---
# 这是 Weather 实体正常显示 condition 的核心
CONDITION_MAP: Final[dict[str, str]] = {
    "100": "sunny",          # 晴
    "101": "cloudy",         # 多云
    "102": "cloudy",         # 少云
    "103": "cloudy",         # 晴间多云
    "104": "cloudy",         # 阴
    "150": "clear-night",    # 晴(夜)
    "151": "cloudy",         # 多云(夜)
    "152": "cloudy",         # 少云(夜)
    "153": "cloudy",         # 晴间多云(夜)
    "300": "rainy",          # 阵雨
    "301": "rainy",          # 强阵雨
    "302": "lightning-rainy",# 雷阵雨
    "305": "rainy",          # 小雨
    "306": "rainy",          # 中雨
    "307": "rainy",          # 大雨
    "315": "rainy",          # 暴雨
    "400": "snowy",          # 小雪
    "401": "snowy",          # 中雪
    "402": "snowy",          # 大雪
    "500": "fog",            # 薄雾
    "501": "fog",            # 雾
    "502": "hail",           # 霾
}