"""weather 平台单测：当前天气属性、三种预报（daily/hourly/twice_daily）、扩展属性.

依赖 cryptography/aiohttp，本地无 homeassistant 时自动 skip，由 CI 跑。
运行：``pytest tests/test_weather.py -v``。
"""
from __future__ import annotations

import asyncio

import pytest

try:
    from custom_components.qweather_pro.weather import (  # noqa: E402
        HeFengWeather,
        QWEATHER_WEATHER_DESCRIPTION,
    )

    _HA_OK = True
except Exception:  # pragma: no cover - 本地缺依赖时跳过
    _HA_OK = False

pytestmark = pytest.mark.skipif(not _HA_OK, reason="requires homeassistant environment")


@pytest.fixture
def weather_data() -> dict:
    """模拟 coordinator.data：V1 嵌套结构（与 coordinator._parse_daily 输出一致）。"""
    return {
        "now": {
            "condition": "sunny",
            "temp": 25.0,
            "feelsLike": 27.0,
            "humidity": 50,
            "pressure": 1013,
            "windSpeed": 10.0,
            "wind360": 180,
            "vis": 10.0,
            "dew": 15.0,
            "precip": 0.0,
            "cloud": 10,
            "uv_index": 5,
            "icon": "100",
            "text_cn": "晴",
        },
        "daily": [
            {
                "datetime": "2026-08-16T00:00:00+00:00",
                "temp_max": 30.0,
                "temp_min": 22.0,
                "temp_avg": 26.0,
                "uv_index_max": 8,
                "daytime": {
                    "start": "2026-08-16T00:00:00+00:00",
                    "end": "2026-08-16T12:00:00+00:00",
                    "text": "晴",
                    "condition": "sunny",
                    "icon": "100",
                    "temp_max": 30.0,
                    "temp_min": 22.0,
                    "wind_degree": 180,
                    "wind_compass": "南风",
                    "wind_speed": 12.0,
                    "wind_scale": "3",
                    "wind_gust_max": 20.0,
                    "precip_amount": 0.0,
                    "precip_probability": 10,
                    "precip_type": "none",
                    "cloud": 10,
                    "humidity": 50,
                },
                "nighttime": {
                    "start": "2026-08-16T12:00:00+00:00",
                    "end": "2026-08-17T00:00:00+00:00",
                    "text": "晴",
                    "condition": "sunny",
                    "icon": "150",
                    "temp_max": 24.0,
                    "temp_min": 20.0,
                    "wind_degree": 200,
                    "wind_compass": "西南风",
                    "wind_speed": 6.0,
                    "wind_scale": "2",
                    "wind_gust_max": 12.0,
                    "precip_amount": 0.0,
                    "precip_probability": 5,
                    "precip_type": "none",
                    "cloud": 20,
                    "humidity": 70,
                },
                "astro": {
                    "sunrise": "05:30",
                    "sunset": "18:45",
                    "moonrise": "21:10",
                    "moonset": "08:20",
                    "moon_phase": "WaxingGibbous",
                },
            }
        ],
        "hourly": [
            {
                "datetime": "2026-08-16T08:00:00+00:00",
                "text": "晴",
                "condition": "sunny",
                "icon": "100",
                "native_temperature": 26.0,
                "native_apparent_temperature": 28.0,
                "native_humidity": 50,
                "native_wind_bearing": 180,
                "wind_compass": "南风",
                "native_wind_speed": 10.0,
                "wind_scale": "3",
                "native_wind_gust_speed": 18.0,
                "native_precipitation": 0.0,
                "precipitation_intensity": 0.0,
                "precipitation_type": "none",
                "precipitation_probability": 10,
                "native_pressure": 1013,
                "native_visibility": 10.0,
                "native_dew_point": 15.0,
                "native_cloud_coverage": 10,
                "uv_index": 5,
            }
        ],
        "aqi": {"aqi": 50, "level": "良", "category": "优"},
        "warning": [{"title": "高温橙色预警"}],
        "indices": [],
        "city": "测试城市",
        "update_time": "2026-08-16 08:00:00",
        "minutely_summary": "未来两小时无降水",
        "weather_abstract": {
            "period": "morning",
            "tonight_text": "晴",
            "temp_change_type": "steady",
            "current_temp": 25,
            "wind_status": "calm",
            "aqi_level": "good",
        },
        "minutely_detail": [],
    }


@pytest.fixture
def weather_entity(mock_coordinator, mock_config_entry, weather_data):
    mock_coordinator.data = weather_data
    return HeFengWeather(mock_coordinator, mock_config_entry, QWEATHER_WEATHER_DESCRIPTION)


def test_current_condition(weather_entity):
    assert weather_entity.condition == "sunny"


def test_native_temperature(weather_entity):
    assert weather_entity.native_temperature == 25.0


def test_native_apparent_temperature(weather_entity):
    assert weather_entity.native_apparent_temperature == 27.0


def test_wind_bearing_from_now(weather_entity):
    assert weather_entity.wind_bearing == 180


def test_supported_features_include_all_forecasts(weather_entity):
    from homeassistant.components.weather import WeatherEntityFeature

    feats = weather_entity.supported_features
    assert feats & WeatherEntityFeature.FORECAST_DAILY
    assert feats & WeatherEntityFeature.FORECAST_HOURLY
    assert feats & WeatherEntityFeature.FORECAST_TWICE_DAILY


def test_forecast_daily_nested_keys(weather_entity):
    fc = asyncio.run(weather_entity.async_forecast_daily())
    assert isinstance(fc, list) and len(fc) == 1
    day = fc[0]
    # HA 标准键
    assert day["condition"] == "sunny"
    assert day["native_temperature"] == 30.0
    assert day["native_templow"] == 22.0
    assert day["temperature"] == 30.0
    assert day["templow"] == 22.0
    # V1 昼夜嵌套自定义键
    assert day["icon_night"] == "150"
    assert day["text_night"] == "晴"
    assert day["wind_scale_day"] == "3"
    assert day["wind_scale_night"] == "2"
    assert day["wind_dir_day"] == "南风"
    assert day["wind_compass"] is None or isinstance(day.get("wind_compass"), str)


def test_forecast_hourly(weather_entity):
    fc = asyncio.run(weather_entity.async_forecast_hourly())
    assert len(fc) == 1
    assert fc[0]["condition"] == "sunny"
    assert fc[0]["native_temperature"] == 26.0


def test_forecast_twice_daily_day_and_night(weather_entity):
    fc = asyncio.run(weather_entity.async_forecast_twice_daily())
    assert len(fc) == 2
    assert fc[0]["is_daytime"] is True
    assert fc[1]["is_daytime"] is False
    assert fc[0]["native_temperature"] == 30.0
    assert fc[1]["native_temperature"] == 24.0


def test_extra_state_attributes(weather_entity):
    attrs = weather_entity.extra_state_attributes
    assert attrs["attribution"]
    assert attrs["city"] == "测试城市"
    assert attrs["update_time"] == "2026-08-16 08:00:00"
    # 今日预报扩展属性
    assert attrs["wind_scale_day"] == "3"
    assert attrs["icon_night"] == "150"
    assert attrs["moon_phase"] == "WaxingGibbous"
    assert attrs["sunrise"] == "05:30"


def test_extra_state_attributes_empty_when_no_data(mock_coordinator, mock_config_entry):
    mock_coordinator.data = {}
    entity = HeFengWeather(mock_coordinator, mock_config_entry, QWEATHER_WEATHER_DESCRIPTION)
    assert entity.extra_state_attributes == {}
