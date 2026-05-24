"""QWeather (和风天气) 集成常量定义."""
from __future__ import annotations

from typing import Final
from homeassistant.const import Platform

# --- 基础信息 ---
DOMAIN: Final = "qweather"
VERSION: Final = "1.0.0"
MANUFACTURER: Final = "QWeather Pro"
ATTRIBUTION: Final = "Data provided by QWeather Pro"

# --- 支持的平台 ---
PLATFORMS: Final = [Platform.WEATHER, Platform.SENSOR]

# --- 配置流用到的键名 (Config & Options) ---
CONF_API_KEY: Final = "api_key"
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

# --- 补全缺失的常量 (用于 Coordinator 和 OptionsFlow) ---
CONF_ALERT: Final = "alert"          # <--- 修复 ImportError 的关键
CONF_GIRD: Final = "gird"            # 对应网格天气选项
CONF_CUSTOM_UI: Final = "custom_ui"  # 对应自定义 UI 选项

# --- 属性扩展键名 ---
ATTR_UPDATE_TIME: Final = "update_time"
ATTR_AQI: Final = "aqi"
ATTR_SUGGESTION: Final = "suggestion"

# --- 生活指数类型映射 (QWeather API v7) ---
SUGGESTION_TYPE_MAP: Final[dict[str, str]] = {
    "1": "sport",    "2": "cw",       "3": "drsg",     "4": "fishing",
    "5": "uv",       "6": "trav",     "7": "ag",       "8": "comf",
    "9": "flu",      "10": "air",     "11": "ac",      "12": "gls",
    "13": "mu",      "14": "dc",      "15": "ptfc",    "16": "fsh",
}

SUGGESTION_NAME_MAP: Final[dict[str, str]] = {
    "sport": "运动指数", "cw": "洗车指数", "drsg": "穿衣指数", "fishing": "钓鱼指数",
    "uv": "紫外线指数", "trav": "旅游指数", "ag": "过敏指数", "comf": "舒适度指数",
    "flu": "感冒指数", "air": "空气指数", "ac": "空调指数", "gls": "太阳镜指数",
    "mu": "化妆指数", "dc": "晾晒指数", "ptfc": "交通指数", "fsh": "防晒指数",
}
