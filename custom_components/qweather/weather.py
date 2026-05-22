"""QWeather (和风天气) 天气平台实现."""
from __future__ import annotations

import logging
from homeassistant.components.weather import (
    Forecast,
    WeatherEntity,
    WeatherEntityDescription,
    WeatherEntityFeature,
)
from homeassistant.const import (
    UnitOfLength,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, ATTRIBUTION, CONF_CUSTOM_UI
from .coordinator import QWeatherUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

QWEATHER_WEATHER_DESCRIPTION = WeatherEntityDescription(
    key="weather",
    name="Weather",                 # 英文实体名（用于 entity_id）
    translation_key="weather",      # 翻译键（用于 UI）
    icon="mdi:weather-partly-cloudy",
)


async def async_setup_entry(hass, entry, async_add_entities):
    """通过配置条目设置天气实体."""
    coordinator: QWeatherUpdateCoordinator = entry.runtime_data

    async_add_entities([
        HeFengWeather(coordinator, entry, QWEATHER_WEATHER_DESCRIPTION)
    ])


class HeFengWeather(CoordinatorEntity[QWeatherUpdateCoordinator], WeatherEntity):
    """和风天气实体类（官方规范版）."""

    entity_description: WeatherEntityDescription
    _attr_has_entity_name = True

    _attr_native_precipitation_unit = UnitOfLength.MILLIMETERS
    _attr_native_pressure_unit = UnitOfPressure.HPA
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_visibility_unit = UnitOfLength.KILOMETERS
    _attr_native_wind_speed_unit = UnitOfSpeed.KILOMETERS_PER_HOUR

    def __init__(self, coordinator, entry, description: WeatherEntityDescription):
        super().__init__(coordinator)
    
        self.entity_description = description
    
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
    
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="QWeather Pro",
            manufacturer=MANUFACTURER,
            entry_type=DeviceEntryType.SERVICE,
            sw_version=coordinator.version,
        )
    
        self._attr_supported_features = (
            WeatherEntityFeature.FORECAST_DAILY |
            WeatherEntityFeature.FORECAST_HOURLY
        )

    # --- 当前天气数据 ---

    @property
    def condition(self) -> str | None:
        return self.coordinator.data.get("now", {}).get("condition")

    @property
    def native_temperature(self) -> float | None:
        return self.coordinator.data.get("now", {}).get("temp")

    @property
    def humidity(self) -> float | None:
        return self.coordinator.data.get("now", {}).get("humidity")

    @property
    def native_pressure(self) -> float | None:
        return self.coordinator.data.get("now", {}).get("pressure")

    @property
    def native_wind_speed(self) -> float | None:
        return self.coordinator.data.get("now", {}).get("windSpeed")

    @property
    def wind_bearing(self) -> float | str | None:
        return self.coordinator.data.get("now", {}).get("wind360")

    @property
    def native_visibility(self) -> float | None:
        return self.coordinator.data.get("now", {}).get("vis")

    @property
    def native_dew_point(self) -> float | None:
        return self.coordinator.data.get("now", {}).get("dew")

    @property
    def cloud_coverage(self) -> float | None:
        return self.coordinator.data.get("now", {}).get("cloud")

    # --- 预报 ---

    async def async_forecast_daily(self) -> list[Forecast] | None:
        return self.coordinator.data.get("daily")

    async def async_forecast_hourly(self) -> list[Forecast] | None:
        return self.coordinator.data.get("hourly")

    # --- 扩展属性 ---

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data
        if not data:
            return {}

        now = data.get("now", {})

        attrs = {
            "attribution": ATTRIBUTION,
            "city": data.get("city"),
            "qweather_icon": now.get("icon"),
            "update_time": data.get("update_time"),
            "obs_time": now.get("obsTime"),
            "condition_cn": now.get("text_cn"),
            "feels_like": now.get("feelsLike"),
            "wind_dir": now.get("windDir"),
            "wind_scale": now.get("windScale"),
            "humidity": now.get("humidity"),
            "pressure": now.get("pressure"),
            "visibility": now.get("vis"),
            "cloud": now.get("cloud"),
            "precip": now.get("precip"),
            "dew": now.get("dew"),
            "minutely_summary": data.get("minutely_summary"),
            "hourly_summary": data.get("hourly_summary"),
        }

        if data.get("aqi"):
            attrs["aqi"] = data.get("aqi")
        if data.get("warning"):
            attrs["warning"] = data.get("warning")
        if data.get("indices"):
            attrs["suggestion"] = data.get("indices")

        if self.coordinator.entry.options.get(CONF_CUSTOM_UI):
            attrs["custom_ui_more_info"] = "qweather-more-info"

        return attrs
