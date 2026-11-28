## Release Notes: QWeather Pro 2026

<!-- Update rule: this file is only updated for substantial feature releases (feat/minor); patch versions are not listed here and are covered by GitHub Releases generated notes. -->

### 🛠 v2.0.0 - Lean Architecture and Minimum HA 2026.9.0

This is the **first release of the 2.x line**: the 1.x migration layer is removed, only the subentry architecture introduced in 1.3.x is kept, and the minimum Home Assistant version is raised to 2026.9.0. This is a removal-only release; no new user-facing features were added.

> ⚠️ **Breaking changes (read before upgrading)**
>
> - **Upgrading below 2026.9.0 is not supported**: the minimum supported version is Home Assistant 2026.9.0, enforced by HACS at the marketplace level; do not manually replace files on older versions.
> - **No direct upgrade from 1.2.x**: the v1 -> v2 migration layer has been removed. 1.2.x users must upgrade to 1.3.x first to complete automatic migration, then upgrade to 2.0.0.
> - **v1 entries are rejected**: if 2.0.0 loads an unmigrated v1 entry, setup fails and a persistent `legacy_entry` Repairs issue points to the upgrade path below.
> - **No downgrade**: v2 entry data from 1.3.x / 2.0.x cannot be downgraded to 1.2.x.

#### ⚠️ Upgrade path

| From -> To | Result |
|---|---|
| 1.3.x -> 2.0.0 | Direct upgrade on HA 2026.9.0+ |
| 1.2.x -> 1.3.x | Automatic migration to account + location subentries |
| 1.2.x -> 2.0.0 | Not supported; upgrade to 1.3.x first to complete migration, then upgrade to 2.0.0 |
| 1.3.x+ -> 1.2.x | Not supported; v2 entry data cannot be downgraded |

#### 🔧 Key changes

- **Migration layer removed**: automatic v1 entry migration code and compatibility branches deleted; location handling uses native `get_subentries_of_type`.
- **Schema migration**: configuration and service schemas moved from voluptuous to probatio, the HA core validation library; CI dropped the voluptuous dependency.
- **HA API updates**: `async_unload_platforms_or_raise` on HA 2026.11+; `UpdateFailedUnreachable` on HA 2026.12+ (older versions keep fallbacks).
- **Fix**: the successful-reconfigure dialog now uses the integration's own translation on HA 2026.10+, no longer the English Home Assistant fallback text.
- **Metadata**: `hacs.json` no longer declares `render_readme`, keeps `zip_release`; the minimum HA is declared by the marketplace as 2026.9.0.

---

### 🛠 v1.3.0 - Subentry Architecture

The closing release of the 1.x line and the base for 2.0.0.

- One entry = one account (credentials only) plus one location subentry per city. Forecast steps, refresh interval and custom UI options moved to each location subentry.
- Existing entries migrated automatically on first start. Entities, devices and history were preserved; entries sharing a host were merged, preferring JWT credentials.
- Migration was one-way: downgrading to 1.2.x required uninstalling and setting up again.
- Supported HA 2026.1.0+; HA 2026.5.0+ was recommended for native subentry APIs.

---

### 🛠 v1.2.6 - Stable 1.2.x Baseline

First stable release of the 1.2 series, built from the 1.2.0-beta releases.

- Migrated the data layer from QWeather V7 to V1 with `daytime` / `nighttime` nested forecasts and primary/backup host fallback. Templates using old V7 attributes needed updating.
- JWT (EdDSA) became the default authentication; an API KEY was still accepted with a forced 100-minute refresh interval.
- Rewrote the dashboard card as a zero-dependency native SVG bundle, removing global ApexCharts conflicts.
- Frontend resource injection became opt-in through two independent switches: `custom_ui` and `custom_more_info`.
- Renamed the string-based `temp_range` sensor to the numeric `current_temperature`.
- Added the `qweather_pro.get_weather` service, diagnostics redaction, reauthentication flow, persistent weather cache and 12-language translation coverage.

---

### 🛠 v1.1.0 - Full-chain i18n and Resilience

- Synced the HA system language to QWeather API requests (30+ languages), with an English fallback for minutely precipitation and life indices.
- Applied the QWeather personal API Host requirement and adapted the GeoAPI path change.
- Added Tenacity-based retry, a smart degradation mode and cold-start self-healing.
- Normalized city name / city ID / latitude-longitude input to coordinates for all API requests.
- Upgraded AQI and alerts to V1 data, with station-level pollutant details and full alert fields.
- Adopted `ConfigEntry.runtime_data` with PEP 695 type aliases.
