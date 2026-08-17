"""sensor 平台单测：5 个传感器的 native_value 与扩展属性.

依赖 cryptography/aiohttp，本地无 homeassistant 时自动 skip，由 CI 跑。
运行：``pytest tests/test_sensor.py -v``。
"""
from __future__ import annotations

import pytest

try:
    from custom_components.qweather_pro.sensor import (  # noqa: E402
        QWeatherSensor,
        SENSOR_DESCRIPTIONS,
    )

    _HA_OK = True
except Exception:  # pragma: no cover - 本地缺依赖时跳过
    _HA_OK = False

pytestmark = pytest.mark.skipif(not _HA_OK, reason="requires homeassistant environment")


@pytest.fixture
def sensor_data() -> dict:
    return {
        "aqi": {
            "aqi": 50,
            "level": "良",
            "category": "优",
            "aqi_unit": "μg/m3",
            "pm2p5": 20,
            "pm2p5_unit": "μg/m3",
            "pm10": 40,
            "pm10_unit": "μg/m3",
            "no2": 30,
            "no2_unit": "ppb",
            "so2": 6,
            "so2_unit": "ppb",
            "o3": 80,
            "o3_unit": "ppb",
            "co": 0.6,
            "co_unit": "ppm",
            "primary": "无",
            "health_effect": "无",
            "health_advice": "适宜",
            "stations": "站点A",
        },
        "daily": [
            {"temp_min": 22, "temp_max": 30},
        ],
        "warning": [{"title": "高温橙色预警"}],
        "minutely_summary": "未来两小时无降水",
        "weather_abstract": {"tonight_text": "晴"},
        "minutely_detail": [],
    }


def _sensor(key: str):
    return next(d for d in SENSOR_DESCRIPTIONS if d.key == key)


def test_all_five_sensors_defined():
    keys = {d.key for d in SENSOR_DESCRIPTIONS}
    assert keys == {
        "aqi",
        "today_temp_range",
        "warning_info",
        "precipitation_summary",
        "weather_summary",
    }


def test_aqi_native_value(mock_coordinator, mock_config_entry, sensor_data):
    mock_coordinator.data = sensor_data
    entity = QWeatherSensor(mock_coordinator, mock_config_entry, _sensor("aqi"))
    assert entity.native_value == "优"


def test_aqi_extra_attributes_formatted(mock_coordinator, mock_config_entry, sensor_data):
    mock_coordinator.data = sensor_data
    entity = QWeatherSensor(mock_coordinator, mock_config_entry, _sensor("aqi"))
    attrs = entity.extra_state_attributes
    assert attrs["aqi_value"] == "50 μg/m3"
    assert attrs["pm2p5"] == "20 μg/m3"
    assert attrs["primary_pollutant"] == "无"
    assert attrs["attribution"]


def test_today_temp_range(mock_coordinator, mock_config_entry, sensor_data):
    mock_coordinator.data = sensor_data
    entity = QWeatherSensor(mock_coordinator, mock_config_entry, _sensor("today_temp_range"))
    assert entity.native_value == "22°C/30°C"
    assert entity.extra_state_attributes["max_temp"] == "30°C"
    assert entity.extra_state_attributes["min_temp"] == "22°C"


def test_today_temp_range_unknown_without_daily(mock_coordinator, mock_config_entry):
    mock_coordinator.data = {}
    entity = QWeatherSensor(mock_coordinator, mock_config_entry, _sensor("today_temp_range"))
    assert entity.native_value == "unknown"


def test_warning_info(mock_coordinator, mock_config_entry, sensor_data):
    mock_coordinator.data = sensor_data
    entity = QWeatherSensor(mock_coordinator, mock_config_entry, _sensor("warning_info"))
    assert entity.native_value == "高温橙色预警"
    assert entity.extra_state_attributes["title"] == "高温橙色预警"


def test_warning_info_without_warning(mock_coordinator, mock_config_entry):
    mock_coordinator.data = {"warning": []}
    entity = QWeatherSensor(mock_coordinator, mock_config_entry, _sensor("warning_info"))
    assert entity.native_value == "without_warning"


def test_precipitation_summary(mock_coordinator, mock_config_entry, sensor_data):
    mock_coordinator.data = sensor_data
    entity = QWeatherSensor(mock_coordinator, mock_config_entry, _sensor("precipitation_summary"))
    assert entity.native_value == "未来两小时无降水"


def test_weather_summary(mock_coordinator, mock_config_entry, sensor_data):
    mock_coordinator.data = sensor_data
    entity = QWeatherSensor(mock_coordinator, mock_config_entry, _sensor("weather_summary"))
    assert entity.native_value == "晴"
    assert entity.extra_state_attributes["tonight_text"] == "晴"


def test_native_value_none_when_no_data(mock_coordinator, mock_config_entry):
    mock_coordinator.data = None
    entity = QWeatherSensor(mock_coordinator, mock_config_entry, _sensor("aqi"))
    assert entity.native_value is None


def test_attr_fn_exception_is_swallowed(mock_coordinator, mock_config_entry):
    """attr_fn 抛异常不应导致实体属性读取崩溃（集成健壮性）。"""
    import types

    bad = types.SimpleNamespace(
        key="bad",
        translation_key="bad",
        value_fn=lambda data: "x",
        attr_fn=lambda data: 1 / 0,
    )
    mock_coordinator.data = {}
    entity = QWeatherSensor(mock_coordinator, mock_config_entry, bad)
    # 不应抛异常
    assert entity.extra_state_attributes == {"attribution": entity.extra_state_attributes["attribution"]}
