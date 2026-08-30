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

前端资源仅在启用时注册。请在集成页面的“选项”中开启“启用自定义前端 UI 支持”（custom_ui）以注册仪表盘卡片，开启“覆盖原生详情弹窗”（custom_more_info）以替换原生弹窗。开启后请重启 Home Assistant。您只需在 Lovelace 仪表盘添加卡片：
```yaml
type: custom:qweather-pro-card
entity: weather.qweather_pro_<城市名>_weather # 默认实体 ID（<城市名> 为添加集成时选择的城市）
```

### 可选配置 (UI 选项)

#### 点击集成页面的 “选项”，您可以实时调整：

- 数据更新频率：5 - 1440 分钟。
- 逐日预报天数：3 / 7 / 10 天（V1 接口上限）。
- 逐小时预报小时数：24 / 72 / 168 小时。
- 启用自定义前端 UI 支持：决定是否启用专业级天气卡片（主卡片）。
- 覆盖原生详情弹窗：决定是否用专业级详情弹窗替换 Home Assistant 原生的 more-info 弹窗。

### 🛠️ 传感器列表

## 和风天气实体说明

| **实体 ID** | **名称** | **说明** |
|-------------|----------|----------|
| `weather.qweather_pro_<城市名>_weather` | 天气 | 主天气实体。状态为当前天气状况与温度。支持 每日预报 / 逐小时预报 / 昼夜两次预报。属性含 `qweather_icon`、`update_time`、`condition_cn`、体感 `feels_like`、湿度、风向/风力/阵风（`wind_dir`/`wind_scale`/`wind_gust`）、降水（`precip`/`precip_type`/`precip_intensity`）、气压、能见度、露点、云量、日出日落与月相、昼夜风力与文字（`wind_scale_day`/`wind_dir_day`/`text_night`/`icon_night`）、`minutely_summary`、降水概率 `precip_probability`；开启「覆盖原生详情弹窗」时额外含 `custom_ui_more_info`。 |
| `sensor.qweather_pro_<城市名>_aqi` | 空气质量 | 状态为空气质量**等级文字**（如 优 / 良 / 轻度污染 / 中度污染）；属性含数值 `aqi_value`、等级 `aqi_level`、首要污染物 `primary_pollutant`、各污染物浓度（PM2.5、PM10、SO₂、NO₂、O₃、CO，带单位）及健康提示 `health_effect` / `health_advice` |
| `sensor.qweather_pro_<城市名>_precipitation_summary` | 降水简报 | 分钟级降水趋势摘要，例如“未来两小时无降水” |
| `sensor.qweather_pro_<城市名>_weather_summary` | 天气概况 | 状态为**今夜天气概况文字**（`tonight_text`，如“今夜多云”）；属性含完整智能概况 `weather_abstract`（时段、温度变化、当前气温、风力等） |
| `sensor.qweather_pro_<城市名>_current_temperature` | 实时温度 | 数值型温度传感器（单位 °C，`device_class: temperature`），支持长期统计与历史曲线。属性包含 `temp_range`（今日温度范围）、`max_temp`、`min_temp`、`feels_like`（体感温度）、`dew_point`（露点温度） |
| `sensor.qweather_pro_<城市名>_current_humidity` | 实时湿度 | 数值型湿度传感器（单位 %，`device_class: humidity`），提供当前环境相对湿度 |
| `sensor.qweather_pro_<城市名>_warning_info` | 气象预警 | 状态为当前生效预警的**标题文字**（取首条预警的 `headline`，如“暴雨橙色预警”）；无预警时为 `without_warning`。属性含完整预警详情（id、发布单位、发布时间、类型、等级、颜色、正文、防御指引） |
