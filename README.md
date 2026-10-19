<div align="right">
  <strong>English</strong> | <a href="./README_CN.md">中文版</a>
</div>

# <img src="custom_components/qweather_pro/brand/icon.png" width="64"> QWeather Pro for Home Assistant

[![Release](https://img.shields.io/github/v/release/PraxiGEN/ha_qweather_pro)](https://github.com/PraxiGEN/ha_qweather_pro/releases)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/PraxiGEN/ha_qweather_pro/blob/main/LICENSE)
[![HACS](https://img.shields.io/badge/HACS-Default-blue.svg)](https://github.com/hacs/integration)
![](https://komarev.com/ghpvc/?username=PraxiGEN&color=ff69b4)

## A deeply customized advanced QWeather (HeWeather) integration for Home Assistant.  
Rebuilt using the latest 2026 development standards, delivering not only highly accurate meteorological data but also ultra-fast native SVG weather cards and professional-grade detail popups.

## ✨ Core Features

- 🛡️ **Security First**  
  - Supports QWeather’s latest JWT (EdDSA) authentication.  
  - Automatically generates local Ed25519 key pairs to protect your API quota from unauthorized use.

- ⚡ **Extreme Performance**
  - **Backend:** Powered by DataUpdateCoordinator with concurrent requests and smart caching to minimize API usage.
  - **Frontend:** Renders temperature trend curves with native SVG for fast, dependency-free charts.

- 📊 **Deep Data**
  - **Minutely precipitation:** Native API-driven minute-level precipitation summary (e.g., “No precipitation in the next two hours”).
  - **Weather summary:** Logically synthesized hourly weather trend summary.
  - **Rich sensors:** AQI (with detailed components), today’s temperature range, active weather alert (title text), weather summary, and more.

- 🎨 **Professional Visuals**
  - **Dashboard card:** Faithfully recreates the look of premium weather apps, supporting 7-day and 24-hour forecast switching.
  - **Custom detail popup:** When enabled, replaces HA’s default popup with lifestyle indices, alert details, and more.

- 🔄 **Latest Standards**  
  - Fully compatible with HA 2026.1+ WebSocket forecast subscription for long-term smooth operation.

## 🌍 Internationalization & Multi-language Support (i18n)

QWeather Pro  internationalized, providing a seamless localized experience for users worldwide.

- **Automatic Language Sync**: The integration automatically detects your Home Assistant system language (Settings -> System -> General) and requests weather data in the matching language (supporting 30+ languages).
- **Smart Fallback Mechanism**:
  - **Core Weather/Alerts/AQI**: Supports all 30+ languages provided by QWeather API (e.g., German, French, Japanese, etc.).
  - **Minutely Precipitation & Life Indices**: Due to API constraints, these specific fields will automatically fallback to **English** if the system language is not Chinese, ensuring stable data delivery.
- **Localized Titles & IDs**: During the setup flow, the integration fetches and locks the city name based on your current language (e.g., "BeiJing" in Chinese or "BeiJing" in English), generating clean, localized Entity IDs.

## 📦 Installation

### Using [HACS](https://hacs.xyz/) (Recommended)

 One-click installation from HACS: 

[![Open your Home Assistant instance and open the QWeather Pro inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=PraxiGEN&repository=ha_qweather_pro&category=integration)

**Or manually:**

1. Open Home Assistant
2. Go to HACS
3. In the search box, type **"QWeather Pro"**
4. Click "Download"

### Manual Installation

1. Download the latest release:  
```yaml
https://github.com/PraxiGEN/ha_qweather_pro
```
2. Extract and place `custom_components/qweather_pro` into your Home Assistant `custom_components` directory.
3. Restart Home Assistant.

## 📖 Documentation Navigation

- [🚀 Detailed Configuration & Usage Guide (DOCS.md)](md/DOCS.md)
- [📜 Changelog (CHANGELOG.md)](md/CHANGELOG.md)

## Special Thanks

This update was optimized with AI assistance and deeply refactored based on the original project:  
[dscao/qweather](https://github.com/dscao/qweather)

## 📜 Disclaimer

- This project is not officially affiliated with QWeather.  
- Meteorological data is provided by **QWeather**.  
- Please comply with QWeather’s API usage policies.

## 🤝 Contributing

Contributions are welcome!

1. Submit **Issues** for bug reports or feature requests  
2. Submit **Pull Requests** to contribute code  
3. Join discussions to share ideas or suggestions

## 📄 License

This project is open-sourced under the **MIT License**.  
See the LICENSE file for details.

## ❤️ Support

If this project helps you, please consider giving it a ⭐!

---

## Compatible Version: 

- **Home Assistant 2026.1+**

  The minimum supported version of this integration is Home Assistant 2026.1 or later.

  To ensure brand icons display correctly, it is recommended to use Home Assistant 2026.3 or later.
  Starting from 2026.3, Home Assistant introduced the custom_integrations directory and the Brands Proxy API, allowing custom integrations to include brand images directly within their own component folders.