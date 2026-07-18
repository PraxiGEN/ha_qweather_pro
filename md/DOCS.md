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

The integration automatically registers frontend resources.  
You only need to add the card in your Lovelace dashboard:

```yaml
type: custom:qweather-card
entity: weather.qweather_pro_area_weather  # Default entity ID

```

### Optional Configuration (UI Options)

#### Click “Options” on the integration page to adjust in real time:

- Data update interval: 5–1440 minutes
- Forecast days/hours: compatible with both free and paid API tiers
- Grid weather: enable 1 km high‑precision grid data
- Custom UI support: choose whether to enable the professional detail popup

### 🛠️ Sensor List

## QWeather Entity Description

| **Entity ID** | **Name** | **Description** |
|---------------|----------|-----------------|
| `sensor.qweather_aqi` | Air Quality | Provides AQI value and level (e.g., Excellent / Good / Light Pollution). Attributes include PM2.5, PM10, CO, NO₂, O₃, and other pollutant details |
| `sensor.qweather_precipitation_summary` | Precipitation Summary | Minute‑level precipitation trend summary, e.g., “No precipitation in the next two hours” |
| `sensor.qweather_weather_summary` | Weather Summary | 6‑hour weather trend summary, e.g., “Next 6 hours: blowing sand” |
| `sensor.qweather_today_temp_range` | Today’s Temperature Range | Today’s high/low temperature range, e.g., `12°C / 25°C`. Attributes include `min_temp` and `max_temp` |
| `sensor.qweather_warning_count` | Weather Warning Count | Number of active weather alerts (e.g., typhoon, heavy rain, strong wind) |

