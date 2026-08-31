## 更新说明：和风天气 Pro 2026

### 🛠 [1.2.6] - 2026-08-31

基于 1.2.0-beta 系列构建的首个稳定版。本版解决了 HACS 审查中提出的全部 blocker（协调器陈旧数据、缺失 reauth、全局 JS 注入），并引入 JWT 鉴权与全面重写的零依赖原生 SVG 卡片。

### 📣 用户须知（配置与重新配置）
- **新增 JWT（Ed25519）鉴权：** 在原有 API Key 之外，现支持 JWT 鉴权。配置时需填写 项目ID（project_id）与 密钥ID（key_id），并生成或粘贴 Ed25519 私钥；签发者（iss）为可选项，建议填写以对齐和风开发者控制台。
- **重新配置支持切换鉴权与补充开发者字段：** 集成选项的"重新配置"现可在 API Key 与 JWT 之间切换，并可补充填写项目ID、密钥ID、签发者等开发者字段；原 API Key 用户无需重建集成即可切换到 JWT。
- **前端 UI 改为默认关闭（见下方破坏性变更）：** 若此前使用自定义主卡或详情弹窗，升级后请在集成选项中手动开启对应开关，否则前端回退为原生 UI。

### ⚠️ 破坏性变更（用户升级须知）
1. Lovelace 资源注入改为默认关闭（opt-in 双开关）：集成不再无条件向所有 HA 前端注入卡片/详情/i18n 的 JS 资源。集成选项新增两个独立开关：
- 启用自定义前端 UI 支持（custom_ui）：注册自定义主卡，默认关。
- 覆盖原生详情弹窗（custom_more_info）：用自定义详情卡替换原生弹窗，默认关。
- 已在用自定义卡片/详情弹窗的用户，升级后必须手动开启对应开关，否则前端回退原生 UI。
2. 实时温度传感器重命名：temp_range 类传感器更名为数值型 current_temperature（实体 registry 会重建）。

### ✨ 核心新功能
- 前端卡片零依赖原生 SVG 重写（最大改动，qweather-pro-card.js +814 行，从 ApexCharts 871KB 全局包降为 ~32KB 原生 SVG）：
- 彻底消除与 apexcharts-card 等生态卡片的全局 JS 冲突（原 issue #61 根因）。
- 支持列表/曲线两种样式；逐时预报图支持滚轮缩放与左右平移、重置按钮重绘。
- qweather-pro-i18n.js、qweather-pro-more-info.js 同步重写（i18n 动态读取、消除加载时序竞态）。
- JWT（Ed25519）鉴权体系：config_flow.py 新增 jwt_setup / reauth_jwt / reconfigure 全流程，密钥对仅生成一次并落库私钥、公钥确定性推导展示 + SHA256 指纹比对。
- reauth 流程落地：401/403 时协调器抛 ConfigEntryAuthFailed → 自动触发重认证，不再静默陈旧。
- 新增 current_humidity 实时湿度传感器；天气实体新暴露 wind_gust / precip_type / precip_intensity 等字段；日预报补充 precipitation_type。
- 新增 qweather_pro.get_weather 服务（services.py +168、services.yaml +31）。
- diagnostics 凭据脱敏（diagnostics.py +37，redact API Key / 私钥 / project）。

### 🐛 协调器硬化（HACS 审查 blocker 修复）
- coordinator.py 大幅重写（+596）：抓取全部失败时正确 raise UpdateFailed → last_update_success=False、实体转 unavailable，不再返回并永久服务昨天的数据；update_time 仅在成功路径更新，避免"看起来健康实为陈旧"。
- API KEY 模式强制锁定 100 分钟刷新间隔、忽略用户越权覆盖。

### 🔧 配置流 / 合规修复
- 翻译 schema 合规：JWT 说明文本内联进 description、动态公钥块用 {key_block} 运行时占位符（修复 hassfest not a valid option 报错）。
- manifest 正确声明 tenacity>=9.1.2（HA 2026.1 起 tenacity 已移出核心依赖）；after_dependencies:["frontend"] 正确声明。
- reconfigure 终止 reason 修正为 reconfigure_successful；async_init 不再误传 entry.data 致流程提前结束。
- 移除 config_flow.py 未使用的 async_get_translations 死导入（PR #86）。

