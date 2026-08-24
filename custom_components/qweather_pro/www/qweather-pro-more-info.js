/** QWeather More Info */
(async () => {
  await customElements.whenDefined("ha-card");

  const Lit = window.LitElement || Object.getPrototypeOf(customElements.get("ha-card"));
  const html = Lit.prototype.html;
  const css = Lit.prototype.css;
  // 动态读取：i18n 为独立文件、加载时序不固定，一次性捕获会导致晚到时回退成翻译键甚至报错
  const getI18N = () => window.QW_I18N || {};
  const stripUnit = (v) => (v || "").toString().replace(/[^\d.-]/g, "");

  // 富数据缓存（按 entity_id），避免 more-info 多次开关/重渲染重复请求 get_weather
  const _richCache = new Map();
  const RICH_CACHE_TTL = 10 * 60 * 1000;   // 10 分钟内命中直接复用
  const RICH_MIN_REFRESH = 60 * 1000;      // 最小刷新间隔 60 秒，防抖合并

  class QWeatherMoreInfo extends Lit {
    static get properties() {
      return { hass: {}, stateObj: {}, _lang: {}, _richData: {}, _richEid: {} };
    }

    constructor() {
      super();
      this._lang = "en";
    }

    _detectLang(hass) {
      const lang = hass.selectedLanguage || hass.language || "en";
      this._lang = getI18N()[lang] ? lang : "en";
    }

    _t(k) {
      // 支持点分键路径 (如 "wd.sw")，同时保持扁平键向后兼容
      const parts = String(k).split(".");
      let s = getI18N()[this._lang] || {};
      for (const p of parts) s = s && s[p];
      if (s != null && typeof s !== "object") return s;
      s = getI18N().en || {};
      for (const p of parts) s = s && s[p];
      return s != null && typeof s !== "object" ? s : k;
    }

    // 风向 compass 代码 → 按当前语言翻译 (fallback 大写代码)
    _windDir(code) {
      if (!code) return "--";
      const t = this._t(`wd.${code}`);
      return t === `wd.${code}` ? String(code).toUpperCase() : t;
    }

    // 月相枚举 → 按当前语言翻译 (fallback 原枚举)
    _moonPhase(code) {
      if (!code) return "--";
      return this._t(`mp.${code}`);
    }

    set hass(hass) {
      this._hass = hass;
      this._detectLang(hass);
      this._maybeFetch();
    }

    set stateObj(value) {
      const old = this._stateObj;
      this._stateObj = value;
      this.requestUpdate("stateObj", old);
      this._maybeFetch();
    }

    get stateObj() {
      return this._stateObj;
    }

    // 实体切换或首次打开时拉取一次富数据；缓存命中则不重复请求
    _maybeFetch() {
      const eid = this._stateObj?.entity_id;
      if (!eid || !this._hass) return;
      if (eid !== this._richEid || !this._richData) {
        this._richEid = eid;
        this._fetchRichData(true);
      }
    }

    /** 通过自定义服务 qweather_pro.get_weather 获取实体属性中已剔除的富数据块
     * (aqi / indices)。
     * 原则：实体属性能读的读属性，不能的走服务；此处仅拉取属性中不再暴露的两块。
     * 缓存：命中模块级 _richCache 且未过期直接复用，避免 more-info 重复开关造成重复请求。
     * @param {boolean} force 是否强制刷新（实体切换 / 首次打开时 true）
     */
    _fetchRichData(force = false) {
      const eid = this._stateObj?.entity_id;
      if (!eid || !this._hass) return;

      const cached = _richCache.get(eid);
      const now = Date.now();
      if (cached && now - cached.ts < RICH_CACHE_TTL) {
        // 命中缓存：非 force 直接复用；force 但缓存仍很新也复用
        if (!force || now - cached.ts < RICH_MIN_REFRESH) {
          this._richData = cached.data;
          this.requestUpdate();
          return;
        }
      }

      clearTimeout(this._richTimer);
      this._richTimer = setTimeout(async () => {
        try {
          const result = await this._hass.callWS({
            type: "call_service",
            domain: "qweather_pro",
            service: "get_weather",
            service_data: { keys: ["aqi", "indices"] },
            target: { entity_id: eid },
            return_response: true,
          });
          // 兼容不同 HA 版本的返回结构：{ response: {...} } 或直接 {...}
          const data = result?.response ?? result ?? {};
          this._richData = data;
          _richCache.set(eid, { data, ts: Date.now() });
          this.requestUpdate();
        } catch (e) {
          console.error("QWeather get_weather service failed:", e);
        }
      }, 200);
    }

    _getIcon(code, datetime = null) {
      if (!code) return "https://static.qweather.com/img/common/icon/202106d/100.png";

      // 自动判断白天/夜晚
      let isDay = true;

      if (datetime) {
        const hour = new Date(datetime).getHours();
        isDay = hour >= 6 && hour < 18;
      }

      const suffix = isDay ? "d" : "n";
      return `https://static.qweather.com/img/common/icon/202106${suffix}/${code}.png`;
    }

    _renderAttr(icon, label, value) {
      return html`
        <div class="attr-item">
          <ha-icon .icon=${icon}></ha-icon>
          <div>
            <div class="attr-label">${label}</div>
            <div class="attr-value">${value}</div>
          </div>
        </div>
      `;
    }

    /* 生活指数渲染 - 修改：增加滚动容器 */
    _renderLifeIndex(list) {
      if (!list || !list.length)
        return html`<div class="no-data">${this._t("no_suggestions")}</div>`;

      return html`
        <div class="life-scroll-box">
          <div class="life-list">
            ${list.map(i => html`
              <div class="life-item">
                <div class="life-header">
                  <span class="life-title">${i.title_cn || i.title}</span>
                  <span class="life-brf">${i.brf}</span>
                </div>
                <div class="life-text">${i.txt || i.text}</div>
              </div>
            `)}
          </div>
        </div>
      `;
    }

    render() {
      if (!this.stateObj)
        return html`<div style="padding:30px;text-align:center;">${this._t("loading")}</div>`;

      const a = this.stateObj.attributes;
      const rd = this._richData || {};
      const air = rd.aqi || {};
      const lifeList = rd.indices || [];

      return html`
        <div class="content">

          <!-- 顶部 -->
          <div class="header-row">
            <div class="main-info">
              <div class="weather-icon" style="background-image:url(${this._getIcon(a.qweather_icon)})"></div>
              <div>
                <div class="state-text">${a.condition_cn || this.stateObj.state}</div>
                <div class="night_weather_info">
                  <span class="label">${this._t("night_weather_info")}：</span>
                  <span>${a.text_night || "--"}</span>
                  <span>·</span>
                  <span>${this._windDir(a.wind_dir_night)}</span>
                  <span>·</span>
                  <span>${this._moonPhase(a.moon_phase)}</span>
                </div>
              </div>
            </div>
            <div class="temp-text">${Math.round(a.temperature)}<sup>°C</sup></div>
          </div>

          <!-- 即时天气 4 项 -->
          <div class="section-title">${this._t("instant_weather")}</div>
          <div class="grid-2x2">
            ${this._renderAttr(
              "mdi:gauge",
              this._t("pressure"),
              `${a.pressure || "0"} hPa`
            )}
            ${this._renderAttr("mdi:thermometer", this._t("dew_point"), `${a.dew_point} °C`)}
            ${this._renderAttr(
              "mdi:cloud-outline",
              `${this._t("cloud_coverage")} · ${this._t("forecast_cloud")}`,
              `${a.cloud_coverage || "0"} · ${a.forecast_cloud|| "0"} %`
            )}
            ${this._renderAttr(
              "mdi:weather-windy",
               `${this._t("precip")} · ${this._t("precip_probability")}`, 
               `${a.precip || "0"} mm · ${a.precip_probability || "0"} %`
            )}
          </div>

          <!-- 空气质量 6 项（3×2）：6 项污染物，来自 get_weather 服务（V1 已剔除实体属性中的 aqi 块） -->
          <div class="section-title">${this._t("aqi")} </div>
          <div class="grid-3x2">
            ${this._renderAttr("mdi:blur", "PM2.5", stripUnit(air.pm2p5) || "--")}
            ${this._renderAttr("mdi:blur", "PM10", stripUnit(air.pm10) || "--")}
            ${this._renderAttr("mdi:chemical-weapon", "NO₂", stripUnit(air.no2) || "--")}
            ${this._renderAttr("mdi:chemical-weapon", "SO₂", stripUnit(air.so2) || "--")}
            ${this._renderAttr("mdi:weather-hazy", "O₃", stripUnit(air.o3) || "--")}
            ${this._renderAttr("mdi:molecule-co", "CO", stripUnit(air.co) || "--")}
          </div>

          <!-- 日月信息 4×1 -->
          <div class="section-title">${this._t("sun_moon")}</div>
          <div class="grid-4x1">
            ${this._renderAttr("mdi:weather-sunset-up", this._t("sunrise"), a.sunrise || "--")}
            ${this._renderAttr("mdi:weather-sunset-down", this._t("sunset"), a.sunset || "--")}
            ${this._renderAttr("mdi:arrow-up-bold-circle-outline", this._t("moonrise"), a.moonrise || "--")}
            ${this._renderAttr("mdi:arrow-down-bold-circle-outline", this._t("moonset"), a.moonset || "--")}
          </div>

          <!-- 生活指数 -->
          <div class="section-title">${this._t("lifestyle_title")}</div>
          ${this._renderLifeIndex(lifeList)}

          <!-- 页脚 -->
          <div class="footer">
            ${this._t("data_source")}: QWeather |
            ${this._t("update_at")}: ${(a.update_time || "").slice(5, 16) || "--"}
            ${a.degraded ? html`<span class="degraded-tag">${this._t("degraded")}</span>` : ""}
          </div>
        </div>
      `;
    }

    static get styles() {
      return css`
        .content { padding:16px; color:var(--primary-text-color); }

        .header-row { display:flex; justify-content:space-between; align-items:center; margin-bottom:20px; }
        .main-info { display:flex; align-items:center; }
        .weather-icon { width:60px; height:60px; background-size:contain; background-repeat:no-repeat; margin-right:14px; }
        .state-text { font-size:22px; font-weight:500; }
        .night_weather_info { font-size:12px; opacity:.6; margin-top:4px; }
        .temp-text { font-size:42px; font-weight:300; }
        .temp-text sup { font-size:18px; }

        .grid-2x2 { display:grid; grid-template-columns:repeat(2,1fr); gap:14px; margin-bottom:24px; }
        .grid-3x2 { display:grid; grid-template-columns:repeat(3,1fr); gap:14px; margin-bottom:24px; }
        .grid-4x1 { display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin-bottom:24px; }

        .attr-item { background:var(--secondary-background-color); padding:12px 14px; border-radius:12px; display:flex; align-items:center; min-width:0; }
        .attr-item ha-icon { margin-right:12px; color:var(--primary-color); --mdc-icon-size:22px; }
        .attr-label { font-size:11px; color:var(--secondary-text-color); white-space:normal; word-break:break-word; line-height:1.2; }
        .attr-value { font-size:15px; font-weight:600; }

        .section-title { font-size:15px; font-weight:bold; margin:18px 0 10px; border-left:4px solid var(--primary-color); padding-left:8px; }

        /* 生活指数滚动容器样式 */
        .life-scroll-box { 
          max-height: 360px; /* 限制约4个项目的高度 */
          overflow-y: auto; 
          padding-right: 6px;
          -webkit-overflow-scrolling: touch; /* 支持移动端流畅滑动 */
        }

        /* 滚动条美化 */
        .life-scroll-box::-webkit-scrollbar { width: 4px; }
        .life-scroll-box::-webkit-scrollbar-track { background: transparent; }
        .life-scroll-box::-webkit-scrollbar-thumb { background: var(--divider-color); border-radius: 10px; }

        .life-list { display:flex; flex-direction:column; gap:12px; }
        .life-item { padding:12px; border-radius:10px; background:var(--secondary-background-color); }
        .life-header { display:flex; justify-content:space-between; font-weight:bold; margin-bottom:6px; }
        .life-title { font-size:14px; }
        .life-brf { color:var(--primary-color); font-size:14px; }
        .life-text { font-size:13px; color:var(--secondary-text-color); line-height:1.5; }

        .no-data { text-align:center; opacity:.6; padding:10px; font-size:13px; }
        .footer { text-align:center; font-size:11px; opacity:.6; margin-top:20px; }
        .degraded-tag { display:inline-block; margin-left:8px; padding:1px 8px; border-radius:10px; font-size:10px; opacity:1; color:var(--warning-color, #ffab40); border:1px solid var(--warning-color, #ffab40); }
        
        @media (max-width: 600px) {

          .grid-3x2,
          .grid-4x1 {
            grid-template-columns: repeat(2, 1fr) !important;
          }

          .attr-item {
            padding: 10px 12px;
          }

          .attr-item ha-icon {
            --mdc-icon-size: 20px;
            margin-right: 8px;
          }

          .weather-icon {
            width: 48px;
            height: 48px;
          }

          .temp-text {
            font-size: 34px;
          }

          .section-title {
            font-size: 14px;
            margin: 14px 0 8px;
          }
        }    
      `;
    }
  }

  if (!customElements.get("qweather-pro-more-info"))
    customElements.define("qweather-pro-more-info", QWeatherMoreInfo);

})();