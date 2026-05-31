# <img src="custom_components/qweather_pro/brand/icon.png" width="64"> 和风天气Pro (QWeather Pro)

[![Release](https://img.shields.io/github/v/release/hzonz/ha_qweather_pro)](https://github.com/hzonz/ha_qweather_pro/releases)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/hzonz/ha_qweather_pro/blob/main/LICENSE)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

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

## 📦 安装

### 通过HACS安装（推荐）

1. 在HACS的"集成"部分，点击右上角的三点菜单
2. 选择"自定义存储库"
3. 在存储库字段输入：`https://github.com/hzonz/ha_qweather_pro`
4. 类别选择"集成"
5. 点击"添加"保存
6. 在HACS中找到"和风天气Pro"集成并点击安装
7. 重启Home Assistant

### 手动安装

1. 下载最新的: `https://github.com/hzonz/ha_qweather_pro`
2. 解压并将`custom_components/qweather_pro`文件夹放入Home Assistant的`custom_components`目录
3. 重启Home Assistant

## 📖 文档导航
- [🚀 详细配置与使用教程 (DOCS.md)](md/DOCS.md)
- [📜 版本更新历史 (CHANGELOG.md)](md/CHANGELOG.md)

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
**兼容版本**: Home Assistant 2024.5+
