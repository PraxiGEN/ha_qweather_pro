"""QWeather (和风天气) 天气平台实现."""
from __future__ import annotations

import logging
from typing import Any

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

# 定义天气描述符
QWEATHER_WEATHER_DESCRIPTION = WeatherEntityDescription(
    key="weather",
    name="Weather", 
    translation_key="weather",
    icon="mdi:weather-partly-cloudy",
)

async def async_setup_entry(hass, entry, async_add_entities):
    """通过配置条目设置天气实体."""
    coordinator: QWeatherUpdateCoordinator = entry.runtime_data
    # 标题已经在 config_flow 中确定为城市名
    async_add_entities([
        HeFengWeather(coordinator, entry, QWEATHER_WEATHER_DESCRIPTION)
    ])

class HeFengWeather(CoordinatorEntity[QWeatherUpdateCoordinator], WeatherEntity):
    """和风天气实体类."""

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
            name=f"QWeather Pro {entry.title}",
            manufacturer=MANUFACTURER,
            entry_type=DeviceEntryType.SERVICE,
            sw_version=str(coordinator.version or "1.0.0"),
        )
    
        # 4. 声明支持的功能
        self._attr_supported_features = (
            WeatherEntityFeature.FORECAST_DAILY |
            WeatherEntityFeature.FORECAST_HOURLY
        )

    # --- 当前天气核心数据 (映射自 coordinator.py 新结构) ---

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
    def wind_bearing(self) -> float | None:
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

    # --- 预报数据直接返回 ---

    async def async_forecast_daily(self) -> list[Forecast] | None:
        return self.coordinator.data.get("daily")

    async def async_forecast_hourly(self) -> list[Forecast] | None:
        return self.coordinator.data.get("hourly")

    # --- 扩展属性：这里是重点更新部分 ---

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        if not data:
            return {}

        now = data.get("now", {})

        # 基础属性
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

        # 复杂对象数据
        if aqi := data.get("aqi"):
            attrs["aqi"] = aqi
        if warnings := data.get("warning"):
            attrs["warning"] = warnings
        if indices := data.get("indices"):
            attrs["suggestion"] = indices

        # 自定义 UI 标志
        if self.coordinator.entry.options.get(CONF_CUSTOM_UI):
            attrs["custom_ui_more_info"] = "qweather-more-info"

        return attrs