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
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import QWeatherConfigEntry
from .const import ATTRIBUTION, CONF_CUSTOM_UI, CONF_CUSTOM_MORE_INFO
from .coordinator import QWeatherUpdateCoordinator

# HA 天气平台 WeatherEntity.async_update_listeners(forecast_types) 在 2026.1.0 的签名中
# forecast_types 默认即为 None（传 None 表示刷新 daily/hourly/twice_daily 全部类型）。
# 本项目最低支持 2026.1.0，调用处直接传 None 即可，无需兼容旧签名。

# 定义天气描述符
QWEATHER_WEATHER_DESCRIPTION = WeatherEntityDescription(
    key="weather",
    translation_key="weather",
    icon="mdi:weather-partly-cloudy",
)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: QWeatherConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
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

    def __init__(
        self,
        coordinator: QWeatherUpdateCoordinator,
        entry: QWeatherConfigEntry,
        description: WeatherEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_translation_key = description.translation_key
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
    def native_apparent_temperature(self) -> float | None:
        """体感温度 (和风 API 的 feelsLike)."""
        return self.coordinator.data.get("now", {}).get("feelsLike")

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
    def native_precipitation(self) -> float | None:
        """当前降水强度 (和风 API 的 precip, 单位 mm)."""
        return self.coordinator.data.get("now", {}).get("precip")

    @property
    def cloud_coverage(self) -> float | None:
        return self.coordinator.data.get("now", {}).get("cloud")

    @property
    def uv_index(self) -> float | None:
        """当前紫外线指数."""
        return self.coordinator.data.get("now", {}).get("uv_index")

    @callback
    def _handle_coordinator_update(self) -> None:
        """数据刷新后推送预报订阅者."""
        super()._handle_coordinator_update()
        self.hass.async_create_task(self.async_update_listeners(None))

    async def async_forecast_daily(self) -> list[Forecast] | None:
        """每日预报 (V1 嵌套结构 → 完整 day/night 键集)."""
        daily_data = self.coordinator.data.get("daily")
        if not daily_data:
            return None
        forecasts: list[Forecast] = []
        for d in daily_data:
            day = d.get("daytime", {})
            night = d.get("nighttime", {})
            astro = d.get("astro", {})
            forecasts.append({
                # --- HA 标准字段（默认卡片 / weather.get_forecasts 服务兼容） ---
                "datetime": d.get("datetime"),
                "is_daytime": True,
                "condition": day.get("condition"),
                "native_temperature": d.get("temp_max"),
                "native_templow": d.get("temp_min"),
                "native_wind_speed": day.get("wind_speed"),
                "wind_bearing": day.get("wind_degree"),
                "native_wind_gust_speed": day.get("wind_gust_max"),
                "humidity": day.get("humidity"),
                "cloud_coverage": day.get("cloud"),
                "native_precipitation": day.get("precip_amount"),
                "precipitation_probability": day.get("precip_probability"),
                "precipitation_type": day.get("precip_type"),
                "uv_index": d.get("uv_index_max"),
                "icon": day.get("icon"),
                "icon_night": night.get("icon"),
                "text": day.get("text"),
                "text_night": night.get("text"),
                "condition_night": night.get("condition"),
                "wind_360_day": day.get("wind_degree"),
                "wind_dir_day": day.get("wind_compass"),
                "wind_scale_day": day.get("wind_scale"),
                "wind_speed": day.get("wind_speed"),
                "wind_360_night": night.get("wind_degree"),
                "wind_dir_night": night.get("wind_compass"),
                "wind_scale_night": night.get("wind_scale"),
                "wind_speed_night": night.get("wind_speed"),
                "sunrise": astro.get("sunrise"),
                "sunset": astro.get("sunset"),
                "moonrise": astro.get("moonrise"),
                "moonset": astro.get("moonset"),
                "moon_phase": astro.get("moon_phase"),
                "cloud": day.get("cloud"),
                "temperature": d.get("temp_max"),
                "templow": d.get("temp_min"),
                "precipitation": day.get("precip_amount"),
            })
        return forecasts

    async def async_forecast_hourly(self) -> list[Forecast] | None:
        """逐小时预报 (V1 hourly → HA Forecast 标准键 + 自定义键)."""
        hourly_data = self.coordinator.data.get("hourly")
        if not hourly_data:
            return None
        return [{
            "datetime": h.get("datetime"),
            "condition": h.get("condition"),
            "text": h.get("text"),
            "icon": h.get("icon"),
            "native_temperature": h.get("native_temperature"),
            "native_apparent_temperature": h.get("native_apparent_temperature"),
            "native_humidity": h.get("native_humidity"),
            "native_cloud_coverage": h.get("native_cloud_coverage"),
            "native_wind_bearing": h.get("native_wind_bearing"),
            "wind_compass": h.get("wind_compass"),
            "native_wind_speed": h.get("native_wind_speed"),
            "wind_scale": h.get("wind_scale"),
            "native_wind_gust_speed": h.get("native_wind_gust_speed"),
            "native_precipitation": h.get("native_precipitation"),
            "precipitation_intensity": h.get("precipitation_intensity"),
            "precipitation_type": h.get("precipitation_type"),
            "precipitation_probability": h.get("precipitation_probability"),
            "native_pressure": h.get("native_pressure"),
            "native_visibility": h.get("native_visibility"),
            "native_dew_point": h.get("native_dew_point"),
            "uv_index": h.get("uv_index"),
        } for h in hourly_data]

    async def async_forecast_twice_daily(self) -> list[Forecast] | None:
        """每日两次（昼夜）预报."""
        daily_data = self.coordinator.data.get("daily")
        if not daily_data:
            return None

        twice_daily_forecast: list[Forecast] = []
        for d in daily_data:
            day = d.get("daytime", {})
            night = d.get("nighttime", {})

            if day.get("start"):
                twice_daily_forecast.append({
                    "datetime": day.get("start"),
                    "is_daytime": True,
                    "cloud_coverage": day.get("cloud"),
                    "condition": day.get("condition"),
                    "humidity": day.get("humidity"),
                    "native_precipitation": day.get("precip_amount"),
                    "native_temperature": day.get("temp_max"),
                    "native_templow": day.get("temp_min"),
                    "native_wind_gust_speed": day.get("wind_gust_max"),
                    "native_wind_speed": day.get("wind_speed"),
                    "precipitation_probability": day.get("precip_probability"),
                    "wind_bearing": day.get("wind_degree"),
                })

            if night.get("start"):
                twice_daily_forecast.append({
                    "datetime": night.get("start"),
                    "is_daytime": False,
                    "cloud_coverage": night.get("cloud"),
                    "condition": night.get("condition"),
                    "humidity": night.get("humidity"),
                    "native_precipitation": night.get("precip_amount"),
                    "native_temperature": night.get("temp_max"),
                    "native_templow": night.get("temp_min"),
                    "native_wind_gust_speed": night.get("wind_gust_max"),
                    "native_wind_speed": night.get("wind_speed"),
                    "precipitation_probability": night.get("precip_probability"),
                    "wind_bearing": night.get("wind_degree"),
                })

        return twice_daily_forecast

    # --- 扩展属性 (键序与各 API 文档返回顺序同步，便于对照维护) ---
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        if not data:
            return {}

        now = data.get("now", {})
        daily = data.get("daily", [])
        hourly = data.get("hourly", [])

        # ===== [集成元数据] (API 文档之外的自有字段，统一置顶) =====
        attrs = {
            "attribution": ATTRIBUTION,
            "city": data.get("city"),
            "update_time": data.get("update_time"),
            "qweather_icon": now.get("icon"),
            # (V1 实况无 obsTime 观测时间戳，该属性已剔除，由 update_time 兜底)
        }

        # ===== 实时天气 (weather-v1-current 文档序) =====
        attrs["condition_cn"] = now.get("text_cn")
        attrs["feels_like"] = now.get("feelsLike")
        attrs["humidity"] = now.get("humidity")
        attrs["wind_dir"] = now.get("windDir")
        attrs["wind_scale"] = now.get("windScale")
        attrs["precip"] = now.get("precip")
        attrs["pressure"] = now.get("pressure")
        attrs["visibility"] = now.get("vis")
        attrs["dew"] = now.get("dew")
        attrs["cloud"] = now.get("cloud")
        # 当前阵风 / 降水类型 / 降水强度（V1 current 解析字段，原仅服务可见）
        attrs["wind_gust"] = now.get("windGust")
        attrs["precip_type"] = now.get("precipType")
        attrs["precip_intensity"] = now.get("precipIntensity")

        # ===== 今日预报 (weather-v1-daily 文档序, daily[0]) =====
        if daily:
            today = daily[0]
            astro = today.get("astro", {})
            day_seg = today.get("daytime", {})
            night_seg = today.get("nighttime", {})
            # 天文 / 月相时间（V1 astro，本地 HH:MM）
            attrs["sunrise"] = astro.get("sunrise")
            attrs["sunset"] = astro.get("sunset")
            attrs["astronomical_dawn"] = astro.get("astronomical_dawn")
            attrs["nautical_dawn"] = astro.get("nautical_dawn")
            attrs["civil_dawn"] = astro.get("civil_dawn")
            attrs["astronomical_dusk"] = astro.get("astronomical_dusk")
            attrs["nautical_dusk"] = astro.get("nautical_dusk")
            attrs["civil_dusk"] = astro.get("civil_dusk")
            attrs["solar_noon"] = astro.get("solar_noon")
            attrs["solar_midnight"] = astro.get("solar_midnight")
            attrs["moonrise"] = astro.get("moonrise")
            attrs["moonset"] = astro.get("moonset")
            attrs["moon_transit"] = astro.get("moon_transit")
            attrs["moon_underfoot"] = astro.get("moon_underfoot")
            attrs["moon_phase"] = astro.get("moon_phase")
            attrs["wind_scale_day"] = day_seg.get("wind_scale")
            attrs["wind_dir_day"] = day_seg.get("wind_compass")
            attrs["forecast_cloud"] = day_seg.get("cloud")
            attrs["text_night"] = night_seg.get("text")
            attrs["icon_night"] = night_seg.get("icon")
            attrs["wind_scale_night"] = night_seg.get("wind_scale")
            attrs["wind_dir_night"] = night_seg.get("wind_compass")

        # ===== 临近降水摘要 (weather-v1-minutely) =====
        attrs["minutely_summary"] = data.get("minutely_summary")

        # ===== 逐小时预报首条 (weather-v1-hourly 文档序) =====
        if hourly:
            # precipitation.probability
            attrs["precip_probability"] = hourly[0].get("precipitation_probability")

        # ===== [卡片兼容] 自定义 UI 触发标志 (Lovelace 卡片) =====
        # 仅当「覆盖原生详情弹窗」开关开启时，才让 HA 用自定义 more-info 卡片替换原生弹窗
        if self.coordinator.entry.options.get(CONF_CUSTOM_MORE_INFO):
            attrs["custom_ui_more_info"] = "qweather-pro-more-info"

        return attrs