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
CONF_ACCOUNT_SELECT: Final = "account_selection"

CONF_UPDATE_INTERVAL: Final = "update_interval"
CONF_HOURLYSTEPS: Final = "hourlysteps"
CONF_DAILYSTEPS: Final = "dailysteps"
CONF_GIRD: Final = "gird"
CONF_CUSTOM_UI: Final = "custom_ui"

# --- 属性扩展键名 ---
ATTR_UPDATE_TIME: Final = "update_time"
ATTR_AQI: Final = "aqi"
ATTR_SUGGESTION: Final = "suggestion"

# --- 默认值 ---
DEFAULT_NAME: Final = "和风天气Pro"
DEFAULT_UPDATE_INTERVAL: Final = 15

# --- 生活指数类型映射 (QWeather API v7) ---
SUGGESTION_TYPE_MAP: Final[dict[str, str]] = {
    "1": "sport",    "2": "cw",       "3": "drsg",     "4": "fishing",
    "5": "uv",       "6": "trav",     "7": "ag",       "8": "comf",
    "9": "flu",      "10": "air",     "11": "ac",      "12": "gls",
    "13": "mu",      "14": "dc",      "15": "ptfc",    "16": "fsh",
}

# HA 语言代码映射到和风天气语言代码
# 涵盖了和风天气支持的所有 30+ 种语言
LANGUAGE_MAP: Final[dict[str, str]] = {
    # 中文系列
    "zh-Hans": "zh",       # 简体中文
    "zh-Hant": "zh-hant",  # 繁体中文
    "zh-HK": "zh-hant",    # 香港繁体
    "zh-TW": "zh-hant",    # 台湾繁体

    # 英文
    "en": "en",
    "en-GB": "en",
    "en-US": "en",

    # 欧洲语系
    "de": "de",            # 德语
    "es": "es",            # 西班牙语
    "fr": "fr",            # 法语
    "it": "it",            # 意大利语
    "nl": "nl",            # 荷兰语
    "el": "el",            # 希腊语
    "sv": "sv",            # 瑞典语
    "pl": "pl",            # 波兰语
    "tr": "tr",            # 土耳其语
    "cs": "cs",            # 捷克语
    "et": "et",            # 爱沙尼亚语
    "fi": "fi",            # 芬兰语
    "is": "is",            # 冰岛语
    "nb": "nb",            # 挪威语 (Bokmål)
    "no": "nb",            # 挪威语回退

    # 亚洲语系
    "ja": "ja",            # 日语
    "ko": "ko",            # 韩语
    "ru": "ru",            # 俄语
    "hi": "hi",            # 印地语
    "th": "th",            # 泰语
    "vi": "vi",            # 越南语
    "ms": "ms",            # 马来语
    "id": "id",            # 印尼语
    "fil": "fil",          # 菲律宾语

    # 中东/其他
    "ar": "ar",            # 阿拉伯语
    "he": "he",            # 希伯来语
    "pt": "pt",            # 葡萄牙语
    "pt-BR": "pt",         # 巴西葡萄牙语
    "bn": "bn",            # 孟加拉语
    "la": "la",            # 拉丁语
}