"""QWeather (和风天气) 天气平台实现 ."""
from __future__ import annotations

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
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, ATTRIBUTION, CONF_CUSTOM_UI
from .coordinator import QWeatherUpdateCoordinator

# 定义天气描述符
QWEATHER_WEATHER_DESCRIPTION = WeatherEntityDescription(
    key="weather",
    translation_key="weather",
    icon="mdi:weather-partly-cloudy",
)

async def async_setup_entry(hass, entry, async_add_entities):
    """通过配置条目设置天气实体."""
    coordinator: QWeatherUpdateCoordinator = entry.runtime_data
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
        self._attr_translation_key = description.translation_key

        # 直接引用 coordinator 中定义好的设备信息
        self._attr_device_info = coordinator.device_info
        
        self._attr_supported_features = (
            WeatherEntityFeature.FORECAST_DAILY |
            WeatherEntityFeature.FORECAST_HOURLY |
            WeatherEntityFeature.FORECAST_TWICE_DAILY
        )

    # --- 当前天气核心数据 (映射自 coordinator.py now 字典) ---

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

    # --- 预报数据同步 ---

    async def async_forecast_daily(self) -> list[Forecast] | None:
        return self.coordinator.data.get("daily")

    async def async_forecast_hourly(self) -> list[Forecast] | None:
        return self.coordinator.data.get("hourly")

    async def async_forecast_twice_daily(self) -> list[Forecast] | None:
        """实现每日两次（昼夜）预报逻辑."""
        daily_data = self.coordinator.data.get("daily")
        if not daily_data:
            return None

        twice_daily_forecast = []
        for d in daily_data:
            # 1. 白天预报 (建议设为早上 8 点)
            twice_daily_forecast.append({
                "datetime": d.get("datetime").replace("T00:00:00", "T08:00:00"),
                "native_temperature": d.get("native_temperature"), # 最高温
                "native_templow": d.get("native_templow"),
                "condition": d.get("condition"), # 白天天气
                "is_daytime": True,
            })
            
            # 2. 夜间预报 (建议设为晚上 20 点)
            # 晚上没有 templow，主温 native_temperature 取最低温
            twice_daily_forecast.append({
                "datetime": d.get("datetime").replace("T00:00:00", "T20:00:00"),
                "native_temperature": d.get("native_templow"), # 晚上显示最低温
                "condition": d.get("condition_night"), # 引用夜间天气状况
                "is_daytime": False,
            })
        
        return twice_daily_forecast

    # --- 扩展属性：保留所有原属性并加入新字段 ---

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        if not data:
            return {}

        now = data.get("now", {})
        daily = data.get("daily", [])
        hourly = data.get("hourly", [])

        # 1. 严格保留原所有核心属性 (0 丢失)
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
        }

        # 2. 动态补全最新 API 字段 (从预报中提取今日瞬时值)
        if daily:
            today = daily[0]
            # --- 天文数据 ---
            attrs["sunrise"] = today.get("sunrise")
            attrs["sunset"] = today.get("sunset")
            attrs["moonrise"] = today.get("moonrise")
            attrs["moonset"] = today.get("moonset")
            attrs["moon_phase"] = today.get("moon_phase")
            attrs["moon_phase_icon"] = today.get("moon_phase_icon")
            # --- 昼夜状况 ---
            attrs["text_night"] = today.get("text_night")
            attrs["icon_night"] = today.get("icon_night")
            # --- 风力详情 (昼夜分离) ---
            attrs["wind_scale_day"] = today.get("wind_scale_day")
            attrs["wind_scale_night"] = today.get("wind_scale_night")
            attrs["wind_dir_day"] = today.get("wind_dir_day")
            attrs["wind_dir_night"] = today.get("wind_dir_night")
            # --- 预报类辅助参数 ---
            attrs["uv_index"] = today.get("uv_index")
            attrs["forecast_pressure"] = today.get("pressure")
            attrs["forecast_vis"] = today.get("vis")
            attrs["forecast_cloud"] = today.get("cloud")

        if hourly:
            attrs["precip_probability"] = hourly[0].get("precipitation_probability")

        # 3. 复杂对象并入
        # --- 空气质量 (AQI) 属性优化 ---
        if aqi_data := data.get("aqi"):
            # 将污染物字典重新打包
            pollutants = {
                "pm2p5": f"{aqi_data.get('pm2p5', '--')} {aqi_data.get('pm2p5_unit', '')}".strip(),
                "pm10": f"{aqi_data.get('pm10', '--')} {aqi_data.get('pm10_unit', '')}".strip(),
                "no2": f"{aqi_data.get('no2', '--')} {aqi_data.get('no2_unit', '')}".strip(),
                "so2": f"{aqi_data.get('so2', '--')} {aqi_data.get('so2_unit', '')}".strip(),
                "o3": f"{aqi_data.get('o3', '--')} {aqi_data.get('o3_unit', '')}".strip(),
                "co": f"{aqi_data.get('co', '--')} {aqi_data.get('co_unit', '')}".strip(),
            }

            # 构造符合你要求的 AQI 嵌套对象
            attrs["aqi"] = {
                "aqi": aqi_data.get("aqi"),
                "aqi_category": aqi_data.get("category"),
                "aqi_level": aqi_data.get("level"),
                "primary_pollutant": aqi_data.get("primary"),
                "health_effect": aqi_data.get("health_effect"),
                "air_quality_advice": aqi_data.get("health_advice"),
                "pollutants": pollutants,
                "stations": aqi_data.get("stations",[])
            }
        # --- 预警信息 (Warnings) 属性优化 ---
        if warnings := data.get("warning"):
            attrs["warning"] = warnings
        #--- 生活指数 (Indices) 属性优化 ---
        if indices := data.get("indices"):
            attrs["suggestion"] = indices

        # 4. 自定义 UI 触发标志 (保持对 Lovelace 卡片的兼容)
        if self.coordinator.entry.options.get(CONF_CUSTOM_UI):
            attrs["custom_ui_more_info"] = "qweather-more-info"

        return attrs