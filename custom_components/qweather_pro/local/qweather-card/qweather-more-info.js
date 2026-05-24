/**
 * QWeather More Info - Suggestion Focused Version (2026.5 Optimized)
 */
(async () => {
  // 必须确保 HA 的基础组件已加载
  await customElements.whenDefined("ha-card");

  const LitElement = window.LitElement || Object.getPrototypeOf(customElements.get("ha-card"));
  const html = LitElement.prototype.html;
  const css = LitElement.prototype.css;

  class QWeatherMoreInfo extends LitElement {
    static get properties() {
      return {
        hass: { type: Object },
        // 关键：HA 详情弹窗默认传递的对象名是 stateObj
        stateObj: { type: Object }
      };
    }

    render() {
      // 如果没有拿到数据对象，显示加载状态而非空白
      if (!this.stateObj) {
        return html`<div style="padding: 30px; text-align: center;">正在同步天气详情...</div>`;
      }

      const attr = this.stateObj.attributes;

      // 数据清洗：处理 AQI 对象结构
      const aqiVal = attr.aqi?.aqi || '--';
      const aqiCat = attr.aqi?.category || '未知';

       // 指数筛选
      const primaryTypes = ["comf", "drsg", "uv", "sport", "flu", "cw", "dc", "trav"];
      const suggestions = (attr.suggestion || [])
        .filter(s => primaryTypes.includes(s.type))
        .slice(0, 8);

      return html`
        <div class="content">
          <div class="header-row">
            <div class="main-info">
              <div class="weather-icon" style="background-image: url(${this._getIcon(attr.qweather_icon)})"></div>
              <div>
                <div class="state-text">${attr.condition_cn || this.stateObj.state}</div>
                <div class="obs-time">观测时间: ${attr.obs_time || '--'}</div>
              </div>
            </div>
            <div class="temp-text">${Math.round(attr.temperature)}<sup>°C</sup></div>
          </div>

          <div class="attr-grid">
            ${this._renderAttr('mdi:water-percent', '湿度', `${attr.humidity}%`)}
            ${this._renderAttr('mdi:thermometer-plus', '体感', `${attr.feels_like}°C`)}
            ${this._renderAttr('mdi:weather-windy', '风向风力', `${attr.wind_dir} ${attr.wind_scale}级`)}
            ${this._renderAttr('mdi:air-filter', '空气质量', `${aqiVal} ${aqiCat}`)}
          </div>

          <div class="section-title">生活指数建议</div>
          <div class="suggestion-list">
            ${suggestions.length === 0 ? html`<div class="no-data">暂无指数信息</div>` : ''}
            ${suggestions.map(s => html`
              <div class="suggestion-row">
                <div class="s-header">
                  <span class="s-name">${s.title_cn || s.title}</span>
                  <span class="s-brf">${s.brf}</span>
                </div>
                <span class="s-text">${s.txt || s.text}</span>
              </div>
            `)}
          </div>

          <div class="footer">
            数据源: QWeather | 更新于: ${attr.update_time || '刚刚'}
          </div>
        </div>
      `;
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

    _getIcon(code) {
      return `/qweather-local/qweather-card/icons/${code || '100'}.svg`;
    }

    static get styles() {
      return css`
        .content { padding: 0 16px 20px 16px; color: var(--primary-text-color); }
        .header-row { display: flex; justify-content: space-between; align-items: center; padding: 20px 0; }
        .main-info { display: flex; align-items: center; }
        .weather-icon { width: 64px; height: 64px; background-size: contain; margin-right: 16px; background-repeat: no-repeat; background-position: center; }
        .state-text { font-size: 24px; font-weight: 500; }
        .obs-time { font-size: 12px; opacity: 0.6; margin-top: 4px; }
        .temp-text { font-size: 44px; font-weight: 300; }
        .temp-text sup { font-size: 20px; }

        .attr-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 24px; }
        .attr-item { background: var(--secondary-background-color); padding: 12px 14px; border-radius: 12px; display: flex; align-items: center; }
        .attr-item ha-icon { margin-right: 12px; color: var(--primary-color); --mdc-icon-size: 22px; }
        .attr-label { font-size: 11px; color: var(--secondary-text-color); }
        .attr-value { font-size: 15px; font-weight: 600; }

        .section-title { font-size: 16px; font-weight: bold; margin: 20px 0 12px 0; }
        .suggestion-list { display: flex; flex-direction: column; gap: 10px; }
        .suggestion-row { padding: 14px; border-radius: 12px; border-left: 5px solid var(--primary-color); background: var(--secondary-background-color); }
        .s-header { display: flex; justify-content: space-between; margin-bottom: 6px; font-weight: bold; }
        .s-name { font-size: 14px; }
        .s-brf { color: var(--primary-color); font-size: 14px; }
        .s-text { color: var(--secondary-text-color); font-size: 13px; line-height: 1.5; display: block; }
        .no-data { text-align: center; opacity: 0.5; padding: 20px; }
        .footer { text-align: center; font-size: 10px; color: var(--secondary-text-color); margin-top: 25px; opacity: 0.6; }
      `;
    }
  }

  // 注册组件
  if (!customElements.get("qweather-more-info")) {
    customElements.define("qweather-more-info", QWeatherMoreInfo);
  }
})();