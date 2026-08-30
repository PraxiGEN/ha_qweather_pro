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
entity: weather.qweather_pro_area_weather  # Default entity ID

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
| `sensor.qweather_pro_aqi` | Air Quality | Provides AQI value and level (e.g., Excellent / Good / Light Pollution). Attributes include PM2.5, PM10, CO, NO₂, O₃, and other pollutant details |
| `sensor.qweather_pro_precipitation_summary` | Precipitation Summary | Minute‑level precipitation trend summary, e.g., “No precipitation in the next two hours” |
| `sensor.qweather_pro_weather_summary` | Weather Summary | 6‑hour weather trend summary, e.g., “Next 6 hours: blowing sand” |
| `sensor.qweather_pro_current_temperature` | Real-time Temperature | Numeric temperature sensor (unit °C, `device_class: temperature`). Supports long-term statistics and history graphs. Attributes include `temp_range` (today’s high/low), `max_temp`, `min_temp`, `feels_like`, and `dew_point` |
| `sensor.qweather_pro_current_humidity` | Real-time Humidity | Numeric relative humidity sensor (unit %, `device_class: humidity`). Provides current ambient humidity |
| `sensor.qweather_pro_warning_count` | Weather Warning Count | Number of active weather alerts (e.g., typhoon, heavy rain, strong wind) |

