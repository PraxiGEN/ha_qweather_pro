/**
 * QWeather Dashboard Card - Pro (2026.6 Enhanced)
 */
(async () => {
  const whenDefined = (t) => customElements.whenDefined(t);
  await Promise.race([whenDefined("ha-card"), whenDefined("ha-panel-lovelace")]);

  const Lit = window.LitElement || Object.getPrototypeOf(customElements.get("ha-card"));
  const html = Lit.prototype.html;
  const css = Lit.prototype.css;
  const I18N = window.QW_I18N;

  class QWeatherCard extends Lit {
    static get properties() {
      return { hass:{}, config:{}, _forecastDaily:{}, _forecastHourly:{}, _weather:{}, _briefing:{}, _selectedTab:{}, _lang:{} };
    }

    constructor() {
      super();
      this._forecastDaily = [];
      this._forecastHourly = [];
      this._selectedTab = "daily";
      this._unsubs = [];
      this._lang = "en";
      this._briefing = null;
    }

    _detectLang(hass) {
      const lang = hass.selectedLanguage || hass.language || "en";
      this._lang = I18N[lang] ? lang : "en";
    }

    _t(k){
      const parts = k.split(".");
      let obj = I18N[this._lang] || I18N.en;
      for(const p of parts){
        obj = obj?.[p];
        if(!obj) return k;
      }
      return obj;
    }

    setConfig(c) { this.config = { ...c }; }

    set hass(hass) {
      this._hass = hass;
      this._detectLang(hass);

      /* 自动识别天气实体 */
      let eid = this.config.entity;
      if (!eid || !hass.states[eid]) {
        const auto = Object.keys(hass.states).find((e) => e.startsWith("weather.qweather_pro_"));
        if (auto) { eid = auto; this.config.entity = auto; }
      }

      /* 自动识别天气概况实体 */
      let bid = this.config.weather_briefing_entity;
      if (!bid || !hass.states[bid]) {
        const autoBrief = Object.keys(hass.states).find(
          (e) => e.startsWith("sensor.qweather_pro_") && e.endsWith("_weather_briefing")
        );
        if (autoBrief) { bid = autoBrief; this.config.weather_briefing_entity = autoBrief; }
      }
      this._briefing = bid ? hass.states[bid] : null;

      const st = hass.states[eid];
      if (st && this._weather !== st) {
        this._weather = st;
        this._subscribeForecasts();
      }
    }

    async _subscribeForecasts() {
      this._clearSubs();
      const eid = this.config.entity;
      try {
        const subD = await this._hass.connection.subscribeMessage(
          (m) => { this._forecastDaily = m.forecast; this.requestUpdate(); },
          { type:"weather/subscribe_forecast", entity_id:eid, forecast_type:"daily" }
        );
        this._unsubs.push(subD);

        const subH = await this._hass.connection.subscribeMessage(
          (m) => { this._forecastHourly = m.forecast; this.requestUpdate(); },
          { type:"weather/subscribe_forecast", entity_id:eid, forecast_type:"hourly" }
        );
        this._unsubs.push(subH);
      } catch(e){ console.error("QWeather subscribe failed", e); }
    }

    _clearSubs() {
      while (this._unsubs.length) { const u = this._unsubs.pop(); if (u) u(); }
    }

    disconnectedCallback() { this._clearSubs(); super.disconnectedCallback(); }

    _handleTabClick(e,t){ e.stopPropagation(); this._selectedTab = t; }

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

    _formatDate(dt){
      const d = new Date(dt);
      if (d.getDate() === new Date().getDate()) return this._t("today");
      const days = I18N[this._lang]?.weekday || I18N.en.weekday;
      return days[d.getDay()];
    }

    _formatTime(dt){
      const d = new Date(dt);
      const h = d.getHours();
      return (h<10?"0"+h:h)+":00";
    }

    /* 天气概况摘要渲染 */
    _renderBriefing() {
      const d = this._briefing.attributes;
      const zh = this._lang.startsWith("zh");
      const period = this._t(`period.${d.period}`);
      const tempTrend = `${this._t("temp_change_prefix")}${this._t(`temp_change_type.${d.temp_change_type}`)}`;
      const aqi = `${this._t("now_prefix")}${d.aqi_status}`;
      const uv = d.uv_risk === "high" ? this._t("uv_high") : "";
      const tonightText = d.tonight_text || "";

      if (zh) {
        return `${period}${tonightText}，${tempTrend}。${aqi}，${uv}。`;
      }
      return `${period} ${tonightText}, ${tempTrend}. ${aqi}, ${uv}.`;
    }

    _renderAttr(icon,label,value){
      return html`
        <div class="attr-item">
          <ha-icon .icon=${icon}></ha-icon>
          <div><div class="attr-label">${label}</div><div class="attr-value">${value}</div></div>
        </div>`;
    }

    _renderSixAttributes(a){
      return html`
        <div class="attributes-grid-3x2">
          ${this._renderAttr("mdi:weather-windy",this._t("wind_scale"),`${a.wind_scale||"--"} ${this._t("level")}`)}
          ${this._renderAttr("mdi:compass",this._t("wind_dir"),a.wind_dir||"--")}
          ${this._renderAttr("mdi:water-percent",this._t("humidity"),`${a.humidity||"--"}%`)}
          ${this._renderAttr("mdi:weather-sunny-alert",this._t("uv_index"),a.uv_index||"--")}
          ${this._renderAttr("mdi:thermometer",this._t("feels_like"),`${a.feels_like||"--"}°C`)}
          ${this._renderAttr("mdi:eye",this._t("visibility"),`${a.visibility||"--"} km`)}
        </div>`;
    }

    render(){
      if(!this._weather) return html`<ha-card class="loading">${this._t("loading")}</ha-card>`;
      const a=this._weather.attributes;
      const isDaily=this._selectedTab==="daily";
      const fc=isDaily?this._forecastDaily:this._forecastHourly;

      return html`
        <ha-card @click="${this._handleMoreInfo}">
          
          <!-- Header -->
          <div class="header">
            <div class="header-left">
              <div class="weather-icon-circle"><img src="${this._getIcon(a.qweather_icon)}"></div>
              <div>
                <div class="condition-state">${a.condition_cn||this._weather.state}</div>
                <div class="city-name">${this.config.name||a.city||"QWeather"}</div>
              </div>
            </div>
            <div class="header-right">
              <div class="current-temp">${Math.round(a.temperature)}<span>°C</span></div>
              <div class="update-time">${a.update_time?.split(" ")[1]||""} ${this._t("update")}</div>
            </div>
          </div>

          <!-- Warnings -支持全显与白字 -->
          ${a.warning?.length
            ? a.warning.map(w=>html`
              <div class="warning-section" style="background-color:${this._getWarningColor(w.level)}">
                <ha-icon icon="mdi:alert-decagram"></ha-icon>
                <div>
                  <div style="font-weight:bold; font-size: 14px;">${w.title}</div>
                  <div class="warning-text">${w.text}</div>
                </div>
              </div>`)
            : ""}

          <!-- 智能简报 -->
          <div class="briefing-box">
            <div class="brief-item">
              <ha-icon icon="mdi:clock-fast"></ha-icon>
              <div class="brief-content">
                <span class="brief-label">${this._t("precip_brief")}</span>
                <span class="brief-value">${a.minutely_summary||this._t("no_precip")}</span>
              </div>
            </div>

            <div class="brief-item">
              <ha-icon icon="mdi:weather-partly-cloudy"></ha-icon>
              <div class="brief-content">
                <span class="brief-label">${this._t("weather_brief")}</span>
                <span class="brief-value">
                  ${this._briefing ? this._renderBriefing() : (a.hourly_summary||this._t("stable_weather"))}
                </span>
              </div>
            </div>
          </div>

          <!-- 6 指标 -->
          ${this._renderSixAttributes(a)}

          <!-- Tabs -->
          <div class="tabs">
            <div class="tab ${isDaily?"active":""}" @click=${e=>this._handleTabClick(e,"daily")}>${this._t("daily_forecast")}</div>
            <div class="tab ${!isDaily?"active":""}" @click=${e=>this._handleTabClick(e,"hourly")}>${this._t("hourly_forecast")}</div>
          </div>

          <!-- Forecast -->
          <div class="forecast-scroll-container">
            ${!fc?.length
              ? html`<div class="data-loading">${this._t("receiving")}</div>`
              : fc.map(i=>html`
                <div class="f-row">
                  <div class="f-date">${isDaily?this._formatDate(i.datetime):this._formatTime(i.datetime)}</div>
                  <div class="f-icon-box">
                    <img class="f-icon" src="${this._getIcon(i.icon)}">
                    ${isDaily?html`<span class="f-condition-text">${i.condition_cn||""}</span>`:""}
                  </div>
                  <div class="f-temp">
                    ${Math.round(i.temperature)}°
                    ${isDaily?html`<span class="f-low">${Math.round(i.templow)}°</span>`:""}
                  </div>
                </div>`)}
          </div>

          <div class="attribution">${a.attribution}</div>
        </ha-card>`;
    }

    _getWarningColor(lv){
      const c={"蓝色":"#2196f3","黄色":"#fdd835","橙色":"#ff9800","红色":"#f44336"};
      return c[lv]||"#f44336";
    }

    _handleMoreInfo(){
      this.dispatchEvent(new CustomEvent("hass-more-info",{detail:{entityId:this.config.entity},bubbles:true,composed:true}));
    }

    static get styles(){
      return css`
        :host{display:block;--primary-color:#03a9f4;}
        ha-card{padding:18px;cursor:pointer;border-radius:12px;transition:.3s;}
        ha-card:hover{box-shadow:var(--ha-card-box-shadow,0 4px 10px rgba(0,0,0,.12));}

        .header{display:flex;justify-content:space-between;align-items:center;margin-bottom:24px;}
        .header-left{display:flex;align-items:center;}
        .weather-icon-circle{width:56px;height:56px;margin-right:16px;border-radius:50%;background:var(--secondary-background-color);display:flex;align-items:center;justify-content:center;}
        .weather-icon-circle img{width:36px;height:36px;}
        .condition-state{font-size:22px;font-weight:500;}
        .city-name{font-size:13px;color:var(--secondary-text-color);}
        .current-temp{font-size:34px;font-weight:300;line-height:1;}
        .current-temp span{font-size:16px;vertical-align:top;margin-left:2px;}
        .update-time{font-size:11px;color:var(--secondary-text-color);margin-top:4px;text-align:right;}

        /* 预警：白字模式 */
        .warning-section{color:white;padding:12px;border-radius:8px;margin-bottom:16px;display:flex;gap:12px;border:1px solid rgba(255,255,255,.2);line-height:1.4;}
        .warning-section ha-icon{color:white;--mdc-icon-size:24px;flex-shrink:0;}
        .warning-text{font-size:12px;opacity:.95;margin-top:4px;display:block;white-space:pre-wrap;}

        .briefing-box{background:var(--secondary-background-color);padding:12px;border-radius:10px;margin-bottom:24px;display:flex;flex-direction:column;gap:8px;}
        .brief-item{display:flex;align-items:center;gap:10px;}
        .brief-item ha-icon{color:var(--primary-color);--mdc-icon-size:18px;}
        .brief-label{font-size:12px;color:var(--secondary-text-color);font-weight:bold;}
        .brief-value{font-size:13px;color:var(--primary-text-color);}

        .attributes-grid-3x2{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;margin-bottom:24px;}
        .attr-item{display:flex;align-items:center;}
        .attr-item ha-icon{margin-right:14px;color:var(--secondary-text-color);--mdc-icon-size:20px;}
        .attr-label{font-size:11px;color:var(--secondary-text-color);}
        .attr-value{font-size:14px;font-weight:500;}

        .tabs{display:flex;border-bottom:1px solid var(--divider-color);margin-bottom:16px;}
        .tab{padding:10px 16px;cursor:pointer;font-size:13px;font-weight:500;color:var(--secondary-text-color);border-bottom:2px solid transparent;}
        .tab.active{color:var(--primary-color);border-bottom-color:var(--primary-color);}

        .forecast-scroll-container{max-height:320px;overflow-y:auto;padding-right:4px;}
        .forecast-scroll-container::-webkit-scrollbar{width:4px;}
        .forecast-scroll-container::-webkit-scrollbar-thumb{background:var(--divider-color);border-radius:4px;}

        .f-row{display:flex;justify-content:space-between;align-items:center;padding:10px 0;border-bottom:1px solid var(--divider-color);}
        .f-date{width:70px;font-size:13px;}
        .f-icon-box{flex:1;display:flex;align-items:center;justify-content:center;gap:10px;}
        .f-icon{width:26px;height:26px;}
        .f-condition-text{font-size:12px;color:var(--secondary-text-color);width:40px;}
        .f-temp{width:80px;text-align:right;font-size:13px;font-weight:500;}
        .f-low{color:var(--secondary-text-color);margin-left:6px;}

        .data-loading{padding:30px;text-align:center;font-size:13px;color:var(--secondary-text-color);}
        .attribution{text-align:center;font-size:9px;color:var(--secondary-text-color);margin-top:16px;opacity:.6;}
        .loading{padding:40px;text-align:center;}
      `;
    }
  }

  customElements.define("qweather-card",QWeatherCard);
  window.customCards=window.customCards||[];
  window.customCards.push({
    type:"qweather-card",
    name:"QWeather Pro Card",
    preview:true,
    description:"A professional weather card with full-text alerts and white-on-red warning support."
  });
})();