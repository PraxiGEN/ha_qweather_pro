"""coordinator 单测：单位换算、V1 解析、实况合并、缓存序列化、智能摘要.

依赖 cryptography/aiohttp，本地无 homeassistant 时自动 skip，由 CI 跑。
为避免构造需要 cryptography 的 coordinator 实例，解析/换算方法采用 unbound 调用
+ harness 借用（方法忽略 self），仅验证核心业务逻辑。

运行：``pytest tests/test_coordinator.py -v``。
"""
from __future__ import annotations

from datetime import datetime

import pytest

try:
    from custom_components.qweather_pro.coordinator import (  # noqa: E402
        QWeatherUpdateCoordinator,
    )

    _HA_OK = True
except Exception:  # pragma: no cover - 本地缺依赖时跳过
    _HA_OK = False

pytestmark = pytest.mark.skipif(not _HA_OK, reason="requires homeassistant environment")


class _Harness:
    """借用 coordinator 的实例 helper（方法忽略 self）。"""

    _to_f = QWeatherUpdateCoordinator._to_f
    _percent = QWeatherUpdateCoordinator._percent
    _speed_kmh = QWeatherUpdateCoordinator._speed_kmh
    _vis_km = QWeatherUpdateCoordinator._vis_km
    _to_utc_iso = QWeatherUpdateCoordinator._to_utc_iso
    _to_local_hm = QWeatherUpdateCoordinator._to_local_hm
    _parse_daily_period = QWeatherUpdateCoordinator._parse_daily_period
    _collect_attributions = QWeatherUpdateCoordinator._collect_attributions
    _cache_data: dict = {}


def _coord() -> _Harness:
    return _Harness()


# --- 单位换算辅助 ---


def test_to_f_safe():
    c = _coord()
    assert QWeatherUpdateCoordinator._to_f(c, None) is None
    assert QWeatherUpdateCoordinator._to_f(c, "12.5") == 12.5
    assert QWeatherUpdateCoordinator._to_f(c, "bad", 0.0) == 0.0


def test_percent_scales_zero_to_one():
    c = _coord()
    assert QWeatherUpdateCoordinator._percent(c, 0.5) == 50.0
    assert QWeatherUpdateCoordinator._percent(c, None, 0.0) == 0.0


def test_speed_kmh_mps_to_kmh():
    c = _coord()
    assert QWeatherUpdateCoordinator._speed_kmh(c, 10) == 36.0
    assert QWeatherUpdateCoordinator._speed_kmh(c, None) is None


def test_vis_km_meters_to_km():
    c = _coord()
    assert QWeatherUpdateCoordinator._vis_km(c, 10000) == 10
    assert QWeatherUpdateCoordinator._vis_km(c, None) is None


# --- V1 每日解析 ---


def _raw_day():
    return {
        "forecastStartTime": "2026-08-16T00:00:00+00:00",
        "forecastEndTime": "2026-08-17T00:00:00+00:00",
        "astro": {
            "sunrise": "2026-08-16T05:30:00+00:00",
            "sunset": "2026-08-16T18:45:00+00:00",
            "moonrise": "2026-08-16T21:10:00+00:00",
            "moonset": "2026-08-16T08:20:00+00:00",
            "moonPhase": "WaxingGibbous",
        },
        "temperatureMax": {"value": 30},
        "temperatureMin": {"value": 22},
        "uvIndexMax": 8,
        "daytime": {
            "forecastStartTime": "2026-08-16T00:00:00+00:00",
            "forecastEndTime": "2026-08-16T12:00:00+00:00",
            "condition": {"text": "晴", "code": "100", "icon": "100"},
            "temperatureMax": {"value": 30},
            "temperatureMin": {"value": 22},
            "wind": {
                "direction": {"degree": 180, "compass": "南风"},
                "speed": {"value": 10},
                "scale": "3",
            },
            "windGustMax": {"value": 20},
            "precipitation": {"amount": {"value": 0}, "probability": 0.1, "type": "none"},
            "cloudCover": 0.1,
            "humidity": 0.5,
        },
        "nighttime": {
            "forecastStartTime": "2026-08-16T12:00:00+00:00",
            "forecastEndTime": "2026-08-17T00:00:00+00:00",
            "condition": {"text": "晴", "code": "150", "icon": "150"},
            "temperatureMax": {"value": 24},
            "temperatureMin": {"value": 20},
            "wind": {
                "direction": {"degree": 200, "compass": "西南风"},
                "speed": {"value": 6},
                "scale": "2",
            },
            "windGustMax": {"value": 12},
            "precipitation": {"amount": {"value": 0}, "probability": 0.05, "type": "none"},
            "cloudCover": 0.2,
            "humidity": 0.7,
        },
    }


