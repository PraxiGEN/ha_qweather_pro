## Release Notes: QWeather Pro 2026

### 🛠 [1.2.6] - 2026-08-31

First stable release built on the 1.2.0-beta series. This release resolves all blockers raised in the HACS review (coordinator stale-data, missing reauth, global JS injection) and introduces JWT auth plus a fully rewritten zero-dependency SVG card.

### 📣 User-Facing Changes (Setup & Reconfigure)
- **JWT is now the default authentication:** New setups and reconfigures default to JWT (Ed25519). The API Key method now enforces a restricted request rate (locked refresh interval), and the integration raises a persistent Repairs issue to nudge API-Key users to migrate to JWT.
- **JWT now has a Developer ID (Project ID / project_id) field:** Because QWeather's review is currently lenient, this field isn't strictly enforced server-side yet — but to avoid errors once enforcement tightens, please complete the Developer ID in "Reconfigure" (along with Key ID and Issuer).
- **Weather entity attributes trimmed; new data query service:** Weather entity attributes have been streamlined. Use the new `qweather_pro.get_weather` service to fetch the full dataset (current conditions, hourly/daily forecasts, AQI, warnings, life indices, etc.), with optional `keys` filtering.

### ⚠️ Breaking Changes (Action Required for Users)
1. **Lovelace resource injection is now Opt-in (dual switches):** The integration no longer unconditionally injects card/more-info/i18n JS resources into the HA frontend. Two new independent toggles have been added to the integration options:
- **Enable Custom Frontend UI Support (custom_ui):** Registers the custom main card. Default is OFF.
- **Override Native More-Info Dialog (custom_more_info):** Replaces the native popup with a custom detailed card. Default is OFF.
- **Note:** Existing users of custom cards/popups **must manually enable** these switches after upgrading, otherwise the frontend will revert to the native UI.
2. **Real-time temperature sensor renaming:** The `temp_range` sensor has been renamed to the numerical `current_temperature` (entity registry will be rebuilt).

