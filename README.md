<div align="right">
  <strong>English</strong> | <a href="./README_CN.md">中文版</a>
</div>

# <img src="custom_components/qweather_pro/brand/icon.png" width="64"> QWeather Pro for Home Assistant

[![Release](https://img.shields.io/github/v/release/PraxiGEN/ha_qweather_pro)](https://github.com/PraxiGEN/ha_qweather_pro/releases)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/PraxiGEN/ha_qweather_pro/blob/main/LICENSE)
[![Marketplace](https://img.shields.io/badge/Marketplace-Available-blue.svg)](https://www.hacs.xyz/docs/marketplace/)

## A deeply customized advanced QWeather (HeWeather) integration for Home Assistant.

Uses a one-account-entry architecture with one location subentry per city, plus JWT (EdDSA) authentication and a zero-dependency native SVG weather card.

## ✨ Core Features

### Architecture

- The account entry stores credentials only; each city is a location subentry.
- Forecast steps, refresh interval and custom UI switches are set in each location subentry's **Configure** dialog.
- Adding another city does not repeat credential setup.

### Security

- JWT (EdDSA) authentication is enabled by default.
- An Ed25519 key pair is generated locally and only the private key is stored, protecting your API quota from unauthorized use.

### Performance

- Backend: DataUpdateCoordinator with concurrent requests and smart caching to minimize API usage.
- Frontend: temperature trend curves rendered with native SVG, no chart library required.

### Data

- Minutely precipitation: native API-driven precipitation summary (e.g. "No precipitation in the next two hours").
- Weather summary: logically synthesized hourly weather trend summary.
- Rich sensors: AQI with detailed components, today's temperature range, active alert title, weather summary and more.

### Visuals

- Dashboard card: recreates the look of premium weather apps, with 7-day and 24-hour forecast switching.
- Optional detail popup: when enabled on a location, replaces HA's native more-info dialog with lifestyle indices and full alert details.

### i18n

- System language is synced to the QWeather API (30+ languages); minutely precipitation and life indices use the documented fallback.

## 📦 Installation

### Via Marketplace (Recommended)

> Since Home Assistant **2026.11**, HACS is built in as the system **Marketplace** at **Settings > Marketplace**. No separate HACS installation is required.

[![Open QWeather Pro in Home Assistant Marketplace.](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=PraxiGEN&repository=ha_qweather_pro&category=integration)

Or manually:

1. Open Home Assistant and go to **Settings > Marketplace**.
2. Search for **QWeather Pro**.
3. Open the detail page and click **Install**.
4. Go to **Settings > Devices & Services > Add Integration**, search for **QWeather Pro**, and complete the setup wizard.

> Restart Home Assistant only if prompted after installation or update.

### Manual Installation

1. Download the latest release:

```yaml
https://github.com/PraxiGEN/ha_qweather_pro
```

2. Extract and place `custom_components/qweather_pro` into the Home Assistant `custom_components` directory.
3. Restart Home Assistant.
4. Go to **Settings > Devices & Services > Add Integration**, search for **QWeather Pro**, and add it.

## 📖 Documentation Navigation

- [Detailed Configuration & Usage Guide (DOCS.md)](md/DOCS.md)
- [Release Notes (CHANGELOG.md)](md/CHANGELOG.md)

## Special Thanks

This project was optimized with AI assistance and deeply refactored from the original project:
[dscao/qweather](https://github.com/dscao/qweather)

## 📜 Disclaimer

- This project is not officially affiliated with QWeather.
- Meteorological data is provided by QWeather.
- Please comply with QWeather's API usage policies.

## 🤝 Contributing

Contributions are welcome.

1. Submit issues for bug reports or feature requests.
2. Submit pull requests to contribute code.
3. Join discussions to share ideas or suggestions.

## 📄 License

This project is open-sourced under the MIT License. See the LICENSE file for details.

## ❤️ Support

If this project helps you, please consider giving it a star.

---

## Compatible Version

- **Home Assistant 2026.9.0+**
  The minimum supported version is Home Assistant 2026.9.0, using native subentry APIs and probatio schemas.

> **[ACTION REQUIRED]** 1.2.x cannot jump directly to 2.0.0. Upgrade to 1.3.x first so automatic migration can complete, then upgrade to 2.0.0; 2.0.0 no longer includes the v1 migration layer.