def test_parse_daily_nested():
    c = _coord()
    result = QWeatherUpdateCoordinator._parse_daily(c, [_raw_day()])
    assert len(result) == 1
    day = result[0]
    assert isinstance(day["datetime"], str) and "2026-08-16" in day["datetime"]
    assert day["temp_max"] == 30.0
    assert day["temp_min"] == 22.0
    assert day["uv_index_max"] == 8
    # 昼夜嵌套 + 代码映射
    assert day["daytime"]["condition"] == "sunny"
    assert day["daytime"]["wind_scale"] == "3"
    assert day["daytime"]["wind_speed"] == 36.0
    assert day["nighttime"]["condition"] == "clear-night"
    assert day["nighttime"]["wind_scale"] == "2"
    assert day["astro"]["moon_phase"] == "WaxingGibbous"
    assert day["astro"]["sunrise"] == "05:30"


def test_parse_hourly():
    c = _coord()
    raw = [
        {
            "forecastTime": "2026-08-16T08:00:00+00:00",
            "condition": {"text": "晴", "code": "100"},
            "temperature": {"value": 26},
            "feelsLike": {"value": 28},
            "humidity": 0.5,
            "wind": {
                "direction": {"degree": 180},
                "speed": {"value": 10},
                "scale": "3",
            },
            "windGust": {"value": 18},
            "precipitation": {"amount": {"value": 0}, "probability": 0.1, "type": "none"},
            "pressure": {"value": 1013},
            "visibility": {"value": 10000},
            "dewPoint": {"value": 15},
            "cloudCover": 0.1,
            "uvIndex": 5,
        }
    ]
    result = QWeatherUpdateCoordinator._parse_hourly(c, raw)
    assert len(result) == 1
    h = result[0]
    assert h["condition"] == "sunny"
    assert h["native_temperature"] == 26.0
    assert h["native_wind_speed"] == 36.0
    assert h["native_precipitation"] == 0.0


def test_parse_indices_uses_suggestion_map():
    c = _coord()
    raw = [{"date": "2026-08-16", "type": "1", "name": "运动", "category": "适宜", "level": "1", "text": "适合"}]
    result = QWeatherUpdateCoordinator._parse_indices(c, raw)
    assert result[0]["type"] == "sport"
    assert result[0]["title"] == "运动"


# --- 实况合并 ---


def _now_raw():
    return {
        "condition": {"text": "晴", "code": "100"},
        "temperature": {"value": 25},
        "feelsLike": {"value": 27},
        "humidity": 0.5,
        "wind": {
            "direction": {"degree": 180, "compass": "南风"},
            "speed": {"value": 10},
            "scale": "3",
        },
        "windGust": {"value": 20},
        "precipitation": {"amount": {"value": 0}},
        "pressure": {"value": 1013},
        "visibility": {"value": 10000},
        "dewPoint": {"value": 15},
        "cloudCover": 0.1,
        "uvIndex": 5,
    }


def test_merge_now_current_priority():
    c = _coord()
    merged = QWeatherUpdateCoordinator._merge_now(c, _now_raw(), None, datetime(2026, 8, 16, 10))
    assert merged["condition"] == "sunny"
    assert merged["temp"] == 25.0
    assert merged["humidity"] == 50.0
    assert merged["windSpeed"] == 36.0
    assert merged["windDir"] == "南风"
    assert merged["vis"] == 10
    assert merged["degraded"] is False


def test_merge_now_degraded_when_missing():
    c = _coord()
    merged = QWeatherUpdateCoordinator._merge_now(c, {}, None, datetime(2026, 8, 16, 10))
    assert merged["degraded"] is True
    assert merged["condition"] == "exceptional"
    assert merged["temp"] is None


# --- 缓存序列化 ---


def test_collect_attributions_dedup():
    c = _coord()
    cache = {
        "now": {"metadata": {"attributions": ["https://a", "https://b"]}},
        "daily": {"metadata": {"attributions": ["https://a"]}},
    }
    assert QWeatherUpdateCoordinator._collect_attributions(cache) == ["https://a", "https://b"]


# --- 智能摘要 ---


def test_generate_smart_abstract_morning():
    c = _coord()
    now = {"text_cn": "晴", "windScale": "3", "temp": 25}
    daily = [
        {"temperatureMax": {"value": 30}, "temperatureMin": {"value": 22}, "daytime": {"condition": {"text": "晴"}}},
        {"temperatureMax": {"value": 28}, "temperatureMin": {"value": 20}, "daytime": {"condition": {"text": "多云"}}},
    ]
    abstract = QWeatherUpdateCoordinator._generate_smart_abstract(c, now, daily, datetime(2026, 8, 16, 10))
    assert abstract["period"] == "morning"
    assert abstract["wind_status"] == "windy"
    assert abstract["temp_change_type"] in {"colder", "steady", "warmer"}