### 🌐 翻译与文档（HACS 审查回应）
- 12 语言翻译大幅补全（每语言 +400 行）：JWT 键、SVG 样式键、湿度、预警字段顺序等。
- README/DOCS 事实修正：SVG 宣称与卡片一致；文档卡片类型改正为 custom:qweather-pro-card（原 qweather-card 不存在）；实体表 warning_info 与实际代码对齐。
- LICENSE 补 dscao 原作者 MIT 署名（维持主版权行 Copyright (c) 2026 PraxiGEN 不变，新增 Based on dscao/qweather ... used under MIT，PR #86）；LICENSE 文件格式亦已修正，GitHub 现正确识别为 MIT（此前因插入署名行被识别为 NOASSERTION）。
- brand 清理：删除非 ASCII 备份文件 logo备.png（183KB）。

### 🧪 测试与 CI
- 测试迁至仓库根 tests/（ludeeus 布局，移出集成目录，HACS 不再误打包）。
- 新增 pytest CI 工作流（tests.yml）、pr-validate/hassfest 校验；stale.yml 自动关旧 issue。
- 新增 11 个测试模块（config_flow / weather / sensor / coordinator / services / diagnostics / init / condition / const 等），覆盖 JWT、reconfigure、协调器、传感器。

### 📊 文件规模
49 文件变更，+7903 / −1788：

