# Documentation (Usage Guide)

Applies to QWeather Pro 2.0.0 and later. Minimum Home Assistant version: **2026.9.0**.

## Configuration Model

2.0.0 uses the 1.3.x subentry structure as its only structure:

- One **account entry** stores the API Host and credentials only.
- Each city is a **location subentry** under that account, with its own forecast steps, refresh interval and UI switches.
- Credentials are entered once. Add more cities from the account entry page; edit each city through its Configure dialog.
- Account credentials are changed with **Reconfigure** on the account entry; location options are changed with **Configure** on the subentry.

## ⚙️ Configuration

### 1. Obtain QWeather Credentials

Go to the [QWeather Console](https://console.qweather.com):

- **JWT (recommended and default):** add a JSON Web Token credential to your project.
  - Project ID and Key ID: shown on the detail page of the corresponding project.
  - Developer ID (Iss): check under **Console > Settings** — a 10-character alphanumeric string starting with "Q".
- **API KEY:** obtain a regular API KEY. Keep in mind that QWeather will restrict API KEY requests and SDK 5+ drops support for it; the integration therefore forces a 100-minute refresh interval in this mode.
- Obtain your personal **API Host**.

### 2. Add the Account and First Location

1. Go to **Settings > Devices & Services > Add Integration** and search for **QWeather Pro**.
2. Fill in:
   - **API server address (Host):** your personal API Host.
   - **Location:** defaults to the HA latitude/longitude; a city name, city ID (China only) or `longitude,latitude` also works.
   - **Use JWT:** enabled by default. Disable it only for API KEY authentication.
   - **API KEY:** required when JWT is disabled.
3. In JWT mode, the next step displays the generated **public key** and its SHA256 fingerprint:
   - Copy the public key into the JWT credential settings in the QWeather Console.
   - Enter the Project ID, Key ID and Developer ID (Iss) in Home Assistant.
   - The private key is generated and stored locally; only the public key is shown.
4. Choose the city from the search results. This creates the account entry and its first location subentry.

### 3. Add or Edit Location Subentries

- Open the QWeather Pro entry in **Settings > Devices & Services**, then use the location subentry control to add another city. Search and select from the results; a duplicate location is rejected.
- Open a location subentry and choose **Configure** to change:
  - Refresh interval, 5–1440 minutes (JWT only; API KEY is fixed at 100 minutes and has no control).
  - Daily forecast steps: 3, 7 or 10 days.
  - Hourly forecast steps: 24, 72 or 168 hours.
  - Enable custom UI support (`custom_ui`).
  - Override the native more-info dialog (`custom_more_info`).
- A location itself cannot be edited. To change the city, delete the subentry and add it again.

### 4. Reconfigure the Account (Main Entry)

Open the QWeather Pro account entry in **Settings > Devices & Services** and choose **Reconfigure** to change account-level settings. The location is **not** changed here; edit location options through **Configure** on the corresponding subentry.

Changeable settings:

- **API server address (Host):** switch to a different personal API Host.
- **Authentication method:** switch between JWT and API KEY.
  - Switching to JWT when a key pair already exists offers **Keep current configuration (reuse key pair)** (reuse the existing Project ID, Key ID, Developer ID (Iss) and private key with no console changes) or **Regenerate JWT (new key pair)** (copy the new public key into the QWeather Console).
  - Switching to JWT for the first time from API KEY generates a new key pair and walks through the JWT setup.
  - Switching back to API KEY automatically clears the stored JWT credentials so no old private key remains.
- **API KEY:** required when JWT is disabled; the refresh interval is locked to 100 minutes in this mode.

On submit, the integration validates the credentials using the coordinates of the **first location subentry**; the change applies to **all locations** under the account and triggers an automatic reload. If JWT authentication fails, you are guided to re-enter the JWT parameters.

## 📈 Frontend Display

Frontend resources are registered only when at least one location enables `custom_ui` or `custom_more_info`. After enabling a switch, follow any Home Assistant prompt to reload or restart, then add the card to a Lovelace dashboard:

```yaml
type: custom:qweather-pro-card
entity: weather.qweather_pro_<city>_weather
```

Replace `<city>` with the entity ID created for that location. The card supports list and chart styles, a 7-day / 24-hour toggle, and mouse-wheel zoom plus panning on the hourly chart.

## Weather Data Service

Use `qweather_pro.get_weather` to fetch the full dataset from a weather entity, device or area through Developer Tools > Actions. Pass `keys` to limit the response to specific blocks:

```yaml
action: qweather_pro.get_weather
target:
  entity_id: weather.qweather_pro_<city>_weather
data:
  keys:
    - aqi
    - warning
```

Supported keys: `city`, `now`, `daily`, `hourly`, `aqi`, `warning`, `indices`, `weather_abstract`, `minutely_detail`, `minutely_summary`, `update_time`, `attributions`. Omit `keys` to return everything.

## Upgrading from 1.x

**[ACTION REQUIRED]** 1.2.x cannot jump directly to 2.0.0.

| From -> To | Result |
|---|---|
| 1.3.x -> 2.0.0 | Direct upgrade on HA 2026.9.0+ |
| 1.2.x -> 1.3.x | Automatic migration to account + location subentries |
| 1.2.x -> 2.0.0 | Not supported; install 1.3.x first |
| 1.3.x+ -> 1.2.x | Not supported; v2 data cannot be downgraded |

If a v1 entry is loaded by 2.0.0, setup fails and a persistent Repairs issue explains the required two-step upgrade.
