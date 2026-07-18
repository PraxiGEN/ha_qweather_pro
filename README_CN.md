<div align="right">
  <a href="./README.md">English Version</a> | <strong>中文版</strong>
</div>

# <img src="custom_components/qweather_pro/brand/icon.png" width="64"> 和风天气Pro (QWeather Pro)

[![Release](https://img.shields.io/github/v/release/hzonz/ha_qweather_pro)](https://github.com/hzonz/ha_qweather_pro/releases)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/hzonz/ha_qweather_pro/blob/main/LICENSE)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
![](https://komarev.com/ghpvc/?username=hzonz&color=ff69b4)

## 一款为 Home Assistant 深度定制的 和风天气 (QWeather) 高级集成。采用 2026 年最新开发标准重构，不仅提供精准的气象数据，还包含极速渲染的 原生 SVG 天气卡片 与 专业级详情弹窗。

## ✨ 核心特性

- 🛡️ 安全先行：支持和风天气最新的 JWT (EdDSA) 认证，本地自动生成 Ed25519 密钥对，保护您的 API 额度不被盗用。
- ⚡ 极致性能：
  - 后端：采用 DataUpdateCoordinator 并发请求机制，智能缓存，最大限度节省免费版 API 额度。
  - 前端：完全剔除 Chart.js 等臃肿库，使用 原生 SVG 渲染温度趋势曲线，渲染速度提升 10 倍以上。
- 📊 深度数据：
  - 分钟级降水：API 原生驱动的分钟级降水简报（如：“未来两小时无降水”）。
  - 天气概况：逻辑合成的小时级天气变动简报。
  - 丰富传感器：包含 AQI（含详细参数）、今日温差、预警数量、气象摘要等。
- 🎨 专业视觉：
  - 仪表盘卡片：1:1 复刻专业天气 App 质感，支持 7 日预报与 24 小时预报切换。
  - 自定义详情页：开启后可替换 HA 默认弹窗，显示 8 项生活指数、气象预警详情等丰富信息。
- 🔄 最新标准：完全适配 HA 2024.3+ 的 WebSocket 预报订阅 机制，确保系统长期运行流畅不卡顿。

## 🌍 国际化与多语言支持 (i18n)

QWeather Pro 现已实现全链路国际化适配，旨在为全球用户提供无缝的本地化体验。

- **自动同步系统语言**：集成将自动识别 Home Assistant 的系统语言（设置 -> 系统 -> 通用），并同步请求对应语言的天气数据（支持 30+ 种语言）。
- **智能语言回退机制**：
  - **基础天气/预警/AQI**：支持和风天气覆盖的所有 30 余种语言（如德语、法语、日语等）。
  - **分钟级降水 & 生活指数**：由于 API 限制，当系统设置为非中英语言时，这两个字段将自动回退至**英文**展示，确保数据永不报错。
- **自定义标题与 ID**：在安装阶段，集成会根据当前语言自动抓取并锁定城市名称（如：中文“北京”或英文“BeiJing”），从而生成美观且符合当地语言习惯的实体 ID。

## 📦 安装

### 通过HACS安装（推荐）

1. 在HACS的"集成"部分，点击右上角的三点菜单
2. 选择"自定义存储库"
3. 在存储库字段输入：
```yaml
https://github.com/hzonz/ha_qweather_pro
```
4. 类别选择"集成"
5. 点击"添加"保存
6. 在HACS中找到"和风天气Pro"集成并点击安装
7. 重启Home Assistant

### 手动安装

1. 下载最新的:
```yaml
https://github.com/hzonz/ha_qweather_pro
```
2. 解压并将`custom_components/qweather_pro`文件夹放入Home Assistant的`custom_components`目录
3. 重启Home Assistant

## 📖 文档导航
- [🚀 详细配置与使用教程 (DOCS.md)](md/DOCS_CN.md)
- [📜 版本更新历史 (CHANGELOG.md)](md/CHANGELOG_CN.md)

## 特别感谢： 本次更新由 AI 协助完成架构优化，并基于原版 [dscao/qweather](https://github.com/dscao/qweather) 进行了深度重构。

## 📜 声明

- 本项目与和风天气官方无直接隶属关系。
- 气象数据由 和风天气 (QWeather) 提供。
- 请遵守和风天气的 API 使用协议。

## 🤝 贡献

欢迎贡献代码、报告问题或提出功能建议！

1. 提交Issues：报告问题或功能请求
2. 提交Pull Requests：贡献代码改进
3. 项目讨论：分享使用经验或建议

## 📄 许可证

本项目基于MIT许可证开源。详情请查看LICENSE文件。

## ❤️ 支持

如果这个项目对您有帮助，请给项目点个Star ⭐！

---

## 兼容版本: 

- **Home Assistant 2026.1+**
  
  本集成最低兼容 HA 2026.1 及以上版本。

- **为确保集成品牌图片正确显示，请选择 Home Assistant 2026.3+**
  
  为确保品牌图标能够正确显示，建议使用 HA 2026.3 或更高版本。
  从 2026.3 起，Home Assistant 引入了 custom_integrations 目录与 Brands Proxy API，自定义集成可以在自身目录中直接包含品牌图片。