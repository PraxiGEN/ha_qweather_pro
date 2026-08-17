"""qweather_pro.get_weather 服务单测（CI 真实 homeassistant 下运行）.

聚焦纯逻辑：服务入参 schema 校验、标量/列表归一化、合法 key 集合。
完整 handler（依赖注册表解析 target 实体）由 test_init 的集成测试覆盖。

运行：``python -m pytest tests/test_services.py -v``。
"""
from __future__ import annotations

import pytest

try:
    from custom_components.qweather_pro.services import (  # noqa: E402
        _as_list,
        INTERNAL_KEYS,
        SERVICE_GET_WEATHER_SCHEMA,
        VALID_KEYS,
    )

    _HA_OK = True
except Exception:  # pragma: no cover - 本地缺依赖时跳过
    _HA_OK = False

pytestmark = pytest.mark.skipif(
    not _HA_OK, reason="requires homeassistant environment"
)


def test_valid_keys_scalar_string_normalized():
    """标量字符串应被归一化为单元素列表。"""
    result = SERVICE_GET_WEATHER_SCHEMA({"keys": "city"})
    assert result["keys"] == ["city"]


def test_valid_keys_list_passthrough():
    result = SERVICE_GET_WEATHER_SCHEMA({"keys": ["city", "now", "aqi"]})
    assert result["keys"] == ["city", "now", "aqi"]


def test_invalid_key_rejected():
    with pytest.raises(Exception):
        SERVICE_GET_WEATHER_SCHEMA({"keys": ["not_a_real_key"]})


def test_optional_keys_absent_ok():
    result = SERVICE_GET_WEATHER_SCHEMA({})
    assert "keys" not in result


def test_as_list_normalization():
    assert _as_list(None) == []
    assert _as_list("city") == ["city"]
    assert _as_list(["city", "now"]) == ["city", "now"]


def test_valid_keys_is_frozen_set_of_expected():
    expected = (
        "city",
        "now",
        "daily",
        "hourly",
        "aqi",
        "warning",
        "indices",
        "weather_abstract",
        "minutely_detail",
        "minutely_summary",
        "update_time",
        "attributions",
    )
    for key in expected:
        assert key in VALID_KEYS
    # 内部诊断字段不应出现在对外暴露的合法 key 中
    assert "cache_freshness" in INTERNAL_KEYS
    assert "cache_freshness" not in VALID_KEYS
