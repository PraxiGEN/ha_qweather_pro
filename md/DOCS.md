# 使用指南 (Documentation)

## ⚙️ 配置

### 1. 获取和风天气凭据

前往 和风天气控制台：

- 标准模式：获取普通的 API KEY。
- JWT 模式 (推荐)：在项目中添加 JSON Web Token 凭据。
- 获取 API host。 （个人 API服务地址）

### 步骤2：在Home Assistant中添加集成

1. 进入 配置 -> 设备与服务 -> 添加集成。
2. 搜索并选择 QWeather Pro。
3. 在配置界面填写以下基础信息:
     - API 服务器地址 `API host`。
     - 地理位置，自动获取HA默认经纬度，可选城市ID。
     - 普通 API key。
4. 如果选择 JWT 认证，集成会自动为您生成一段 公钥 (Public Key)：
    - 复制该公钥。
    - 粘贴到和风天气控制台的凭据设置中。
    - 在 HA 中填入生成的 Project ID 和 Key ID 即可完成绑定。

### 📈 前端展示

本集成会自动注册前端资源，您只需在 Lovelace 仪表盘添加卡片：
```yaml
type: custom:qweather-card
entity: weather.tian_qi  # 默认实体 ID
```

### 可选配置 (UI 选项)

#### 点击集成页面的 “选项”，您可以实时调整：

- 数据更新频率：5 - 1440 分钟。
- 预报天数/小时数：适配免费版与付费版。
- 格点天气：开启 1km 级高精度定位支持。
- 自定义 UI 支持：决定是否启用专业级详情弹窗。

### 🛠️ 传感器列表

## 和风天气实体说明

| **实体 ID** | **名称** | **说明** |
|-------------|----------|----------|
| `sensor.qweather_aqi` | 空气质量 | 提供 AQI 数值与等级（如：优 / 良 / 轻度污染），属性包含 PM2.5、PM10、CO、NO₂、O₃ 等详细污染物数据 |
| `sensor.qweather_precipitation_summary` | 降水简报 | 分钟级降水趋势摘要，例如“未来两小时无降水” |
| `sensor.qweather_weather_summary` | 天气概况 | 未来 6 小时天气趋势总结，例如“未来 6 小时：扬沙” |
| `sensor.qweather_today_temp_range` | 今日温度范围 | 今日最高/最低温度范围，格式如 `12°C / 25°C`，属性包含 `min_temp` 与 `max_temp` |
| `sensor.qweather_warning_count` | 气象预警数量 | 当前生效中的气象预警数量（如台风、暴雨、大风等） |
