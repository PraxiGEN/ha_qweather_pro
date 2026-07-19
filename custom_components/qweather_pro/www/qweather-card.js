/** QWeather Dashboard Card - Pro*/
(async () => {
  const CARD_VERSION = "v1.0.0-lit";

  console.log(
    `%cQWeather Pro Card ${CARD_VERSION} Fixed`,
    "color: #1976d2; font-weight: bold; background: #e3f2fd; border: 1px solid #1976d2; border-radius: 4px; padding: 2px 6px;"
  );
  
  const whenDefined = (t) => customElements.whenDefined(t);
  await Promise.race([whenDefined("ha-card"), whenDefined("ha-panel-lovelace")]);

  const Lit = window.LitElement || Object.getPrototypeOf(customElements.get("ha-card"));
  const html = Lit.prototype.html;
  const css = Lit.prototype.css;
  const I18N = window.QW_I18N;

  class QWeatherCard extends Lit {
    static get properties() {
      return { hass:{}, config:{}, _forecastDaily:{}, _forecastHourly:{}, _weather:{}, _selectedTab:{}, _lang:{} };
    }

    constructor() {
      super();
      this._forecastDaily = [];
      this._forecastHourly = [];
      this._warningOpen = {};
      this._selectedTab = "daily"; 
      this._unsubs = [];
      this._lang = "en";
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

    static getGridOptions() { return { rows: "auto", columns: 12 }; }

    static getStubConfig(hass) {
      const auto = Object.keys(hass.states).find((e) => e.startsWith("weather.qweather_pro_"));
      return { 
        type: "custom:qweather-card",
        entity: auto || "", 
        show_daily: true, 
        show_hourly: true 
      };
    }

    setConfig(config) {
      if (!config) throw new Error("Invalid configuration");
      this.config = { show_daily: true, show_hourly: true, ...config };

      // --- 同步逻辑：确保选中的标签与开关状态匹配 ---
      if (this.config.show_daily && !this.config.show_hourly) this._selectedTab = "daily";
      else if (!this.config.show_daily && this.config.show_hourly) this._selectedTab = "hourly";
    }

    set hass(hass) {
      this._hass = hass;
      this._detectLang(hass);
      // 直接从配置读取实体
      const st = hass.states[this.config.entity];
      if (st && (!this._weather || this._weather.entity_id !== st.entity_id)) {
        this._weather = st;
        this._subscribeForecasts();
      } else if (st) {
        this._weather = st;
      }
    }

    async _subscribeForecasts() {
      while (this._unsubs.length) { const u = this._unsubs.pop(); if (u) u(); }
      const eid = this.config.entity;
      if (!eid) return;
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

    _handleTabClick(e,t){ e.stopPropagation(); this._selectedTab = t; this.requestUpdate(); }

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

    _mapAqiLevel(aqi) {
      if (!aqi) return 1;
      if (aqi <= 50) return 1;
      if (aqi <= 100) return 2;
      if (aqi <= 150) return 3;
      if (aqi <= 200) return 4;
      if (aqi <= 300) return 5;
      return 6;
    }
  
    _toggleWarning(i) {
      this._warningOpen[i] = !this._warningOpen[i];
      this.requestUpdate();
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
          ${this._renderAttr("mdi:thermometer",this._t("feels_like"),`${a.feels_like||"--"}°C`)}
          ${this._renderAttr("mdi:water-percent",this._t("humidity"),`${a.humidity||"--"}%`)}
          ${this._renderAttr("mdi:eye",this._t("visibility"),`${a.visibility||"--"} km`)}
          ${this._renderAttr("mdi:weather-windy",this._t("wind_scale"),`${a.wind_scale||"--"} ${this._t("level")}`)}
          ${this._renderAttr("mdi:compass",this._t("wind_dir"),a.wind_dir||"--")}
          ${this._renderAttr("mdi:weather-sunny-alert",this._t("uv_index"),a.uv_index||"--")}
        </div>`;
    }

    render(){
      if(!this._weather) return html`<ha-card class="loading">${this._t("loading")}</ha-card>`;
      
      const a=this._weather.attributes;
      const isDaily=this._selectedTab==="daily";
      const fc=isDaily?this._forecastDaily:this._forecastHourly;
      
      const showDaily = this.config.show_daily;
      const showHourly = this.config.show_hourly;
      const showAny = showDaily || showHourly;

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
              <div class="aqi-tag air-tag air-tag--${this._mapAqiLevel(a.aqi?.aqi)}">
               AQI ${a.aqi?.aqi_category || "--"}
              </div>
            </div>
          </div>

          <!-- Warnings -->
          ${a.warning?.length ? a.warning.map((w, i) => html`
            <div class="warning-section" style="background-color:${this._getWarningColor(w.level)}">
              <div class="warning-header" @click=${(e) => { e.stopPropagation(); this._toggleWarning(i); }}>
                <div class="warning-title"><ha-icon icon="mdi:alert-decagram"></ha-icon><span>${w.title}</span></div>
                <ha-icon class="warning-arrow" icon="${this._warningOpen[i] ? 'mdi:chevron-up' : 'mdi:chevron-down'}"></ha-icon>
              </div>
              ${this._warningOpen[i] ? html`<div class="warning-detail" @click=${(e)=>e.stopPropagation()}>${w.text}</div>` : ""}
            </div>
          `) : ""}

          <!-- Briefing -->
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
                  ${this._renderBriefing(a)}
                </span>
              </div>
            </div>
          </div>

          <!-- 6 Attributes -->
          ${this._renderSixAttributes(a)}

          <!-- Tabs -->
          ${showAny ? html`
            <div class="tabs">
              ${showDaily ? html`
                <div class="tab ${isDaily?"active":""}" @click=${e=>this._handleTabClick(e,"daily")}>${this._t("daily_forecast")}</div>
              ` : ""}
              ${showHourly ? html`
                <div class="tab ${!isDaily?"active":""}" @click=${e=>this._handleTabClick(e,"hourly")}>${this._t("hourly_forecast")}</div>
              ` : ""}
            </div>
          ` : ""}

          <!-- Forecast Content -->
          ${showAny ? html`
            <div class="forecast-scroll-container">
              ${(!fc || fc.length === 0)
                ? html`<div class="data-loading">${this._t("receiving")}</div>`
                : fc.map(i => html`
                  <div class="f-row">
                    <div class="f-date">${isDaily ? this._formatDate(i.datetime) : this._formatTime(i.datetime)}</div>
                    <div class="f-icon-box">
                      <img class="f-icon" src="${this._getIcon(i.icon, isDaily ? null : i.datetime)}">
                      ${isDaily ? html`<span class="f-condition-text">${i.condition_cn || ""}</span>` : ""}
                    </div>
                    <div class="f-temp">
                      ${Math.round(i.temperature)}°
                      ${isDaily ? html`<span class="f-low">${Math.round(i.templow)}°</span>` : ""}
                    </div>
                  </div>
                `)}
            </div>
          ` : ""}

          <!-- Footer -->
          <div class="footer">
            ${this._t("data_source")}: QWeather | ${this._t("update_at")}: ${a.update_time?.split(" ")[1]||""}
          </div>
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
        ha-card{padding:18px;cursor:pointer;border-radius:12px;transition:.3s;overflow:hidden;display: flex;flex-direction: column;}
        ha-card:hover{box-shadow:var(--ha-card-box-shadow,0 4px 10px rgba(0,0,0,.12));}
        .loading { padding: 30px; color: var(--secondary-text-color); text-align: center; }
        .header{display:flex;justify-content:space-between;align-items:center;margin-bottom:24px;}
        .header-left{display:flex;align-items:center;}
        .weather-icon-circle{width:56px;height:56px;margin-right:16px;border-radius:50%;background:var(--secondary-background-color);display:flex;align-items:center;justify-content:center;}
        .weather-icon-circle img{width:36px;height:36px;}
        .condition-state{font-size:22px;font-weight:500;}
        .current-temp{font-size:34px;font-weight:300;line-height:1;}
        .current-temp span{font-size:16px;vertical-align:top;margin-left:2px;}
        .air-tag {display: inline-block;width: 76px;padding: 4px 0;font-size: 13px;line-height: 16px;text-align: center;white-space: nowrap;border-radius: 14px;color: white;}
        .air-tag--1 { background-color: #95B359; }
        .air-tag--2 { background-color: #A9A538; }
        .air-tag--3 { background-color: #E0991D; }
        .air-tag--4 { background-color: #D96161; }
        .air-tag--5 { background-color: #A257D0; }
        .air-tag--6 { background-color: #D94371; }
        .aqi-tag {margin-top: 4px;}
        .warning-section { color: white; padding: 12px; border-radius: 8px; margin-bottom: 16px; border: 1px solid rgba(255,255,255,.2); }
        .warning-header { display: flex; justify-content: space-between; align-items: center; cursor: pointer; }
        .warning-title { display: flex; align-items: center; gap: 8px; font-weight: bold; font-size: 14px; }
        .warning-arrow { --mdc-icon-size: 20px; color: white; }
        .warning-detail { margin-top: 10px; font-size: 12px; line-height: 1.5; opacity: .95; }
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
        .forecast-scroll-container{max-height:320px;overflow-y:auto;padding-right:4px;transition: all 0.3s ease-in-out;}
        .forecast-scroll-container::-webkit-scrollbar{width:4px;}
        .forecast-scroll-container::-webkit-scrollbar-thumb{background:var(--divider-color);border-radius:4px;}
        .f-row{display:flex;justify-content:space-between;align-items:center;padding:10px 0;border-bottom:1px solid var(--divider-color);}
        .f-date{width:70px;font-size:13px;}
        .f-icon-box{flex:1;display:flex;align-items:center;justify-content:center;gap:10px;}
        .f-icon{width:26px;height:26px;}
        .f-condition-text{font-size:12px;color:var(--secondary-text-color);width:40px;}
        .f-temp{width:80px;text-align:right;font-size:13px;font-weight:500;}
        .f-low{color:var(--secondary-text-color);margin-left:6px;}
        .data-loading{padding:30px;text-align:center;font-size:13px;color:var(--secondary-text-color);min-height: 100px;display: flex;align-items: center;justify-content: center;}
        .footer {text-align: center;font-size: 10px;color: var(--secondary-text-color);opacity: .6;margin-top: 12px;}
        ha-card > *:last-child { margin-bottom: 0 !important; }
        .attributes-grid-3x2:last-of-type { margin-bottom: 12px; }
      `;
    }

    static getConfigElement() { return document.createElement("qweather-card-pro-editor"); }
  }

  class QWeatherCardProEditor extends Lit {
    static get properties() { return { hass: { type: Object }, config: { type: Object } }; }
    setConfig(c) { this.config = c; }
    set hass(h) {
      this._hass = h;
      if (h) this._detectLang(h);
      if (h && this.config && !Object.prototype.hasOwnProperty.call(this.config, 'entity')) {
        const auto = Object.keys(h.states).find(e => e.startsWith("weather.qweather_pro_") && e.includes("_weather"));
        if (auto) {
          this._valueChanged({ 
            entity: auto,
            show_daily: true,
            show_hourly: true 
          });
        }
      }
    }

    constructor() {
      super();
      this._lang = "en";
    }

    _detectLang(hass) {
      const lang = hass?.selectedLanguage || hass?.language || "en";
      this._lang = I18N[lang] ? lang : "en";
    }

    _t(k) {
      const parts = k.split(".");
      let obj = I18N[this._lang] || I18N.en;
      for (const p of parts) {
        obj = obj?.[p];
        if (!obj) return k;
      }
      return obj;
    }

    _valueChanged(ev) {
      const config = ev?.detail?.value || ev;
      this.dispatchEvent(new CustomEvent("config-changed", {
        detail: { config: { ...this.config, ...config } },
        bubbles: true,
        composed: true,
      }));
    }

    _schema() {
      return [
        { name: "entity", selector: { entity: { domain: "weather", integration: "qweather_pro" } } },
        { name: "show_daily", selector: { boolean: {} } },
        { name: "show_hourly", selector: { boolean: {} } }
      ];
    }

    _computeLabel = (schema) => {
      return this._t(`editor.${schema.name}`);
    };

    render() {
      if (!this._hass || !this.config) return html``;

      return html`
        <ha-form
          .hass=${this._hass}
          .data=${this.config}
          .schema=${this._schema()}
          .computeLabel=${this._computeLabel}
          @value-changed=${this._valueChanged}
        ></ha-form>
      `;
    }
  }

  customElements.define("qweather-card",QWeatherCard);
  customElements.define("qweather-card-pro-editor", QWeatherCardProEditor);

  window.customCards=window.customCards||[];
  window.customCards.push({
    type:"qweather-card",
    name:"QWeather Pro Card",
    preview:true,
    description:"A professional weather card with vertical symmetry and briefing entity selector."
  });
})();