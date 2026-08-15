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
from .const import ATTRIBUTION, CONF_CUSTOM_UI
from .coordinator import QWeatherUpdateCoordinator

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
        """当前紫外线指数 (V1 current 的 uvIndex，降级时回退今日 uvIndexMax)."""
        return self.coordinator.data.get("now", {}).get("uv_index")

    @callback
    def _handle_coordinator_update(self) -> None:
        """coordinator 数据刷新：写入新状态并推送预报订阅者.

        按 HA 官方文档 "Updating weather forecast(s)" 建议：预报缓存失效时
        调用 async_update_listeners，将更新推送给活跃的 forecast 订阅方
        (前端卡片 / weather.get_forecasts 服务)。
        """
        super()._handle_coordinator_update()
        self.hass.async_create_task(self.async_update_listeners())

    # --- 预报数据同步 (键序与 HA 官方 Forecast 字段表一致) ---
    async def async_forecast_daily(self) -> list[Forecast] | None:
        """每日预报 (V1 嵌套结构 → HA Forecast 标准键).

        1 天 1 条、白天视角 (HA 生态惯例)：日级 temp_max/min + daytime 时段数据。
        """
        daily_data = self.coordinator.data.get("daily")
        if not daily_data:
            return None
        return [{
            "datetime": d.get("datetime"),
            "is_daytime": True,
            "cloud_coverage": d.get("daytime", {}).get("cloud"),
            "condition": d.get("daytime", {}).get("condition"),
            "humidity": d.get("daytime", {}).get("humidity"),
            "native_precipitation": d.get("daytime", {}).get("precip_amount"),
            "native_temperature": d.get("temp_max"),
            "native_templow": d.get("temp_min"),
            "native_wind_gust_speed": d.get("daytime", {}).get("wind_gust_max"),
            "native_wind_speed": d.get("daytime", {}).get("wind_speed"),
            "precipitation_probability": d.get("daytime", {}).get("precip_probability"),
            "uv_index": d.get("uv_index_max"),
            "wind_bearing": d.get("daytime", {}).get("wind_degree"),
        } for d in daily_data]

    async def async_forecast_hourly(self) -> list[Forecast] | None:
        """逐小时预报 (V1 hourly → HA Forecast 标准键).

        键序与 hourly API 文档同步：forecastTime → condition → temperature → precipitation.probability。
        """
        hourly_data = self.coordinator.data.get("hourly")
        if not hourly_data:
            return None
        return [{
            # forecastTime
            "datetime": h.get("datetime"),
            # condition
            "condition": h.get("condition"),
            # temperature
            "native_temperature": h.get("native_temperature"),
            # precipitation.probability
            "precipitation_probability": h.get("precipitation_probability"),
        } for h in hourly_data]

    async def async_forecast_twice_daily(self) -> list[Forecast] | None:
        """实现每日两次（昼夜）预报逻辑.

        V1 升级：不再用本地 8 点/20 点平移猜测时段边界，直接取
        daytime/nighttime 时段真实的 forecastStartTime 与各自独立的
        condition/温度区间/风/降水 (is_daytime 标记昼夜)。
        """
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
                    "native_temperature": night.get("temp_min"),
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
        # condition.text (condition 本体由实体 state 覆盖)
        attrs["condition_cn"] = now.get("text_cn")
        # temperature (实体 state 覆盖，无属性)
        # feelsLike
        attrs["feels_like"] = now.get("feelsLike")
        # humidity (实体 state 覆盖，此属性为卡片兼容保留)
        attrs["humidity"] = now.get("humidity")
        # wind: direction.compass / scale (degree/speed 由实体 state 覆盖)
        attrs["wind_dir"] = now.get("windDir")
        attrs["wind_scale"] = now.get("windScale")
        # precipitation.amount
        attrs["precip"] = now.get("precip")
        # pressure (实体 state 覆盖，卡片兼容保留)
        attrs["pressure"] = now.get("pressure")
        # visibility (实体 state 覆盖，卡片兼容保留)
        attrs["visibility"] = now.get("vis")
        # dewPoint
        attrs["dew"] = now.get("dew")
        # cloudCover
        attrs["cloud"] = now.get("cloud")
        # uvIndex (current 无此字段，取自 daily 的 uvIndexMax，见下)

        # ===== 今日预报 (weather-v1-daily 文档序, daily[0]) =====
        if daily:
            today = daily[0]
            astro = today.get("astro", {})
            day_seg = today.get("daytime", {})
            night_seg = today.get("nighttime", {})
            # forecastStartTime (预报 datetime 走 forecast 服务，无属性)
            # astro: sunrise / sunset / moonrise / moonset / moonPhase
            attrs["sunrise"] = astro.get("sunrise")
            attrs["sunset"] = astro.get("sunset")
            attrs["moonrise"] = astro.get("moonrise")
            attrs["moonset"] = astro.get("moonset")
            attrs["moon_phase"] = astro.get("moon_phase")
            # (V1 无 moonPhaseIcon，图标由前端按 moon_phase 推导，属性已剔除)
            # temperatureMax / temperatureMin (预报走 forecast 服务，无属性)
            # uvIndexMax (当前 UV 走实体 uv_index 标准属性；日级最大值走 forecast 服务)
            # daytime: condition (state 白天视角覆盖) / wind / cloudCover
            attrs["wind_scale_day"] = day_seg.get("wind_scale")
            attrs["wind_dir_day"] = day_seg.get("wind_compass")
            attrs["forecast_cloud"] = day_seg.get("cloud")
            # nighttime: condition / wind
            attrs["text_night"] = night_seg.get("text")
            attrs["icon_night"] = night_seg.get("icon")
            attrs["wind_scale_night"] = night_seg.get("wind_scale")
            attrs["wind_dir_night"] = night_seg.get("wind_compass")
            # (V1 每日预报不含 pressure/visibility，forecast_pressure/forecast_vis 死属性已剔除)

        # ===== 临近降水摘要 (weather-v1-minutely) =====
        attrs["minutely_summary"] = data.get("minutely_summary")

        # ===== 逐小时预报首条 (weather-v1-hourly 文档序) =====
        if hourly:
            # precipitation.probability
            attrs["precip_probability"] = hourly[0].get("precipitation_probability")

        # ===== [暂时剔除 2026-08-15] 大块嵌套属性 =====
        # 剔除原因：降低 recorder 落库体积；计划迁移至集成自有服务按需读取
        # (卡片额外数据走服务的方案，见讨论记录)。需要临时恢复时取消注释即可。

        # --- 空气质量 (weather-v1-air-current 文档序) ---
        # if aqi_data := data.get("aqi"):
        #     pollutants = {
        #         "pm2p5": f"{aqi_data.get('pm2p5', '--')} {aqi_data.get('pm2p5_unit', '')}".strip(),
        #         "pm10": f"{aqi_data.get('pm10', '--')} {aqi_data.get('pm10_unit', '')}".strip(),
        #         "no2": f"{aqi_data.get('no2', '--')} {aqi_data.get('no2_unit', '')}".strip(),
        #         "so2": f"{aqi_data.get('so2', '--')} {aqi_data.get('so2_unit', '')}".strip(),
        #         "o3": f"{aqi_data.get('o3', '--')} {aqi_data.get('o3_unit', '')}".strip(),
        #         "co": f"{aqi_data.get('co', '--')} {aqi_data.get('co_unit', '')}".strip(),
        #     }
        #     attrs["aqi"] = {
        #         "aqi": aqi_data.get("aqi"),
        #         "aqi_category": aqi_data.get("category"),
        #         "aqi_level": aqi_data.get("level"),
        #         "primary_pollutant": aqi_data.get("primary"),
        #         "health_effect": aqi_data.get("health_effect"),
        #         "air_quality_advice": aqi_data.get("health_advice"),
        #         "pollutants": pollutants,
        #         "stations": aqi_data.get("stations", []),
        #     }

        # --- 天气摘要 ---
        # if abstract := data.get("weather_abstract"):
        #     attrs["weather_abstract"] = abstract

        # --- 预警信息 (weather-v1-warning-alert 文档序) ---
        # if warnings := data.get("warning"):
        #     attrs["warning"] = warnings

        # --- 生活指数 (weather-v1-indices 文档序) ---
        # if indices := data.get("indices"):
        #     attrs["suggestion"] = indices

        # ===== [卡片兼容] 自定义 UI 触发标志 (Lovelace 卡片) =====
        if self.coordinator.entry.options.get(CONF_CUSTOM_UI):
            attrs["custom_ui_more_info"] = "qweather-pro-more-info"

        return attrs