"""QWeather (和风天气) 传感器平台."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
)

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, ATTRIBUTION, LOGGER
from .coordinator import QWeatherUpdateCoordinator

@dataclass(frozen=True, kw_only=True)
class QWeatherSensorEntityDescription(SensorEntityDescription):
    """自定义描述类，确保 key 用于唯一标识，translation_key 用于命名."""
    value_fn: Callable[[dict[str, Any]], Any]
    attr_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None

SENSOR_DESCRIPTIONS: tuple[QWeatherSensorEntityDescription, ...] = (
    QWeatherSensorEntityDescription(
        key="aqi",
        translation_key="aqi",
        icon="mdi:air-filter",
        value_fn=lambda data: data.get("aqi", {}).get("category", "Unknown"),
        attr_fn=lambda data: {
            # 基础数据
            "aqi_value": (aqi := data.get("aqi", {})).get("aqi"),
            "aqi_level": aqi.get("level"),
            "primary_pollutant": aqi.get("primary", "None"),

            # 污染物浓度 (带单位，且增加空值保护)
            # 使用 get(..., '--') 确保在数据缺失时不会显示 'None μg/m3'
            "pm2p5": f"{aqi.get('pm2p5', '--')} {aqi.get('pm2p5_unit', 'μg/m3')}",
            "pm10": f"{aqi.get('pm10', '--')} {aqi.get('pm10_unit', 'μg/m3')}",
            "no2": f"{aqi.get('no2', '--')} {aqi.get('no2_unit', 'ppb')}",
            "so2": f"{aqi.get('so2', '--')} {aqi.get('so2_unit', 'ppb')}",
            "o3": f"{aqi.get('o3', '--')} {aqi.get('o3_unit', 'ppb')}",
            "co": f"{aqi.get('co', '--')} {aqi.get('co_unit', 'ppm')}",

            # 健康建议 (V1 接口的精华字段)
            "health_effect": aqi.get("health_effect", "No data available"),
            "health_advice": aqi.get("health_advice", "Please refer to the recommendations of the local meteorological authorities"),

            # 监测站信息
            "stations": aqi.get("stations", "No monitoring station information available"),
        },
    ),
    QWeatherSensorEntityDescription(
        key="today_temp_range",
        translation_key="today_temp_range",
        icon="mdi:thermometer-lines",
        value_fn=lambda data: (
            f"{int(daily[0].get('native_templow'))}°C/"
            f"{int(daily[0].get('native_temperature'))}°C"
            if (daily := data.get("daily")) else "Unknown"
        ),
        attr_fn=lambda data: {
            "max_temp": f"{daily[0].get('native_temperature')}°C" if (daily := data.get("daily")) and len(daily) > 0 else None,
            "min_temp": f"{daily[0].get('native_templow')}°C" if (daily := data.get("daily")) and len(daily) > 0 else None,
        },
    ),
    QWeatherSensorEntityDescription(
        key="warning_info",
        translation_key="warning_info",
        icon="mdi:alert-decagram",
        value_fn=lambda data: data.get("warning", [{}])[0].get("title", "Without warning") if data.get("warning") else "Without warning",
        attr_fn=lambda data: (
            data.get("warning")[0] if data.get("warning") and len(data.get("warning")) > 0 else {}
        ),
    ),
    QWeatherSensorEntityDescription(
        key="precipitation_summary",
        translation_key="precipitation_summary",
        icon="mdi:message-text-clock",
        value_fn=lambda data: data.get("minutely_summary", "No precipitation in the next two hours"),
        attr_fn=lambda data: {
            "detail": data.get("minutely_detail", [])
        },
    ),
    QWeatherSensorEntityDescription(
        key="weather_summary",
        translation_key="weather_summary",
        icon="mdi:weather-partly-cloudy",
        value_fn=lambda data: data.get("weather_abstract", {}).get("tonight_text"),
        attr_fn=lambda data: data.get("weather_abstract", {}),
    ),
)

async def async_setup_entry(
    hass: HomeAssistant, 
    entry: QWeatherConfigEntry,
    async_add_entities: AddEntitiesCallback
) -> None:
    """设置平台实体."""
    coordinator = entry.runtime_data

    async_add_entities(
        QWeatherSensor(coordinator, entry, description)
        for description in SENSOR_DESCRIPTIONS
    )

class QWeatherSensor(CoordinatorEntity[QWeatherUpdateCoordinator], SensorEntity):
    """和风天气传感器."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, description):
        super().__init__(coordinator)

        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_translation_key = description.translation_key
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self) -> Any:
        """从 Coordinator 获取数据."""
        if not self.coordinator.data:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """添加额外属性."""
        attrs = {"attribution": ATTRIBUTION}
        if self.entity_description.attr_fn:
            try:
                attrs.update(self.entity_description.attr_fn(self.coordinator.data))
            except Exception:
                pass
        return attrs