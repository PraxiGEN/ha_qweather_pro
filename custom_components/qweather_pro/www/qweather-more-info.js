/** QWeather More Info */
(async () => {
  await customElements.whenDefined("ha-card");

  const Lit = window.LitElement || Object.getPrototypeOf(customElements.get("ha-card"));
  const html = Lit.prototype.html;
  const css = Lit.prototype.css;
  const I18N = window.QW_I18N;
  const stripUnit = (v) => (v || "").toString().replace(/[^\d.-]/g, "");

  class QWeatherMoreInfo extends Lit {
    static get properties() {
      return { hass: {}, stateObj: {}, _lang: {} };
    }

    constructor() {
      super();
      this._lang = "en";
    }

    _detectLang(hass) {
      const lang = hass.selectedLanguage || hass.language || "en";
      this._lang = I18N[lang] ? lang : "en";
    }

    _t(k) {
      return I18N[this._lang][k] || I18N.en[k] || k;
    }

    set hass(hass) {
      this._hass = hass;
      this._detectLang(hass);
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
      const aqiVal = a.aqi?.aqi || "--";
      const aqiCat = a.aqi?.aqi_category || (this._lang === "zh" ? "未知" : "Unknown");
      const lifeList = a.suggestion || []; 

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
                  <span>${a.wind_dir_night || "--"}</span>
                  <span>·</span>
                  <span>${a.moon_phase || "--"}</span>
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
              `${this._t("pressure")} · ${this._t("forecast_pressure")}`,
              `${a.pressure || "0"} · ${a.forecast_pressure || "0"} hPa`
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

          <!-- 空气质量 6 项（3×2） -->
          <div class="section-title">${this._t("aqi")} </div>
          <div class="grid-3x2">
            <!-- ${this._renderAttr("mdi:air-filter", this._t("aqi"), aqiVal)} -->
            <!-- ${this._renderAttr("mdi:alert-circle", this._t("aqi_cat"), aqiCat)} -->
            ${this._renderAttr("mdi:blur", "PM2.5", stripUnit(a.aqi?.pollutants?.pm2p5) || "--")}
            ${this._renderAttr("mdi:blur", "PM10", stripUnit(a.aqi?.pollutants?.pm10) || "--")}
            ${this._renderAttr("mdi:chemical-weapon", "NO₂", stripUnit(a.aqi?.pollutants?.no2) || "--")}
            ${this._renderAttr("mdi:chemical-weapon", "SO₂", stripUnit(a.aqi?.pollutants?.so2) || "--")}
            ${this._renderAttr("mdi:weather-hazy", "O₃", stripUnit(a.aqi?.pollutants?.o3) || "--")}
            ${this._renderAttr("mdi:molecule-co", "CO", stripUnit(a.aqi?.pollutants?.co) || "--")}
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
            ${this._t("observed")}: ${a.obs_time.slice(5, 16).replace("T", " ")}
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
        
        @media (max-width: 600px) {

          .grid-3x2,
          .grid-4x2,
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

  if (!customElements.get("qweather-more-info"))
    customElements.define("qweather-more-info", QWeatherMoreInfo);

})();