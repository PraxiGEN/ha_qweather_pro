"""const 模块单测：轮询间隔解析、语言映射、生活指数映射.

CI（GitHub Actions）使用真实 homeassistant 运行；本文件为纯逻辑测试，不直接依赖 homeassistant 运行时。
运行：``pytest tests/test_const.py -v``（或 ``python -m pytest tests``）。
"""
from __future__ import annotations

from custom_components.qweather_pro.const import (  # noqa: E402
    DEFAULT_UPDATE_INTERVAL,
    API_KEY_UPDATE_INTERVAL,
    CONF_UPDATE_INTERVAL,
    LANGUAGE_MAP,
    SUGGESTION_TYPE_MAP,
    resolve_update_interval,
)


class TestResolveUpdateInterval:
    """API KEY→强制锁定 100min（忽略用户 options）/ JWT→默认 15min 且用户可覆盖."""

    def test_jwt_default_15min(self):
        assert resolve_update_interval({}, True) == DEFAULT_UPDATE_INTERVAL == 15

    def test_api_key_default_100min(self):
        assert resolve_update_interval({}, False) == API_KEY_UPDATE_INTERVAL == 100

    def test_user_override_wins_jwt(self):
        assert resolve_update_interval({CONF_UPDATE_INTERVAL: 30}, True) == 30

    def test_api_key_override_ignored_locked_to_100(self):
        # API KEY 认证强制锁定 100 分钟，用户在选项里填的 update_interval 必须被忽略，
        # 条目配置流也不暴露该控件（coordinator 强制 API_KEY_UPDATE_INTERVAL）。
        assert resolve_update_interval({CONF_UPDATE_INTERVAL: 5}, False) == API_KEY_UPDATE_INTERVAL == 100
        assert resolve_update_interval({CONF_UPDATE_INTERVAL: 1}, False) == API_KEY_UPDATE_INTERVAL

    def test_options_none_treated_as_default(self):
        assert resolve_update_interval(None, False) == API_KEY_UPDATE_INTERVAL

    def test_bad_override_falls_back(self):
        # 非法间隔（字符串/越界）应回退到对应认证方式的默认，而非抛异常
        assert resolve_update_interval({CONF_UPDATE_INTERVAL: "fast"}, False) == API_KEY_UPDATE_INTERVAL
        assert resolve_update_interval({CONF_UPDATE_INTERVAL: -3}, True) == DEFAULT_UPDATE_INTERVAL


class TestLanguageMap:
    """HA 语言代码 → 和风语言代码映射."""

    def test_chinese_variants_map_to_zh(self):
        assert LANGUAGE_MAP["zh-Hans"] == "zh"
        assert LANGUAGE_MAP["zh-Hant"] == "zh-hant"
        assert LANGUAGE_MAP["zh-HK"] == "zh-hant"
        assert LANGUAGE_MAP["zh-TW"] == "zh-hant"

    def test_english_variants_map_to_en(self):
        assert LANGUAGE_MAP["en"] == "en"
        assert LANGUAGE_MAP["en-GB"] == "en"
        assert LANGUAGE_MAP["en-US"] == "en"

    def test_common_languages_passthrough(self):
        assert LANGUAGE_MAP["ja"] == "ja"
        assert LANGUAGE_MAP["ko"] == "ko"
        assert LANGUAGE_MAP["ru"] == "ru"
        assert LANGUAGE_MAP["de"] == "de"
        assert LANGUAGE_MAP["fr"] == "fr"

    def test_portuguese_branches(self):
        assert LANGUAGE_MAP["pt"] == "pt"
        assert LANGUAGE_MAP["pt-BR"] == "pt"


class TestSuggestionTypeMap:
    """V7 生活指数 type 数字 → HA 命名."""

    def test_known_mappings(self):
        assert SUGGESTION_TYPE_MAP["1"] == "sport"
        assert SUGGESTION_TYPE_MAP["3"] == "drsg"
        assert SUGGESTION_TYPE_MAP["12"] == "gls"
        assert SUGGESTION_TYPE_MAP["15"] == "ptfc"

    def test_unknown_returns_unknown_key(self):
        # coordinator 用 .get(type, "unknown")，未知数字落到 unknown
        assert SUGGESTION_TYPE_MAP.get("99", "unknown") == "unknown"
