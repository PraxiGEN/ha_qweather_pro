<div align="right">
  <a href="./README.md">English Version</a> | <strong>中文版</strong>
</div>

# <img src="custom_components/qweather_pro/brand/icon.png" width="64"> 和风天气Pro (QWeather Pro)

[![Release](https://img.shields.io/github/v/release/PraxiGEN/ha_qweather_pro)](https://github.com/PraxiGEN/ha_qweather_pro/releases)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/PraxiGEN/ha_qweather_pro/blob/main/LICENSE)
[![Marketplace](https://img.shields.io/badge/Marketplace-Available-blue.svg)](https://www.hacs.xyz/docs/marketplace/)

## 一款为 Home Assistant 深度定制的和风天气 (QWeather) 高级集成。

采用 1 个账号条目 + 按城市划分的位置子条目架构，支持 JWT (EdDSA) 鉴权与零依赖原生 SVG 天气卡片。

## ✨ 核心特性

### 架构

- 账号条目只保存凭据，每个城市是一个位置子条目。
- 预报步长、刷新间隔与自定义 UI 开关都在各自位置子条目的「配置」中设置。
- 新增城市无需重复填写账号凭据。

### 安全

- 默认启用和风天气 JWT (EdDSA) 鉴权。
- 本地生成 Ed25519 密钥对，仅保存私钥，避免 API 额度被盗用。

### 性能

- 后端：DataUpdateCoordinator 并发请求 + 智能缓存，最大限度节省 API 额度。
- 前端：温度趋势曲线使用原生 SVG 渲染，无需图表库。

### 数据

- 分钟级降水：API 原生驱动的降水简报（如「未来两小时无降水」）。
- 天气概况：逻辑合成的小时级天气变动简报。
- 丰富传感器：AQI（含详细参数）、今日温差、生效预警标题、气象摘要等。

### 视觉

- 仪表盘卡片：复刻专业天气 App 质感，支持 7 日预报与 24 小时预报切换。
- 可选详情弹窗：在位置子条目中开启后，用生活指数与完整预警详情替换 HA 原生弹窗。

### 国际化

- 系统语言同步至和风天气 API（30+ 种语言）；分钟级降水与生活指数按已知规则回退。

## 📦 安装

### 通过市场安装（推荐）

> 自 Home Assistant **2026.11** 起，HACS 已内置为系统自带的**市场（Marketplace）**，位于**设置 > 市场**，无需另行安装。

[![在 Home Assistant 市场中打开和风天气 Pro。](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=PraxiGEN&repository=ha_qweather_pro&category=integration)

或者手动操作：

1. 打开 Home Assistant，进入**设置 > 市场**。
2. 搜索 **QWeather Pro**。
3. 进入详情页，点击**安装**。
4. 前往**设置 > 设备与服务 > 添加集成**，搜索 **QWeather Pro** 并完成配置向导。

> 安装或更新后仅在 Home Assistant 提示时重启。


### 手动安装

1. 下载最新的 Release：

```yaml
https://github.com/PraxiGEN/ha_qweather_pro
```

2. 解压并将 `custom_components/qweather_pro` 文件夹放入 Home Assistant 的 `custom_components` 目录。
3. 重启 Home Assistant。
4. 前往**设置 > 设备与服务 > 添加集成**，搜索并添加 **QWeather Pro**。

## 📖 文档导航

- [详细配置与使用教程 (DOCS.md)](md/DOCS_CN.md)
- [版本更新历史 (CHANGELOG.md)](md/CHANGELOG_CN.md)

## 特别感谢

本项目由 AI 协助架构优化，并基于原版 [dscao/qweather](https://github.com/dscao/qweather) 深度重构。

## 📜 声明

- 本项目与和风天气官方无隶属关系。
- 气象数据由和风天气 (QWeather) 提供。
- 请遵守和风天气的 API 使用协议。

## 🤝 贡献

欢迎贡献代码、报告问题或提出功能建议。

1. 提交 Issues：报告问题或功能请求。
2. 提交 Pull Requests：贡献代码改进。
3. 项目讨论：分享使用经验或建议。

## 📄 许可证

本项目基于 MIT 许可证开源，详情请查看 LICENSE 文件。

## ❤️ 支持

如果这个项目对您有帮助，请给项目点个 Star。

---

## 兼容版本

- **Home Assistant 2026.9.0+**
  本集成最低兼容 Home Assistant 2026.9.0，使用原生子条目 API 与 probatio schema。

> **[ACTION REQUIRED]** 1.2.x 不能直达 2.0.0。请先升级到 1.3.x 完成自动迁移，再升级到 2.0.0；2.0.0 不再内置 v1 迁移层。