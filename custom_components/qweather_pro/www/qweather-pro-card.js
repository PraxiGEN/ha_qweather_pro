/** QWeather Dashboard Card - Pro*/
(async () => {
  const CARD_VERSION = "v1.0.1-lit";

  console.log(
    `%cQWeather Pro Card ${CARD_VERSION} Fixed`,
    "color: #1976d2; font-weight: bold; background: #e3f2fd; border: 1px solid #1976d2; border-radius: 4px; padding: 2px 6px;"
  );
  const whenDefined = (t) => customElements.whenDefined(t);
  await Promise.race([whenDefined("ha-card"), whenDefined("ha-panel-lovelace")]);

  const Lit = window.LitElement || Object.getPrototypeOf(customElements.get("ha-card"));
  const { html, css } = Lit.prototype;
  const I18N = window.QW_I18N || {}; // 防御性检查

  class QWeatherCard extends Lit {
    static get properties() {
      return { 
        hass: {}, config: {}, 
        _forecastDaily: { state: true }, 
        _forecastHourly: { state: true }, 
        _warningOpen: { state: true },
        _weather: { state: true }, 
        _selectedTab: { state: true }, 
        _lang: { state: true } 
      };
    }

    constructor() {
      super();
      this._forecastDaily = [];
      this._forecastHourly = [];
      this._warningOpen = {};
      this._selectedTab = "daily"; 
      this._unsubs = [];
      this._lang = "en";
      this._chart = null;
    }

    async updated(changedProps) {
      super.updated(changedProps);
      // 只有在预报数据变化、Tab切换或UI重绘后才更新图表
      if (changedProps.has("_forecastDaily") || changedProps.has("_forecastHourly") || changedProps.has("_selectedTab") || changedProps.has("_weather")) {
        // 使用 timeout 确保 DOM 节点 #weatherChart 已经存在于 Shadow DOM 中
        setTimeout(() => this._updateChart(), 150);
      }
    }

    _detectLang(hass) {
      const lang = hass.selectedLanguage || hass.language || "en";
      this._lang = I18N[lang] ? lang : "en";
    }

    _t(k) {
      const parts = k.split(".");
      let obj = I18N[this._lang] || I18N.en || {};
      for (const p of parts) { obj = obj?.[p]; if (!obj) return k; }
      return obj;
    }

    static getGridOptions() { return { rows: "auto", columns: 12 }; }

    static getStubConfig(hass) {
      const auto = Object.keys(hass.states).find((e) => e.startsWith("weather.qweather_pro_"));
      return { type: "custom:qweather-pro-card", entity: auto || "", show_daily: true, show_hourly: true, show_warnings: true };
    }

    setConfig(config) {
      if (!config) throw new Error("Invalid configuration");
      this.config = { show_daily: true, show_hourly: true, show_warnings: true, ...config };
      if (this.config.show_daily && !this.config.show_hourly) this._selectedTab = "daily";
      else if (!this.config.show_daily && this.config.show_hourly) this._selectedTab = "hourly";
    }

    set hass(hass) {
      this._hass = hass;
      this._detectLang(hass);
      const eid = this.config.entity;
      if (!eid) return;

      const st = hass.states[eid];
      if (st && (!this._weather || this._weather.entity_id !== st.entity_id)) {
        this._weather = st;
        this._subscribeForecasts();
      } else if (st) {
        this._weather = st;
      }
    }

    async _subscribeForecasts() {
      this._clearSubs();
      const eid = this.config.entity;
      if (!eid || !this._hass) return;
      try {
        const subD = await this._hass.connection.subscribeMessage(
          (m) => { this._forecastDaily = m.forecast; },
          { type: "weather/subscribe_forecast", entity_id: eid, forecast_type: "daily" }
        );
        this._unsubs.push(subD);
        const subH = await this._hass.connection.subscribeMessage(
          (m) => { this._forecastHourly = m.forecast; },
          { type: "weather/subscribe_forecast", entity_id: eid, forecast_type: "hourly" }
        );
        this._unsubs.push(subH);
      } catch (e) { console.error("QWeather subscribe failed", e); }
    }

    _clearSubs() { while (this._unsubs.length) { const u = this._unsubs.pop(); if (u) u(); } }
   
    disconnectedCallback() { 
      if (this._chart) { this._chart.destroy(); this._chart = null; }
      this._clearSubs(); 
      super.disconnectedCallback(); 
    }

    _handleTabClick(e, t) { e.stopPropagation(); this._selectedTab = t; }

    _getIcon(code, datetime = null) {
      if (!code) return "https://static.qweather.com/img/common/icon/202106d/100.png";
      let isDay = true;
      if (datetime) {
        const hour = new Date(datetime).getHours();
        isDay = hour >= 6 && hour < 18;
      }
      const suffix = isDay ? "d" : "n";
      return `https://static.qweather.com/img/common/icon/202106${suffix}/${code}.png`;
    }

    _formatDate(dt) {
      const d = new Date(dt);
      if (d.getDate() === new Date().getDate()) return this._t("today");
      const weekday = (I18N[this._lang] || I18N.en || {}).weekday || [];
      return weekday[d.getDay()] || dt;
    }

    _formatTime(dt) {
      const d = new Date(dt);
      const h = d.getHours();
      return (h < 10 ? "0" + h : h) + ":00";
    }

    _mapAqiLevel(aqi) {
      const v = parseInt(aqi);
      if (isNaN(v)) return 1;
      if (v <= 50) return 1; if (v <= 100) return 2; if (v <= 150) return 3;
      if (v <= 200) return 4; if (v <= 300) return 5; return 6;
    }

    _renderBriefing(a) {
      const d = a.weather_abstract;
      const zh = this._lang.startsWith("zh");
      const period = this._t(`period.${d.period}`);
      const tempTrend = `${this._t("temp_change_prefix")}${this._t(`temp_change_type.${d.temp_change_type}`)}`;
      const currentTemp = `${this._t("now_is")}${d.current_temp}°C`;
      const wind_status = this._t(`wind_status.${d.wind_status}`);
      const aqi_level = this._t(`aqi_level.${d.aqi_level}`);
      const tonightText = d.tonight_text || "";

      if (zh) {
        return `${period}${tonightText}，${tempTrend}。${currentTemp}，${wind_status}，${aqi_level}。`;
      }
      return `${period} ${tonightText}, ${tempTrend}. ${currentTemp}, ${wind_status}, ${aqi_level}.`;
    }

    _renderAttr(icon, label, value) {
      return html`
        <div class="attr-item">
          <ha-icon .icon=${icon}></ha-icon>
          <div><div class="attr-label">${label}</div><div class="attr-value">${value}</div></div>
        </div>`;
    }

    _renderSixAttributes(a) {
      return html`
        <div class="attributes-grid-3x2">
          ${this._renderAttr("mdi:thermometer", this._t("feels_like"), `${a.feels_like || "--"}°C`)}
          ${this._renderAttr("mdi:water-percent", this._t("humidity"), `${a.humidity || "--"}%`)}
          ${this._renderAttr("mdi:eye", this._t("visibility"), `${a.visibility || "--"} km`)}
          ${this._renderAttr("mdi:weather-windy", this._t("wind_scale"), `${a.wind_scale || "--"} ${this._t("level")}`)}
          ${this._renderAttr("mdi:compass", this._t("wind_dir"), a.wind_dir || "--")}
          ${this._renderAttr("mdi:weather-sunny-alert", this._t("uv_index"), a.uv_index || "--")}
        </div>`;
    }
    /** ApexCharts 渲染引擎 */
    async _updateChart() {
      const el = this.shadowRoot.getElementById('weatherChart');
      if (!el) return;

      const isDaily = this._selectedTab === "daily";
      const data = isDaily ? this._forecastDaily : this._forecastHourly;
      if (!data || data.length === 0) return;

      const series = isDaily ? [
        { name: this._t("max_temp") || 'Max', data: data.map(d => Math.round(d.temperature)) },
        { name: this._t("min_temp") || 'Min', data: data.map(d => Math.round(d.templow)) }
      ] : [
        { name: this._t("temp") || 'Temp', data: data.map(d => Math.round(d.temperature)) }
      ];

      const categories = data.map(d => isDaily ? this._formatDate(d.datetime) : this._formatTime(d.datetime));

      const options = {
        series: series,
        chart: {
          type: 'area',
          height: 180,
          toolbar: { show: false },
          animations: { enabled: true },
          sparkline: { enabled: false },
          background: 'transparent',
          fontFamily: 'inherit'
        },
        colors: isDaily ? ['#ff9800', '#2196f3'] : ['#03a9f4'],
        fill: {
          type: 'gradient',
          gradient: { shadeIntensity: 1, opacityFrom: 0.3, opacityTo: 0.05, stops: [0, 90, 100] }
        },
        stroke: { curve: 'smooth', width: 3 },
        dataLabels: {
          enabled: true,
          formatter: (v) => `${v}°`,
          style: { fontSize: '10px', colors: ['var(--primary-text-color)'] }
        },
        grid: { show: false },
        xaxis: {
          categories: categories,
          labels: { style: { colors: 'var(--secondary-text-color)', fontSize: '10px' } },
          axisBorder: { show: false }, axisTicks: { show: false }
        },
        yaxis: { show: false },
        legend: { show: false },
        tooltip: { theme: 'dark' }
      };

      if (!window.ApexCharts) {
        await new Promise((resolve) => {
          const s = document.createElement("script");
          s.src = "https://cdn.jsdelivr.net/npm/apexcharts";
          s.onload = resolve;
          document.head.appendChild(s);
        });
      }

      if (!this._chart) {
        this._chart = new ApexCharts(el, options);
        await this._chart.render();
      } else {
        this._chart.updateOptions(options);
      }
    }

    render() {
      if (!this._weather) return html`<ha-card class="loading">${this._t("loading")}</ha-card>`;
      const a = this._weather.attributes;
      const isDaily = this._selectedTab === "daily";
      const showAny = this.config.show_daily || this.config.show_hourly;

      return html`
        <ha-card @click="${this._handleMoreInfo}">
          <div class="header">
            <div class="header-left">
              <div class="weather-icon-circle"><img src="${this._getIcon(a.qweather_icon)}"></div>
              <div>
                <div class="condition-state">${a.condition_cn || this._weather.state}</div>
                <div class="city-name">${this.config.name || a.city || "QWeather"}</div>
              </div>
            </div>
            <div class="header-right">
              <div class="current-temp">${Math.round(a.temperature)}<span>°C</span></div>
              <div class="aqi-tag air-tag air-tag--${this._mapAqiLevel(a.aqi?.aqi)}">
               AQI ${a.aqi?.aqi_category || "--"}
              </div>
            </div>
          </div>

          ${this.config.show_warnings && a.warning?.length ? a.warning.map((w, i) => html`
            <div class="warning-section" style="background-color:${this._getWarningColor(w.level)}">
              <div class="warning-header" @click=${(e) => { e.stopPropagation(); this._warningOpen[i] = !this._warningOpen[i]; this.requestUpdate(); }}>
                <div class="warning-title"><ha-icon icon="mdi:alert-decagram"></ha-icon><span>${w.title}</span></div>
                <ha-icon class="warning-arrow" icon="${this._warningOpen[i] ? 'mdi:chevron-up' : 'mdi:chevron-down'}"></ha-icon>
              </div>
              ${this._warningOpen[i] ? html`<div class="warning-detail" @click=${(e)=>e.stopPropagation()}>${w.text}</div>` : ""}
            </div>
          `) : ""}

          <div class="briefing-box">
            <div class="brief-item">
              <ha-icon icon="mdi:clock-fast"></ha-icon>
              <div class="brief-content">
                <span class="brief-label">${this._t("precip_brief")}</span>
                <span class="brief-value">${a.minutely_summary || this._t("no_precip")}</span>
              </div>
            </div>
            <div class="brief-item">
              <ha-icon icon="mdi:weather-partly-cloudy"></ha-icon>
              <div class="brief-content">
                <span class="brief-label">${this._t("weather_brief")}</span>
                <span class="brief-value">${this._renderBriefing(a)}</span>
              </div>
            </div>
          </div>

          ${this._renderSixAttributes(a)}

          ${showAny ? html`
            <div class="tabs">
              ${this.config.show_daily ? html`<div class="tab ${isDaily ? "active" : ""}" @click=${e => this._handleTabClick(e, "daily")}>${this._t("daily_forecast")}</div>` : ""}
              ${this.config.show_hourly ? html`<div class="tab ${!isDaily ? "active" : ""}" @click=${e => this._handleTabClick(e, "hourly")}>${this._t("hourly_forecast")}</div>` : ""}
            </div>
            <div id="chart-wrapper"><div id="weatherChart"></div></div>
          ` : ""}

          <div class="footer">
            ${this._t("data_source")}: QWeather | ${this._t("update_at")}: ${a.update_time?.split(" ")[1] || ""}
          </div>
        </ha-card>`;
    }

    _getWarningColor(lv) {
      const c = { "蓝色": "#2196f3", "黄色": "#fdd835", "橙色": "#ff9800", "红色": "#f44336" };
      return c[lv] || "#f44336";
    }

    _handleMoreInfo() {
      this.dispatchEvent(new CustomEvent("hass-more-info", { detail: { entityId: this.config.entity }, bubbles: true, composed: true }));
    }

    static get styles() {
      return css`
        :host{display:block;--primary-color:#03a9f4;}
        ha-card{padding:18px;cursor:pointer;border-radius:12px;transition:.3s;overflow:hidden;display:flex;flex-direction:column;background:var(--card-background-color);color:var(--primary-text-color);}
        .header{display:flex;justify-content:space-between;align-items:center;margin-bottom:24px;}
        .header-left{display:flex;align-items:center;}
        .weather-icon-circle{width:56px;height:56px;margin-right:16px;border-radius:50%;background:var(--secondary-background-color);display:flex;align-items:center;justify-content:center;}
        .weather-icon-circle img{width:36px;height:36px;}
        .condition-state{font-size:22px;font-weight:500;}
        .current-temp{font-size:34px;font-weight:300;line-height:1;}
        .current-temp span{font-size:16px;vertical-align:top;margin-left:2px;}
        .air-tag {display:inline-block;width:76px;padding:4px 0;font-size:13px;line-height:16px;text-align:center;white-space:nowrap;border-radius:14px;color:white;}
        .air-tag--1{background-color:#95B359;} .air-tag--2{background-color:#A9A538;} .air-tag--3{background-color:#E0991D;} .air-tag--4{background-color:#D96161;} .air-tag--5{background-color:#A257D0;} .air-tag--6{background-color:#D94371;}
        .aqi-tag{margin-top:4px;}
        .warning-section{color:white;padding:12px;border-radius:8px;margin-bottom:16px;border:1px solid rgba(255,255,255,.2);}
        .warning-header{display:flex;justify-content:space-between;align-items:center;cursor:pointer;}
        .warning-title{display:flex;align-items:center;gap:8px;font-weight:bold;font-size:14px;}
        .warning-arrow{--mdc-icon-size:20px;color:white;}
        .warning-detail{margin-top:10px;font-size:12px;line-height:1.5;opacity:.95;}
        .briefing-box{background:var(--secondary-background-color);padding:12px;border-radius:10px;margin-bottom:24px;display:flex;flex-direction:column;gap:8px;}
        .brief-item{display:flex;align-items:center;gap:10px;}
        .brief-item ha-icon{color:var(--primary-color);--mdc-icon-size:18px;}
        .brief-label{font-size:12px;color:var(--secondary-text-color);font-weight:bold;}
        .brief-value{font-size:13px;}
        .attributes-grid-3x2{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;margin-bottom:24px;}
        .attr-item{display:flex;align-items:center;}
        .attr-item ha-icon{margin-right:14px;color:var(--secondary-text-color);--mdc-icon-size:20px;}
        .attr-label{font-size:11px;color:var(--secondary-text-color);}
        .attr-value{font-size:14px;font-weight:500;}
        .tabs{display:flex;border-bottom:1px solid var(--divider-color);margin-bottom:8px;}
        .tab{padding:10px 16px;cursor:pointer;font-size:13px;font-weight:500;color:var(--secondary-text-color);border-bottom:2px solid transparent;}
        .tab.active{color:var(--primary-color);border-bottom-color:var(--primary-color);}
        #chart-wrapper{min-height:180px;width:100%;margin:8px 0;}
        .footer{text-align:center;font-size:10px;color:var(--secondary-text-color);opacity:.6;margin-top:12px;}
        .loading{padding:40px;text-align:center;}
      `;
    }

    static getConfigElement() { return document.createElement("qweather-pro-card-editor"); }
  }

  class QWeatherCardProEditor extends Lit {
    static get properties() { return { hass: {}, config: {} }; }
    setConfig(c) { this.config = c; }
    set hass(h) {
      this._hass = h;
      if (h && this.config && !Object.prototype.hasOwnProperty.call(this.config, 'entity')) {
        const auto = Object.keys(h.states).find(e => e.startsWith("weather.qweather_pro_"));
        if (auto) this._valueChanged({ entity: auto, show_daily: true, show_hourly: true, show_warnings: true });
      }
    }
    _valueChanged(ev) {
      const config = ev?.detail?.value || ev;
      this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: { ...this.config, ...config } }, bubbles: true, composed: true }));
    }
    render() {
      if (!this._hass || !this.config) return html``;
      const lang = this._hass.selectedLanguage || this._hass.language || "en";
      const i18n = I18N[lang] || I18N.en || { editor: {} };
      return html`
        <ha-form
          .hass=${this._hass}
          .data=${this.config}
          .schema=${[
            { name: "name", selector: { text: {} } },
            { name: "entity", selector: { entity: { domain: "weather", integration: "qweather_pro" } } },
            { name: "show_daily", selector: { boolean: {} } },
            { name: "show_hourly", selector: { boolean: {} } },
            { name: "show_warnings", selector: { boolean: {} } }
          ]}
          .computeLabel=${(s) => i18n.editor[s.name] || s.name}
          @value-changed=${this._valueChanged}
        ></ha-form>`;
    }
  }

  customElements.define("qweather-pro-card", QWeatherCard);
  customElements.define("qweather-pro-card-editor", QWeatherCardProEditor);

  window.customCards=window.customCards||[];
  window.customCards.push({
    type:"qweather-pro-card",
    name:"QWeather Pro Card",
    preview:false,
    description:"A professional weather card with vertical symmetry and briefing entity selector."
  });
})();