### ✨ Core New Features
- **Frontend card rewritten with zero-dependency native SVG:** (Major change, `qweather-pro-card.js` +814 lines, reduced from an 871KB ApexCharts global bundle to ~32KB native SVG):
- Completely eliminates global JS conflicts with other ecosystem cards like `apexcharts-card` (root cause of issue #61).
- Supports both **List** and **Chart** styles; hourly forecast charts now support mouse-wheel zooming and horizontal panning with a reset redraw button.
- Synchronized rewrite of `qweather-pro-i18n.js` and `qweather-pro-more-info.js` (dynamic i18n reading, eliminated loading race conditions).
- **JWT (Ed25519) Authentication System:** `config_flow.py` adds `jwt_setup`, `reauth_jwt`, and `reconfigure` flows. Key pairs are generated once with the private key stored in the database. Public keys are deterministically derived for display with SHA256 fingerprint verification.
- **Reauth flow implemented:** The coordinator now throws `ConfigEntryAuthFailed` on 401/403 errors → automatically triggers re-authentication instead of silently serving stale data.
- **Enhanced Data Entities:** Added `current_humidity` real-time sensor; weather entities now expose `wind_gust`, `precip_type`, `precip_intensity`, etc.; daily forecasts now include `precipitation_type`.
- **New Service:** Added `qweather_pro.get_weather` service (`services.py` +168, `services.yaml` +31).
- **Diagnostics Redaction:** (`diagnostics.py` +37) API Keys, Private Keys, and Project IDs are now masked in diagnostic exports.

### 🐛 Coordinator Hardening (HACS Review Blocker Fixes)
- **Coordinator rewrite (+596):** Correctly raises `UpdateFailed` when all fetches fail → sets `last_update_success=False` and marks entities as `unavailable`. It no longer returns or perpetually serves "yesterday's data." `update_time` is only updated on successful paths to avoid "stale data looking healthy."
- **API KEY Enforcement:** Strictly locks the refresh interval to 100 minutes in API KEY mode, ignoring manual user overrides to ensure compliance.

### 🔧 Config Flow / Compliance Fixes
- **Translation Schema Compliance:** JWT help text is now inlined into descriptions; dynamic public key blocks use the `{key_block}` runtime placeholder (fixes `hassfest` "not a valid option" errors).
- **Manifest Updates:** Correctly declared `tenacity>=9.1.2` (as `tenacity` was removed from HA Core dependencies in 2026.1); added `after_dependencies: ["frontend"]`.
- **Flow Logic Fixes:** Corrected `reconfigure` termination reason to `reconfigure_successful`; `async_init` no longer erroneously passes `entry.data`, which previously caused flows to end prematurely.
- **Cleanup:** Removed unused `async_get_translations` dead import in `config_flow.py` (PR #86).

### 🌐 Translations & Documentation (HACS Review Response)
- **Comprehensive Translation Coverage:** 12 languages updated (+400 lines per language) covering JWT keys, SVG style keys, humidity, and alert field orders.
- **README/DOCS Corrections:** Fact-checked SVG claims; corrected card type to `custom:qweather-pro-card` (the previously documented `qweather-card` did not exist); aligned entity tables for `warning_info` with actual code.
- **LICENSE Update:** Added MIT attribution for original author `dscao` (Main copyright line remains `Copyright (c) 2026 PraxiGEN`, added `Based on dscao/qweather ... used under MIT`, PR #86). The LICENSE file format was also corrected so GitHub detects it as `MIT` (it had briefly shown `NOASSERTION` due to an inserted attribution line breaking Licensee's match).
- **Brand Cleanup:** Deleted non-ASCII backup file `logo备.png` (183KB).

### 🧪 Testing & CI
- **Test Relocation:** Moved tests to the repository root `/tests` (following the `ludeeus` layout) to ensure they are not packaged by HACS.
- **New CI Workflows:** Added `pytest` workflow (`tests.yml`), `pr-validate`, and `hassfest` validation; `stale.yml` added to automatically close inactive issues.
- **Expanded Coverage:** Added 11 new test modules (`config_flow`, `weather`, `sensor`, `coordinator`, `services`, `diagnostics`, etc.) covering JWT, reconfigure logic, the coordinator, and sensors.

### 📊 File Statistics
49 file changes, +7903 / −1788:
- **Major Rewrites:** `coordinator.py` (+596), `config_flow.py` (+374), `www/qweather-pro-card.js` (+814), `weather.py` (+313), `translations/*` (12×~404).
- **New Files:** `services.py`, `services.yaml`, `diagnostics.py`, `tests/*` (11), `pytest.ini`, `conftest.py`.
- **Cleanups:** Deleted `brand/logo备.png`, significantly reduced card bundle size.

### 🛠 [1.2.0-beta.5] - 2026-08-24

### ⚠️ Breaking Changes
- **Lovelace resource injection is now opt-in:** The integration no longer registers its frontend resources (card / more-info / i18n) into every Home Assistant frontend unconditionally. Two independent switches were added under the integration options:
  - `启用自定义前端 UI 支持` (custom_ui): registers the custom main card. **Off by default.**
  - `覆盖原生详情弹窗` (custom_more_info): replaces the native entity detail popup with the custom more-info card. **Off by default.**
  - Any user already relying on the custom card or custom more-info popup must enable the corresponding switch after upgrading, otherwise the frontend falls back to the native UI.

### ✨ New Features
- Added a new `current_humidity` sensor entity reporting the current relative humidity (%).

### 🐛 Bug Fixes
- Translated the `precip_type` state values (rain / snow / ice / mixed / none / unknown) in all 12 languages, so the weather entity's precipitation-type attribute now shows a localized label instead of the raw code.
- Fixed the custom card occasionally rendering raw translation keys instead of localized text. The card now reads the i18n bundle dynamically and repaints once ready, removing the load-order race.
- Fixed the chart reset button switching the X axis to numeric indices (0,1,2…) instead of weekday/time labels; reset now rebuilds the chart.
- Fixed the forecast chart not filling the card width with few data points by switching to a numeric axis so data always spans edge to edge.

### 🔧 Card / Chart Enhancements
- Hourly forecast chart now supports mouse-wheel zoom and left/right pan, with a default 10-hour window and a custom reset button.

### 🛠 [1.2.0-beta.4] - 2026-08-23

### 🐛 Bug Fixes
- Fixed a `TypeError: async_update_listeners() missing 1 required positional argument: 'forecast_types'` that was raised on every coordinator update. The call now passes `None` (refresh all forecast types), as required by Home Assistant since 2024.4.

### ✨ Newly Exposed Entity Attributes
- Weather entity now exposes previously unexposed current-condition fields: `wind_gust` (gust wind speed, km/h), `precip_type` (rain/snow/none), and `precip_intensity` (precipitation intensity).
- Daily forecast entries now include `precipitation_type`, matching the hourly forecast.
- Added 14 astronomical/lunar time fields to the weather entity attributes (all in local HH:MM): `sunrise`, `sunset`, `astronomical_dawn`, `nautical_dawn`, `civil_dawn`, `astronomical_dusk`, `nautical_dusk`, `civil_dusk`, `solar_noon`, `solar_midnight`, `moonrise`, `moonset`, `moon_transit`, `moon_underfoot`.
- The `current_temperature` sensor now exposes `temp_avg` (daily average temperature).

### 🌐 Translations
- Added i18n name keys for all newly exposed fields across the 12 supported languages.

### 🛠 [1.2.0-beta.3] - 2026-08-19

### 🐛 Bug Fixes
- Fixed humidity (and other percentage fields) showing long floating-point artifacts such as `57.99999999999999%`. Percent values are now rounded to integers.
- Removed the invalid `color_name` field from severe-weather-warning attributes, as the V1 API does not return it.
- Slimmed `manifest.json` requirements to only `tenacity>=9.1.4` (minimum version constraint). `aiohttp` / `cryptography` / `PyJWT` are built into Home Assistant core and no longer need explicit declaration.

### 🛠 [1.2.0-beta.2] - 2026-08-16

### ⚠️ Breaking Changes
- **API migration (V7 → V1):** The data layer has been fully migrated from QWeather V7 API to the **V1 API**. The coordinator parsers were rewritten around V1’s `daytime` / `nighttime` nested structure, with a new primary/backup data‑source fallback. Any custom template or automation that relied on the old V7 field mapping must be re‑checked.
- **Weather entity attribute changes:** Forecast and current‑condition attributes were reorganized to match the V1 schema.
  - Daily forecast is now day/night nested: new keys such as `wind_scale_day` / `wind_dir_day` / `wind_scale_night` / `wind_dir_night`, `icon_night` / `text_night` / `condition_night`, and `wind_360_*`; wind direction is now expressed as `wind_degree` (degrees) / `wind_compass` (cardinal).
  - Current‑condition extra attributes were reshuffled per V1: `wind_dir`, `wind_scale`, `forecast_cloud`, `moon_phase`, etc.; the legacy `obsTime` observation timestamp was removed and is now covered by `update_time`.
  - Any template/automation/third‑party card that referenced the old (V7 flat) attribute keys will now read `unknown` — please switch to the new keys.
- **Temperature sensor entity renamed:** `sensor.qweather_today_temp_range` → `sensor.qweather_current_temperature`. It is now a **numeric** temperature sensor (`device_class: temperature`, `state_class: measurement`, unit °C) instead of a string. The old string state `12°C/25°C` is replaced by a numeric state plus attributes `temp_range` (today’s high/low), `max_temp`, `min_temp`, `feels_like`, and `dew_point`. Any template/automation referencing the old entity id or the old string state must be updated.

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

