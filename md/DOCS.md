# Documentation (Usage Guide)

## ⚙️ Configuration

### 1. Obtain QWeather Credentials

Go to the QWeather Console:

- Standard Mode: Obtain a regular API KEY.
- JWT Mode (Recommended): Add a JSON Web Token credential to your project.
- Obtain the API host (your personal API service address).

### Step 2: Add the Integration in Home Assistant

1. Go to Settings → Devices & Services → Add Integration.
2. Search for and select QWeather Pro.
3. Fill in the following basic information:
   - API server address: `API host`
   - Location: automatically uses HA’s default latitude/longitude (WGS‑84 supported)
   - Standard API key
4. If you choose JWT authentication, the integration will automatically generate a Public Key:
   - Copy this public key
   - Paste it into the credential settings in the QWeather Console
   - Enter the generated Project ID and Key ID in Home Assistant to complete the binding

### 📈 Frontend Display

Frontend resources are registered only when enabled. Open the integration’s **Options** and turn on **“启用自定义前端 UI 支持”** (`custom_ui`) to register the dashboard card, and **“覆盖原生详情弹窗”** (`custom_more_info`) to replace the native popup. After enabling, restart Home Assistant.  
You only need to add the card in your Lovelace dashboard:

```yaml
type: custom:qweather-pro-card
entity: weather.qweather_pro_<城市名>_weather  # Default entity ID (<城市名> = city selected when adding the integration)

```

### Optional Configuration (UI Options)

#### Click “Options” on the integration page to adjust in real time:

- Update Interval: 5–1440 minutes
- Daily Forecast Days: 3 / 7 / 10 days (V1 API limit)
- Hourly Forecast Hours: 24 / 72 / 168 hours
- Enable Custom UI Support: choose whether to enable the professional weather card (main card).
- Replace native detail popup: choose whether to replace the native Home Assistant more-info popup with the professional detail popup.

### 🛠️ Sensor List

## QWeather Entity Description

| **Entity ID** | **Name** | **Description** |
|---------------|----------|-----------------|
| `weather.qweather_pro_<城市名>_weather` | Weather | Main weather entity. State is the current condition and temperature. Supports `forecast_daily`, `forecast_hourly` and `forecast_twice_daily`. Attributes include `qweather_icon`, `update_time`, `condition_cn`, `feels_like`, `humidity`, `wind_dir`/`wind_scale`/`wind_gust`, `precip`/`precip_type`/`precip_intensity`, `pressure`, `visibility`, `dew`, `cloud`, sunrise/sunset & moon phase times, day/night wind & text (`wind_scale_day`/`wind_dir_day`/`text_night`/`icon_night`), `minutely_summary`, `precip_probability`; when “Replace native detail popup” is on, also `custom_ui_more_info`. |
| `sensor.qweather_pro_<城市名>_aqi` | Air Quality | State is the air‑quality **category** (e.g. 优 / 良 / 轻度污染 / 中度污染). Attributes include the numeric `aqi_value`, `aqi_level`, `primary_pollutant`, pollutant concentrations with units (PM2.5, PM10, SO₂, NO₂, O₃, CO) and health guidance (`health_effect`, `health_advice`) |
| `sensor.qweather_pro_<城市名>_precipitation_summary` | Precipitation Forecast | Minute‑level precipitation trend summary, e.g., “No precipitation in the next two hours” |
| `sensor.qweather_pro_<城市名>_weather_summary` | Weather Briefing | State is tonight’s weather abstract text (`tonight_text`), e.g. “今夜多云”. Attributes contain the full smart abstract (`weather_abstract`: period, temp change, current temp, wind status, etc.) |
| `sensor.qweather_pro_<城市名>_current_temperature` | Real-time Temperature | Numeric temperature sensor (unit °C, `device_class: temperature`). Supports long-term statistics and history graphs. Attributes include `temp_range` (today’s high/low), `max_temp`, `min_temp`, `feels_like`, and `dew_point` |
| `sensor.qweather_pro_<城市名>_current_humidity` | Real-time Humidity | Numeric relative humidity sensor (unit %, `device_class: humidity`). Provides current ambient humidity |
| `sensor.qweather_pro_<城市名>_warning_info` | Weather Warnings | State is the title of the active warning (first alert’s `headline`), e.g. “暴雨橙色预警”; `without_warning` when none. Attributes contain the full warning detail (id, sender, issued time, type, level, color, text, instruction) |

