## Release Notes: QWeather Pro 2026

### 🛠 [1.2.0-beta.2] - 2026-08-16

### ⚠️ Breaking Changes
- **API migration (V7 → V1):** The data layer has been fully migrated from QWeather V7 API to the **V1 API**. The coordinator parsers were rewritten around V1’s `daytime` / `nighttime` nested structure, with a new primary/backup data‑source fallback. Any custom template or automation that relied on the old V7 field mapping must be re‑checked.
- **Weather entity attribute changes:** Forecast and current‑condition attributes were reorganized to match the V1 schema.
  - Daily forecast is now day/night nested: new keys such as `wind_scale_day` / `wind_dir_day` / `wind_scale_night` / `wind_dir_night`, `icon_night` / `text_night` / `condition_night`, and `wind_360_*`; wind direction is now expressed as `wind_degree` (degrees) / `wind_compass` (cardinal).
  - Current‑condition extra attributes were reshuffled per V1: `wind_dir`, `wind_scale`, `forecast_cloud`, `moon_phase`, etc.; the legacy `obsTime` observation timestamp was removed and is now covered by `update_time`.
  - Any template/automation/third‑party card that referenced the old (V7 flat) attribute keys will now read `unknown` — please switch to the new keys.

### 🔐 Authentication & Quota Strategy
- JWT by default: New setups and re‑configurations now default to JWT, which has no request limit. API KEY stays available but becomes optional.
- API KEY will be capped: From 2027‑01‑01 QWeather limits daily requests for API KEY auth (exact number not yet announced), and SDK 5+ drops API KEY support. JWT is the recommended path.
- Smart migration prompt: If you are still on API KEY, a Repairs (修复) notice appears, guiding you to switch to JWT for unlimited, faster updates.
- Gentler polling on API KEY: When using API KEY, the default refresh interval is slowed to 100 minutes (was 15) to stay safely under the coming limit.

### 💾 Cache That Survives Restarts
- Now uses Home Assistant’s native storage to cache weather data. After a restart the last known data is restored instantly instead of waiting for the next refresh.

### 🔧 On‑Demand Weather Service
- Added a `get_weather` service so the card (and you) can fetch fresh weather data any time. The card already uses it to read AQI and severe weather warnings.

### 🃏 Card Improvements (V1)
- The card now reads AQI and severe weather warnings through the `get_weather` service.
- The more‑info panel shows more V1 fields, including separate day/night conditions.
- Brand names and technical abbreviations are no longer pushed into the translation files — only localizable text is translated.

### 🌐 Translations
- Added the API KEY quota notice to all 12 supported languages.
- Updated all 12 languages for the V1 API changes and new UI strings.

### 🧰 Other
- Added a diagnostics page that exports integration data for troubleshooting.
- Added a re‑authentication flow for credential renewal.
- Rebuilt sensors to adapt to the V1 daily nested structure.
- More‑info dialog now shows wind direction and moon phase with localization.

### 🛠 [1.1.0] - 2026-06-02 (Milestone)

### 🌍 Full‑chain Internationalization (I18N)
- Automatic system language sync: The integration now automatically detects and follows Home Assistant’s system language in real time (supports 30+ global languages).
- Intelligent language fallback: Due to API limitations for “minutely precipitation” and “lifestyle indices”, an automatic fallback mechanism is implemented. When HA is set to a non‑Chinese/English language, these fields will gracefully fall back to English to ensure stable output for global users.
- Conditional entity loading: The Weather Summary entity is now language‑aware. It is only created when the system language is Chinese or English. Switching to other languages and reloading will automatically remove this entity to keep the UI clean and localized.

### 📡 API Host Adaptation (Mandatory from 2026‑06‑01)
- Public domain shutdown compliance: Fully aligned with QWeather’s announcement regarding the shutdown of public domains on June 1, 2026. All hardcoded domains such as `api.qweather.com` have been removed, enforcing the use of personal API Host.
- GeoAPI path restructuring: Automatically adapts to the updated geographic query path changes (v2 → geo/v2). Users only need to enter the Host domain; the integration handles all version path adjustments internally.

### 🛡️ Industrial‑grade Resiliency & Self‑Healing
- Dual‑layer retry protection: Introduces the Tenacity library with exponential backoff retry. For transient network jitter, the system retries silently in the background while keeping the UI smooth and uninterrupted.
- Smart degradation mode (Circuit Breaker): When persistent network failures or API quota exhaustion are detected, the integration automatically reduces the refresh frequency to once per hour to prevent IP blocking due to excessive requests.
- Cold‑start self‑healing: Fixes the long‑standing issue where entities remain “permanently unknown” after HA restarts due to network unavailability. If the initial refresh fails, the integration will retry aggressively until the first valid data is obtained, instead of waiting for long update intervals.

### 📍 Geographic Data Normalization
- Multi‑mode input conversion: The location field now supports “city name”, “city ID”, and “latitude/longitude”. Regardless of what the user enters, the integration automatically standardizes it into precise coordinates during configuration. **"Only supports the Chinese language."**
- Coordinate‑driven API requests: To fully leverage the precision of V1 Alerts and V1 Air Quality APIs (1×1 km resolution), all backend requests are now unified under coordinate‑based queries, eliminating issues caused by city‑ID‑based requests.

### 📊 Platinum‑grade Data Alignment (Professional Data)
- Professional Air Quality (V1): Upgraded AQI API from V7 to V1. Now provides station‑level pollutant concentrations (PM2.5, NO₂, O₃, etc. with units), detailed health impact descriptions, and protection advice for different groups.
- Deep alert parsing: Fully replicates QWeather’s V1 alert protocol, including issuing agency, defense guidelines (Instruction), alert color level, and all extended fields.
- Lossless attribute preservation: Rebuilt the data dictionary to ensure 100% preservation of all 16+ real‑time weather attributes, and added advanced parameters such as Moon Phase, UV Index, and Day/Night conditions.

### 🚀 Architectural Modernization
- Runtime Data & Strong Typing: Fully adopts HA 2026.5’s `ConfigEntry.runtime_data` standard combined with PEP 695 type aliases.