- 重写级：coordinator.py(+596)、config_flow.py(+374)、www/qweather-pro-card.js(+814)、weather.py(+313)、translations/*(12×~404)
- 新增：services.py、services.yaml、diagnostics.py、tests/*(11)、pytest.ini、conftest.py
- 清理：删 brand/logo备.png、降卡片体积

### 🛠 [1.2.0-beta.5] - 2026-08-24

### ⚠️ 破坏性变更
- **前端资源注册改为默认关闭：** 集成不再无条件向所有 Home Assistant 前端注入其前端资源（主卡 / 详情弹窗 / i18n）。集成选项中新增两个相互独立的总开关：
  - `启用自定义前端 UI 支持`（custom_ui）：注册自定义主卡。**默认关闭。**
  - `覆盖原生详情弹窗`（custom_more_info）：用自定义详情卡片替换原生实体详情弹窗。**默认关闭。**
  - 已在使用自定义主卡或自定义详情弹窗的用户，升级后需在集成选项中手动打开对应开关，否则前端回退为原生 UI。

### ✨ 新功能
- 新增 `current_humidity` 实时湿度传感器实体，报告当前相对湿度（%）。

### 🐛 问题修复
- 为全部 12 种语言翻译 `precip_type` 状态值（雨 / 雪 / 冰粒或冻雨 / 混合降水 / 无降水 / 未知），天气实体的降水类型属性现在显示本地化文案而非原始代码。
- 修复自定义卡片偶显翻译键（而非本地化文本）的问题。卡片现动态读取 i18n 包，并在其就绪后重绘，消除加载时序竞争。
- 修复图表重置按钮将 X 轴变成数字索引（0,1,2…）而非星期/时间标签的问题；重置现在重建图表。
- 修复数据点数较少时预报图表未占满卡片宽度的问题，改用数值轴使数据始终贴边铺满。

### 🔧 卡片 / 图表优化
- 逐小时预报图表现支持鼠标滚轮缩放与左右划动，默认 10 小时视窗并带自定义重置按钮。

### 🛠 [1.2.0-beta.4] - 2026-08-23

### 🐛 问题修复
- 修复每次 coordinator 更新都会抛出的 `TypeError: async_update_listeners() missing 1 required positional argument: 'forecast_types'` 报错。现已传入 `None`（刷新全部预报类型），符合 Home Assistant 2024.4 起的必填要求。

### ✨ 新增暴露的实体属性
- 天气实体新增暴露原先未输出的实况字段：`wind_gust`（阵风风速，km/h）、`precip_type`（降水类型：雨/雪/无）、`precip_intensity`（降水强度）。
- 每日预报条目新增 `precipitation_type`，与逐小时预报保持一致。
- 天气实体属性新增 14 个天文/月相时间字段（均为本地时间 HH:MM）：`sunrise`（日出）、`sunset`（日落）、`astronomical_dawn`（天文晨光）、`nautical_dawn`（航海晨光）、`civil_dawn`（民用晨光）、`astronomical_dusk`（天文暮光）、`nautical_dusk`（航海暮光）、`civil_dusk`（民用暮光）、`solar_noon`（正午太阳时）、`solar_midnight`（子夜太阳时）、`moonrise`（月出）、`moonset`（月落）、`moon_transit`（月上中天）、`moon_underfoot`（月下中天）。
- `current_temperature` 温度传感器新增暴露 `temp_avg`（日均温）。

### 🌐 翻译
- 为全部 12 种语言新增上述新字段的本地化名称键。

### 🛠 [1.2.0-beta.3] - 2026-08-19

### 🐛 问题修复
- 修复湿度（及其他百分比字段）显示 `57.99999999999999%` 这类长浮点伪影的问题，百分比现取整显示。
- 移除气象预警属性中无效的 `color_name` 字段（V1 API 不返回该字段）。
- 精简 `manifest.json` 依赖声明：仅保留 `tenacity>=9.1.4`（下限约束，环境已满足则不强制升级）。`aiohttp` / `cryptography` / `PyJWT` 为 Home Assistant 核心内置依赖，无需再显式声明。

### 🛠 [1.2.0-beta.2] - 2026-08-16

### ⚠️ 破坏性变更（Breaking Changes）
- **API 迁移（V7 → V1）**：数据层已从和风天气 V7 API 全面切换到 **V1 API**。coordinator 解析器已按 V1 的 `daytime` / `nighttime` 嵌套结构重写，并新增主备数据源回退（primary/backup fallback）。依赖旧 V7 字段映射的自定义模板/自动化需重新核对。
- **天气实体属性变更**：预报与实况属性已按 V1 结构重组。
  - 每日预报改为昼夜嵌套：新增 `wind_scale_day` / `wind_dir_day` / `wind_scale_night` / `wind_dir_night`、`icon_night` / `text_night` / `condition_night`、`wind_360_*` 等键；风向改用 `wind_degree`（角度）/ `wind_compass`（方位）表达。
  - 实况扩展属性按 V1 重排：`wind_dir`、`wind_scale`、`forecast_cloud`、`moon_phase` 等键名/取值有调整；旧的 `obsTime` 观测时间戳已移除，由 `update_time` 兜底。
  - 任何直接引用旧（V7 扁平）属性键的模板/自动化/第三方卡片，现在都会取到 `unknown`，请改用新键。
- **温度传感器实体重命名**：`sensor.qweather_today_temp_range` → `sensor.qweather_current_temperature`。由字符串实体改为**数值型**温度传感器（`device_class: temperature`、`state_class: measurement`、单位 °C）。原字符串状态 `12°C/25°C` 改为数值状态 + 属性 `temp_range`（今日温度范围）、`max_temp`、`min_temp`、`feels_like`（体感温度）、`dew_point`（露点温度）。引用旧实体 id 或旧字符串状态的模板/自动化需相应更新。

### 🔐 认证与额度策略
- 默认使用 JWT：新接入和重新配置默认采用 JWT 认证，无请求限制；API KEY 仍可用，但改为可选。
- API KEY 即将受限：自 2027-01-01 起，和风天气将对 API KEY 认证设置每日请求上限（具体数值未公布），且 SDK 5+ 不再支持 API KEY，推荐使用 JWT。
- 智能迁移提示：若你仍在使用 API KEY，系统会在“修复”中弹出提示，引导你切换到 JWT，以获得无限额、更频繁的更新。
- API KEY 轮询更慢：使用 API KEY 时，默认刷新间隔放宽到 100 分钟（原为 15 分钟），从容应对即将到来的限制。

### 💾 重启不丢数据
- 改用 Home Assistant 原生存储缓存天气数据。重启后，上一次的数据会立即恢复，无需等待下一次刷新。

### 🔧 按需天气服务
- 新增 `get_weather` 服务，可随时主动拉取最新天气；卡片已改用它读取空气质量（AQI）与恶劣天气预警。

### 🃏 卡片升级（V1）
- 卡片通过 `get_weather` 服务读取空气质量（AQI）与恶劣天气预警。
- 详情面板补充了更多 V1 字段，含独立的白天/夜间天气状况。
- 品牌名与技术缩写不再塞进翻译文件，仅可本地化文案参与翻译。

### 🌐 翻译
- 已将 API KEY 额度提示同步至全部 12 种语言；同时更新了 V1 API 相关文案与新界面字符串。

### 🧰 其他
- 新增诊断页（diagnostics），可导出集成数据用于排障。
- 新增凭证过期后的重新认证流程（re‑auth flow）。
- 重构传感器以适配 V1 每日嵌套结构。
- 详情面板补齐风向、月相等字段与本地化。

### 🛠 [1.1.0] - 2026-06-02 (里程碑)

### 🌍 全链路国际化 (Internationalization)
- 系统语言自动同步：集成现在能够自动识别并实时跟随 Home Assistant 的系统语言设置（支持 30+ 种全球语言）。
- 智能语言回退机制：针对“分钟降水”和“生活指数”API 的局限性，实现了自动回退逻辑。当系统处于非中英语言时，这些字段会自动降级为英文显示，确保全球用户都能获得稳定的数据输出。
- 条件化实体加载：天气概况实体（Weather Summary）现在具备语言感知能力。该实体仅在系统语言为中文或英文时生成。切换至其他语言并重载后，系统会自动移除该实体，保持界面的本地化纯净。

### 📡 API Host 适配 (2026.6.1 强制标准)
- 公共域名关停适配：严格遵循和风天气 2026 年 6 月 1 日全面关停公共域名的公告。彻底移除了 api.qweather.com 等硬编码，强制推行个人专属 API Host。
- GeoAPI 路径重构：自动处理地理查询路径的变更（v2 -> geo/v2），用户只需输入 Host 域名，底层逻辑会自动适配所有版本路径。

### 🛡️ 工业级容错与自愈 (Resiliency)
- 双重保障重试机制：引入 Tenacity 库实现指数退避重试（Exponential Backoff）。针对瞬时网络抖动，系统会在后台静默重试，用户 UI 保持无感刷新。
- 智能退让模式 (Circuit Breaker)：当检测到持续性网络故障或 API 欠费时，集成会自动将刷新频率降低至 1 小时/次，防止频繁请求导致 IP 被封禁。
- 冷启动自愈逻辑：修复了重启 HA 时因网络未就绪导致实体“永久未知”的顽疾。若启动刷新失败，集成将保持高频重试直至获取第一手数据，不再死等长周期循环。

### 📍 地理数据标准化 (Normalization)
- 多模输入自动转换：地理位置输入框现在支持“城市名”、“城市 ID”和“经纬度”三种模式。无论用户输入什么，集成都会在配置阶段通过 GeoAPI 自动将其标准化为高精度坐标存储。
- 全 API 坐标驱动：为了发挥 V1 预警和 V1 空气质量 API 的最大精度（1x1公里级），所有底层请求现已统一升级为“精准经纬度驱动”，彻底解决了使用城市 ID 导致部分专业 API 失效的问题。

### 📊 铂金级数据对齐 (Professional Data)
- 专业空气质量 (V1)：将 AQI 接口从 V7 升级至 V1。现在提供站点级的污染物浓度（PM2.5, NO2, O3 等带单位数据）、详细的健康影响评价以及针对不同人群的防护建议。
- 预警信息深度解析：完美复刻和风 V1 预警协议，包含发布单位、防御指南（Instruction）、预警颜色等级等全量字段。
- 无损属性保留：重构了数据字典，确保 100% 保留了原流程中所有的 16+ 个实况天气属性，并新增了月相（Moon Phase）、紫外线（UV）、昼夜天气状况等高阶气象参数。

### 🚀 架构现代化 (Modernization)
- Runtime Data & 强类型：全面采用 HA 2026.5 规范的 ConfigEntry.runtime_data 配合 PEP 695 类型别名。
