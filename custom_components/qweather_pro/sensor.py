"""QWeather (和风天气) 传感器平台."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, ATTRIBUTION
from .coordinator import QWeatherUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class QWeatherSensorEntityDescription(SensorEntityDescription):
    """自定义描述类，确保 key 用于唯一标识，translation_key 用于命名."""
    value_fn: Callable[[dict[str, Any]], Any]
    attr_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None

SENSOR_DESCRIPTIONS: tuple[QWeatherSensorEntityDescription, ...] = (
    QWeatherSensorEntityDescription(
        key="aqi",
        name="AQI",
        translation_key="aqi",
        icon="mdi:air-filter",
        value_fn=lambda data: data.get("aqi", {}).get("category", "未知"),
        attr_fn=lambda data: {
            "pm2p5": data.get("aqi", {}).get("pm2p5"),
            "pm10": data.get("aqi", {}).get("pm10"),
            "no2": data.get("aqi", {}).get("no2"),
            "so2": data.get("aqi", {}).get("so2"),
            "o3": data.get("aqi", {}).get("o3"),
            "co": data.get("aqi", {}).get("co"),
            "primary": data.get("aqi", {}).get("primary"),
        },
    ),
    QWeatherSensorEntityDescription(
        key="today_temp_range",
        name="Today Temperature Range",
        translation_key="today_temp_range",
        icon="mdi:thermometer-lines",
        value_fn=lambda data: (
            f"{int(daily[0].get('native_templow'))}°C/"
            f"{int(daily[0].get('native_temperature'))}°C"
            if (daily := data.get("daily")) else "未知"
        ),
        attr_fn=lambda data: {
            "max_temp": daily[0].get("native_temperature") if (daily := data.get("daily")) else None,
            "min_temp": daily[0].get("native_templow") if (daily := data.get("daily")) else None,
        },
    ),
    QWeatherSensorEntityDescription(
        key="warning_count",
        name="Warning Count",
        translation_key="warning_count",
        icon="mdi:alert-decagram",
        value_fn=lambda data: len(data.get("warning", [])),
    ),
    QWeatherSensorEntityDescription(
        key="precipitation_summary",
        name="Precipitation Summary",
        translation_key="precipitation_summary",
        icon="mdi:message-text-clock",
        value_fn=lambda data: data.get("minutely_summary"),
    ),
    QWeatherSensorEntityDescription(
        key="weather_summary",
        name="Weather Summary",
        translation_key="weather_summary",
        icon="mdi:weather-partly-cloudy",
        value_fn=lambda data: data.get("hourly_summary"),
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
    """和风天气传感器（官方规范版）."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, description):
        super().__init__(coordinator)

        self.entity_description = description

        self._attr_unique_id = f"{entry.entry_id}_{description.key}"

        self._attr_translation_key = description.translation_key

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"QWeather Pro {entry.title}",
            manufacturer=MANUFACTURER,
            entry_type=DeviceEntryType.SERVICE,
            sw_version=coordinator.version,
        )

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