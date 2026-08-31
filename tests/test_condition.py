"""condition 模块单测：和风天气代码 → HA 标准天气状态映射.

CI（GitHub Actions）使用真实 homeassistant 运行；``ATTR_CONDITION_*`` 常量由真实 homeassistant 提供。
运行：``pytest tests/test_condition.py -v``。
"""
from __future__ import annotations

from homeassistant.components.weather import (  # noqa: E402
    ATTR_CONDITION_SUNNY,
    ATTR_CONDITION_PARTLYCLOUDY,
    ATTR_CONDITION_CLOUDY,
    ATTR_CONDITION_RAINY,
    ATTR_CONDITION_LIGHTNING_RAINY,
    ATTR_CONDITION_CLEAR_NIGHT,
    ATTR_CONDITION_SNOWY,
    ATTR_CONDITION_EXCEPTIONAL,
    ATTR_CONDITION_HAIL,
    ATTR_CONDITION_POURING,
    ATTR_CONDITION_SNOWY_RAINY,
    ATTR_CONDITION_FOG,
)

from custom_components.qweather_pro.condition import CONDITION_MAP  # noqa: E402


class TestConditionMap:
    """验证关键天气代码映射到正确的 HA 状态常量."""

    def test_sunny(self):
        assert CONDITION_MAP["100"] == ATTR_CONDITION_SUNNY

    def test_partly_cloudy(self):
        assert CONDITION_MAP["101"] == ATTR_CONDITION_PARTLYCLOUDY
        assert CONDITION_MAP["103"] == ATTR_CONDITION_PARTLYCLOUDY

    def test_cloudy(self):
        # 少云/阴 在 HA 中统一为 cloudy
        assert CONDITION_MAP["102"] == ATTR_CONDITION_CLOUDY
        assert CONDITION_MAP["104"] == ATTR_CONDITION_CLOUDY

    def test_rain_and_thunder(self):
        assert CONDITION_MAP["300"] == ATTR_CONDITION_RAINY
        assert CONDITION_MAP["302"] == ATTR_CONDITION_LIGHTNING_RAINY

    def test_night_clear(self):
        assert CONDITION_MAP["150"] == ATTR_CONDITION_CLEAR_NIGHT

    def test_snow(self):
        assert CONDITION_MAP["400"] == ATTR_CONDITION_SNOWY

    def test_unknown_code_falls_back_to_exceptional(self):
        # "999" 在映射表中显式指向 exceptional；真正未收录的代码用 .get(code, exceptional) 兜底
        assert CONDITION_MAP["999"] == ATTR_CONDITION_EXCEPTIONAL
        assert "998" not in CONDITION_MAP
        assert CONDITION_MAP.get("998", ATTR_CONDITION_EXCEPTIONAL) == ATTR_CONDITION_EXCEPTIONAL

    def test_all_values_are_valid_ha_conditions(self):
        valid = {
            ATTR_CONDITION_SUNNY,
            ATTR_CONDITION_PARTLYCLOUDY,
            ATTR_CONDITION_CLOUDY,
            ATTR_CONDITION_RAINY,
            ATTR_CONDITION_LIGHTNING_RAINY,
            ATTR_CONDITION_CLEAR_NIGHT,
            ATTR_CONDITION_SNOWY,
            ATTR_CONDITION_EXCEPTIONAL,
            ATTR_CONDITION_HAIL,
            ATTR_CONDITION_POURING,
            ATTR_CONDITION_SNOWY_RAINY,
            ATTR_CONDITION_FOG,
        }
        # 映射值要么是已知 HA 状态，要么是兜底 exceptional
        assert set(CONDITION_MAP.values()).issubset(valid)
