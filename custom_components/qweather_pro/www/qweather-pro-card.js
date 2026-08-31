/** QWeather Dashboard Card - Pro */
(async () => {
  if (!window.LitElement && !customElements.get("ha-card")) {
    await customElements.whenDefined("ha-card");
  }
  const Lit = window.LitElement || Object.getPrototypeOf(customElements.get("ha-card"));
  const html = Lit.prototype.html;
  const css = Lit.prototype.css;
  const CARD_VERSION = "v2.0.0-svg";

  console.log(
    `%cQWeather Pro Card ${CARD_VERSION} (no-bundle)`,
    "color: #1976d2; font-weight: bold; background: #e3f2fd; border: 1px solid #1976d2; border-radius: 4px; padding: 2px 6px;"
  );


  const getI18N = () => window.QW_I18N || {};
  const _richCache = new Map();            // entity_id -> { data, ts }
  const RICH_CACHE_TTL = 10 * 60 * 1000;   // 10 分钟内命中缓存直接复用
  const RICH_MIN_REFRESH = 60 * 1000;      // 最小刷新间隔，过滤订阅建立时的立即推送

  // --- 图表常量 ---
  const CHART_H = 180;          // 图表高度（px）
  const CHART_PAD_T = 26;       // 顶部留白（容纳数据标签）
  const CHART_PAD_B = 22;       // 底部留白（容纳 X 轴标签）
  const CHART_PAD_X = 10;       // 左右留白
  const HOURLY_WINDOW = 10;     // 时视图默认最多显示的小时数
  const SMOOTH_TENSION = 0.2;   // 平滑曲线张力（Catmull-Rom 系）
const SVG_NS = "http://www.w3.org/2000/svg";

  class QWeatherCard extends Lit {
    static get properties() {
      return {
        hass: {}, config: {},
        _forecastDaily: { state: true },
        _forecastHourly: { state: true },
        _warningOpen: { state: true },
        _weather: { state: true },
        _richData: { state: true },
        _selectedTab: { state: true },
        _lang: { state: true },
        _chartW: { state: true },
        _view: { state: true },
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
      // i18n 资源可能晚于卡片加载：记录是否已就绪，就绪后触发一次重绘刷新译文
      this._i18nReady = !!window.QW_I18N;
      this._richData = {};
      this._richDebounce = null;
      // 图表：_view 为 null 表示使用默认视窗（全部 / 前 10 小时）
      this._chartW = 600;
      this._view = null;
      this._uid = "qw" + Math.random().toString(36).slice(2, 9);
      this._drag = null;
      this._ro = null;
      this._eventsBound = null;
    }

    updated(changedProps) {
      super.updated(changedProps);
      if (this.config?.forecast_style !== "curve") return;
      // 仅在图表相关数据变化时重绘，避免 hass 每次推送都重建 SVG
      const need = ["_forecastDaily", "_forecastHourly", "_selectedTab", "_chartW", "config"];
      if (need.some((k) => changedProps.has(k))) this._drawChart();
    }

    disconnectedCallback() {
      clearTimeout(this._richDebounce);
      const wrap = this.shadowRoot?.getElementById("chart-wrapper");
      if (wrap && this._onWheel) wrap.removeEventListener("wheel", this._onWheel);
      if (this._ro) { this._ro.disconnect(); this._ro = null; }
      this._clearSubs();
      super.disconnectedCallback();
    }

    _detectLang(hass) {
      const lang = hass.selectedLanguage || hass.language || "en";
      this._lang = getI18N()[lang] ? lang : "en";
    }

    _t(k) {
      const parts = k.split(".");
      let obj = getI18N()[this._lang] || getI18N().en || {};
      for (const p of parts) { obj = obj?.[p]; if (!obj) return k; }
      return obj;
    }

    /** 风向翻译：V1 compass 为大写缩写 (N/NNE/...)，i18n wd 键为小写，需归一化 */
    _wd(dir) {
      if (!dir) return "--";
      const key = String(dir).toLowerCase();
      const t = this._t(`wd.${key}`);
      return t === `wd.${key}` ? dir : t;
    }

    static getGridOptions() { return { rows: "auto", columns: 12 }; }

    static getStubConfig(hass) {
      const auto = Object.keys(hass.states).find((e) => e.startsWith("weather.qweather_pro_"));
      return { type: "custom:qweather-pro-card", entity: auto || "", show_daily: true, show_hourly: true, show_warnings: true, forecast_style: "list" };
    }

    setConfig(config) {
      if (!config) throw new Error("Invalid configuration");
      this.config = { show_daily: true, show_hourly: true, show_warnings: true, forecast_style: "list", ...config };
      if (this.config.show_daily && !this.config.show_hourly) this._selectedTab = "daily";
      else if (!this.config.show_daily && this.config.show_hourly) this._selectedTab = "hourly";
    }

    set hass(hass) {
      this._hass = hass;
      this._detectLang(hass);
      // i18n 资源晚到：一旦 window.QW_I18N 就绪，强制重绘以刷新译文（避免持续显示翻译键）
      if (window.QW_I18N && !this._i18nReady) {
        this._i18nReady = true;
        this.requestUpdate();
      }
      const eid = this.config.entity;
      if (!eid) return;

      const st = hass.states[eid];
      if (st && (!this._weather || this._weather.entity_id !== st.entity_id)) {
        this._weather = st;
        this._subscribeForecasts();
        this._fetchRichData();
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
          (m) => { this._forecastDaily = m.forecast; this._fetchRichData(true); },
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

    /** 通过自定义服务 qweather_pro.get_weather 获取实体属性中已剔除的富数据块
     * @param {boolean} force 是否强制刷新（订阅推送时 true）
     */
    _fetchRichData(force = false) {
      const eid = this.config.entity;
      if (!eid || !this._hass) return;

      const cached = _richCache.get(eid);
      const now = Date.now();
      if (cached && now - cached.ts < RICH_CACHE_TTL) {
        if (!force || now - cached.ts < RICH_MIN_REFRESH) {
          this._richData = cached.data;
          this.requestUpdate();
          return;
        }
      }

      clearTimeout(this._richDebounce);
      this._richDebounce = setTimeout(async () => {
        try {
          const result = await this._hass.callWS({
            type: "call_service",
            domain: "qweather_pro",
            service: "get_weather",
            service_data: { keys: ["aqi", "warning", "weather_abstract"] },
            target: { entity_id: eid },
            return_response: true,
          });
          const data = result?.response ?? result ?? {};
          this._richData = data;
          _richCache.set(eid, { data, ts: Date.now() });
          this.requestUpdate();
        } catch (e) {
          console.error("QWeather get_weather service failed:", e);
        }
      }, 200);
    }

    _handleTabClick(e, tab) {
      e.stopPropagation();
      if (this._selectedTab === tab) return;
      this._selectedTab = tab;
      this._view = null;   // 切换日/时视图时回到默认视窗
    }

    _getIcon(code, datetime = null) {
      if (!code) return "https://static.qweather.com/img/common/icon/202106d/100.png";
      let isDay = true;
      if (datetime) {
        const hour = new Date(datetime).getHours();
        isDay = hour >= 6 && hour < 18;
      }
      return `https://static.qweather.com/img/common/icon/202106${isDay ? "d" : "n"}/${code}.png`;
    }

    _formatDate(dt) {
      const d = new Date(dt);
      if (d.getDate() === new Date().getDate()) return this._t("today");
      const weekday = (getI18N()[this._lang] || getI18N().en || {}).weekday || [];
      return weekday[d.getDay()] || dt;
    }

    _formatTime(dt) {
      const h = new Date(dt).getHours();
      return (h < 10 ? "0" + h : h) + ":00";
    }

    _mapAqiLevel(aqi) {
      const v = parseInt(aqi);
      if (isNaN(v)) return 1;
      if (v <= 50) return 1; if (v <= 100) return 2; if (v <= 150) return 3;
      if (v <= 200) return 4; if (v <= 300) return 5; return 6;
    }

    _renderBriefing() {
      const d = this._richData?.weather_abstract;
      if (!d) return this._t("loading") || "—";
      const zh = this._lang.startsWith("zh");
      const period = this._t(`period.${d.period}`);
      const tempTrend = `${this._t("temp_change_prefix")}${this._t(`temp_change_type.${d.temp_change_type}`)}`;
      const currentTemp = `${this._t("now_is")}${d.current_temp}°C`;
      const wind_status = this._t(`wind_status.${d.wind_status}`);
      const aqi_level = this._t(`aqi_level.${d.aqi_level}`);
      const tonightText = d.tonight_text || "";
      return zh
        ? `${period}${tonightText}，${tempTrend}。${currentTemp}，${wind_status}，${aqi_level}。`
        : `${period} ${tonightText}, ${tempTrend}. ${currentTemp}, ${wind_status}, ${aqi_level}.`;
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
          ${this._renderAttr("mdi:compass", this._t("wind_dir"), this._wd(a.wind_dir))}
          ${this._renderAttr("mdi:weather-sunny-alert", this._t("uv_index"), a.uv_index || "--")}
        </div>`;
    }

    // ==================== 预报数据（两种样式共用） ====================
    _forecastData() {
      return this._selectedTab === "daily" ? this._forecastDaily : this._forecastHourly;
    }

    /** 当前系列定义：日视图为最高/最低温双线，时视图为单温度线 */
    _series() {
      return this._selectedTab === "daily"
        ? [{ key: "temperature", color: "#ff9800" }, { key: "templow", color: "#2196f3" }]
        : [{ key: "temperature", color: "#03a9f4" }];
    }

    /** 当前视窗索引区间 [start, end]（已钳制到合法范围） */
    _range(n) {
      const isDaily = this._selectedTab === "daily";
      const defEnd = isDaily ? n - 1 : Math.min(HOURLY_WINDOW - 1, n - 1);
      let s = this._view?.s ?? 0;
      let e = this._view?.e ?? defEnd;
      s = Math.max(0, Math.min(s, n - 1));
      e = Math.max(s, Math.min(e, n - 1));
      return [s, e];
    }

    // ==================== 样式一：原生 SVG 曲线 ====================
    /** 生成平滑路径（Catmull-Rom 转三次贝塞尔），点数不足时退化为折线 */
    _smoothPath(pts) {
      if (!pts.length) return "";
      if (pts.length < 3) return "M" + pts.map((p) => `${p.x},${p.y}`).join("L");
      let d = `M${pts[0].x},${pts[0].y}`;
      const t = SMOOTH_TENSION;
      for (let i = 0; i < pts.length - 1; i++) {
        const p0 = pts[i - 1] || pts[i];
        const p1 = pts[i];
        const p2 = pts[i + 1];
        const p3 = pts[i + 2] || p2;
        const c1x = p1.x + (p2.x - p0.x) * t;
        const c1y = p1.y + (p2.y - p0.y) * t;
        const c2x = p2.x - (p3.x - p1.x) * t;
        const c2y = p2.y - (p3.y - p1.y) * t;
        d += `C${c1x},${c1y} ${c2x},${c2y} ${p2.x},${p2.y}`;
      }
      return d;
    }

    _drawChart() {
      const wrap = this.shadowRoot?.getElementById("chart-wrapper");
      if (!wrap) return;
      this._bindChartEvents(wrap);

      const data = this._forecastData();
      if (!data || data.length === 0) { wrap.replaceChildren(); return; }

      const n = data.length;
      const [s, e] = this._range(n);
      const vis = e - s + 1;
      const W = Math.max(200, this._chartW || 600);
      const innerW = W - CHART_PAD_X * 2;
      const innerH = CHART_H - CHART_PAD_T - CHART_PAD_B;
      const series = this._series();

      // Y 范围：仅统计可见区间内的数值（缩放时自动适配，等价 autoScaleYaxis）
      let min = Infinity, max = -Infinity;
      for (const sr of series) {
        for (let i = s; i <= e; i++) {
          const v = Number(data[i]?.[sr.key]);
          if (Number.isFinite(v)) { if (v < min) min = v; if (v > max) max = v; }
        }
      }
      if (!Number.isFinite(min) || !Number.isFinite(max)) { min = 0; max = 1; }
      if (max - min < 1) { max = min + 1; }
      const padY = (max - min) * 0.15;
      min -= padY; max += padY;

      const xOf = (i) => CHART_PAD_X + (vis === 1 ? innerW / 2 : ((i - s) * innerW) / (vis - 1));
      const yOf = (v) => CHART_PAD_T + innerH - ((v - min) / (max - min)) * innerH;

      // 标签密度控制：点密集时按步长采样，避免重叠
      const labelStep = vis > 10 ? Math.ceil(vis / 8) : 1;
      const tickStep = Math.max(1, Math.ceil(vis / 7));
      const PAD_X = 4, PAD_Y = 2;

      const el = (tag, attrs) => {
        const node = document.createElementNS(SVG_NS, tag);
        for (const k in attrs) node.setAttribute(k, attrs[k]);
        return node;
      };

      const svg = el("svg", { class: "chart", viewBox: `0 0 ${W} ${CHART_H}`, preserveAspectRatio: "none" });

      const defs = el("defs", {});
      series.forEach((sr, si) => {
        const lg = el("linearGradient", { id: `${this._uid}-g${si}`, x1: "0", y1: "0", x2: "0", y2: "1" });
        lg.appendChild(el("stop", { offset: "0%", "stop-color": sr.color, "stop-opacity": "0.35" }));
        lg.appendChild(el("stop", { offset: "100%", "stop-color": sr.color, "stop-opacity": "0.03" }));
        defs.appendChild(lg);
      });
      svg.appendChild(defs);

      const baseY = CHART_PAD_T + innerH;
      series.forEach((sr, si) => {
        const pts = [];
        for (let i = s; i <= e; i++) {
          const v = Number(data[i]?.[sr.key]);
          if (Number.isFinite(v)) pts.push({ i, x: xOf(i), y: yOf(v), v: Math.round(v) });
        }
        if (!pts.length) return;
        const line = this._smoothPath(pts);
        const first = pts[0], last = pts[pts.length - 1];
        svg.appendChild(el("path", {
          d: `${line}L${last.x},${baseY}L${first.x},${baseY}Z`,
          fill: `url(#${this._uid}-g${si})`,
        }));
        svg.appendChild(el("path", {
          d: line, fill: "none", stroke: sr.color, "stroke-width": "3",
          "stroke-linecap": "round", "stroke-linejoin": "round",
        }));
        pts.forEach((p, k) => {
          if (k % labelStep !== 0 && k !== pts.length - 1) return;
          const label = `${p.v}°`;
          const Yb = p.y - 10;                       // 文字基线（点上方，留出与曲线距离）
          const tw = label.length * 6.2, th = 11;
          const bg = el("rect", {
            class: "pt-label-bg",
            x: p.x - tw / 2 - PAD_X,
            y: Yb - 9 - PAD_Y,                       // 垂直居中于文字包围盒
            width: tw + PAD_X * 2,
            height: th + PAD_Y * 2,
            rx: 3,
          });
          svg.appendChild(bg);
          const t = el("text", { class: "pt-label", x: p.x, y: Yb, "text-anchor": "middle" });
          t.textContent = label;
          svg.appendChild(t);
        });
      });

      for (let i = s; i <= e; i++) {
        if ((i - s) % tickStep !== 0 && i !== e) continue;
        const label = this._selectedTab === "daily"
          ? this._formatDate(data[i].datetime)
          : this._formatTime(data[i].datetime);
        const t = el("text", { class: "ax-label", x: xOf(i), y: CHART_H - 6, "text-anchor": "middle" });
        t.textContent = label;
        svg.appendChild(t);
      }

      wrap.replaceChildren(svg);
    }

    /** 绑定图表交互：切换样式后 wrapper 是新节点，需按元素重新绑定 */
    _bindChartEvents(wrap) {
      if (this._eventsBound === wrap) return;

      if (this._eventsBound && this._onWheel) {
        this._eventsBound.removeEventListener("wheel", this._onWheel);
      }
      if (!this._onWheelBound) { this._onWheel = this._onWheel.bind(this); this._onWheelBound = true; }
      // wheel 需 passive:false 才能 preventDefault，模板绑定无法指定
      wrap.addEventListener("wheel", this._onWheel, { passive: false });
      this._eventsBound = wrap;

      if (this._ro) this._ro.disconnect();
      // 先同步测一次：ResizeObserver 回调在下一帧，晚一帧会短暂拉伸（viewBox 用实际像素）
      const w0 = Math.round(wrap.getBoundingClientRect().width);
      if (w0 > 0) this._chartW = w0;
      if (typeof ResizeObserver !== "undefined") {
        this._ro = new ResizeObserver((entries) => {
          const w = Math.round(entries[0].contentRect.width);
          if (w > 0 && Math.abs(w - this._chartW) > 2) this._chartW = w;
        });
        this._ro.observe(wrap);
      }
    }

    _onWheel(ev) {
      const data = this._forecastData();
      if (!data || data.length === 0) return;
      ev.preventDefault();
      ev.stopPropagation();

      const n = data.length;
      const [s, e] = this._range(n);
      const span = e - s + 1;

      // 以指针位置为锚点缩放：保持锚点下的数据点不动
      const rect = ev.currentTarget.getBoundingClientRect();
      const ratio = rect.width ? (ev.clientX - rect.left) / rect.width : 0.5;
      const anchor = s + ratio * (span - 1);

      const factor = ev.deltaY > 0 ? 1.2 : 1 / 1.2;   // 下滚缩小（显示更多），上滚放大
      const nextSpan = Math.max(2, Math.min(n, Math.round(span * factor)));
      if (nextSpan === span) return;

      let ns = Math.round(anchor - ratio * (nextSpan - 1));
      let ne = ns + nextSpan - 1;
      if (ns < 0) { ns = 0; ne = nextSpan - 1; }
      if (ne > n - 1) { ne = n - 1; ns = Math.max(0, ne - nextSpan + 1); }
      this._view = { s: ns, e: ne };
      this._drawChart();
    }

    _onPointerDown(ev) {
      const data = this._forecastData();
      if (!data || data.length === 0) return;
      this._drag = { x: ev.clientX, s: this._view?.s, e: this._view?.e, n: data.length };
      try { ev.currentTarget.setPointerCapture(ev.pointerId); } catch (_) { /* 忽略捕获失败 */ }
    }

    _onPointerMove(ev) {
      if (!this._drag) return;
      const { x, s, e, n } = this._drag;
      const [cs, ce] = this._range(n);
      const start = s ?? cs, end = e ?? ce;
      const span = end - start + 1;
      const W = Math.max(200, this._chartW || 600);
      const perPx = span / (W - CHART_PAD_X * 2);
      let delta = Math.round((ev.clientX - x) * perPx);
      if (delta === 0) return;

      // 拖拽向右→视窗左移（内容跟随手指）
      let ns = start - delta;
      let ne = end - delta;
      if (ns < 0) { ne -= ns; ns = 0; }
      if (ne > n - 1) { ns -= ne - (n - 1); ne = n - 1; }
      ns = Math.max(0, ns);
      this._view = { s: ns, e: ne };
      this._drawChart();
      this._drag = { ...this._drag, s: ns, e: ne };
    }

    _onPointerUp(ev) {
      if (!this._drag) return;
      this._drag = null;
      try { ev.currentTarget.releasePointerCapture(ev.pointerId); } catch (_) { /* 已释放 */ }
    }

    /** 重置视窗：清空自定义区间即回到默认（日视图全部 / 时视图前 10 小时） */
    _handleChartReset(e) {
      e.stopPropagation();
      this._view = null;
      this._drawChart();
    }

    // ==================== 样式二：列表（横向滚动） ====================
    _renderList() {
      const data = this._forecastData();
      if (!data || data.length === 0) return html``;
      const isDaily = this._selectedTab === "daily";

      return html`
        <div class="fc-list">
          ${data.map((d) => {
            const icon = isDaily ? (d.daytime?.icon || d.icon) : d.icon;
            const hi = Math.round(Number(d.temperature));
            const lo = isDaily ? Math.round(Number(d.templow)) : null;
            return html`
              <div class="fc-item">
                <div class="fc-time">${isDaily ? this._formatDate(d.datetime) : this._formatTime(d.datetime)}</div>
                <img class="fc-icon" src=${this._getIcon(icon, d.datetime)} alt="">
                <div class="fc-temp">
                  <span class="fc-hi">${Number.isFinite(hi) ? hi : "--"}°</span>
                  ${isDaily && Number.isFinite(lo) ? html`<span class="fc-lo">${lo}°</span>` : ""}
                </div>
              </div>`;
          })}
        </div>`;
    }

    // ==================== 主渲染 ====================
    render() {
      if (!this._weather) return html`<ha-card class="loading">${this._t("loading")}</ha-card>`;
      const a = this._weather.attributes;
      const isDaily = this._selectedTab === "daily";
      const showAny = this.config.show_daily || this.config.show_hourly;
      const isCurve = this.config.forecast_style === "curve";

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
              <div class="aqi-tag air-tag air-tag--${this._mapAqiLevel(this._richData?.aqi?.aqi)}">
                AQI ${this._richData?.aqi?.category || "--"}
              </div>
            </div>
          </div>

          ${this.config.show_warnings && this._richData?.warning?.length ? this._richData.warning.map((w, i) => html`
            <div class="warning-section" style="background-color:${this._getWarningColor(w.color)}">
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
                <span class="brief-value">${this._renderBriefing()}</span>
              </div>
            </div>
          </div>

          ${this._renderSixAttributes(a)}

          ${showAny ? html`
            <div class="tabs">
              ${this.config.show_daily ? html`<div class="tab ${isDaily ? "active" : ""}" @click=${e => this._handleTabClick(e, "daily")}>${this._t("daily_forecast")}</div>` : ""}
              ${this.config.show_hourly ? html`<div class="tab ${!isDaily ? "active" : ""}" @click=${e => this._handleTabClick(e, "hourly")}>${this._t("hourly_forecast")}</div>` : ""}
              ${isCurve ? html`<div class="tab-reset" @click=${e => this._handleChartReset(e)} title="重置视图"><ha-icon icon="mdi:refresh"></ha-icon></div>` : ""}
            </div>
            ${isCurve
              ? html`<div id="chart-wrapper" @click=${e => e.stopPropagation()}
                           @pointerdown=${this._onPointerDown} @pointermove=${this._onPointerMove}
                           @pointerup=${this._onPointerUp} @pointercancel=${this._onPointerUp}></div>`
              : this._renderList()}
          ` : ""}

          <div class="footer">
            ${this._t("data_source")}: QWeather | ${this._t("update_at")}: ${a.update_time?.split(" ")[1] || ""}
          </div>
        </ha-card>`;
    }

    _getWarningColor(c) {
      const m = { "blue": "#2196f3", "yellow": "#fdd835", "orange": "#ff9800", "red": "#f44336" };
      return m[c] || "#f44336";
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
        .header-right{display:flex;flex-direction:column;align-items:center;}
        .weather-icon-circle{width:56px;height:56px;margin-right:16px;border-radius:50%;background:var(--secondary-background-color);display:flex;align-items:center;justify-content:center;}
        .weather-icon-circle img{width:36px;height:36px;}
        .condition-state{font-size:22px;font-weight:500;}
        .current-temp{font-size:34px;font-weight:300;line-height:1;}
        .current-temp span{font-size:16px;vertical-align:top;margin-left:2px;}
        .air-tag {display:inline-block;padding:4px 10px;font-size:13px;line-height:16px;text-align:center;white-space:nowrap;border-radius:14px;color:white;width:fit-content;}
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
        .tab-reset{margin-left:auto;display:flex;align-items:center;padding:0 6px;cursor:pointer;color:var(--secondary-text-color);--mdc-icon-size:18px;}
        .tab-reset:hover{color:var(--primary-color);}
        #chart-wrapper{height:${CHART_H}px;width:100%;margin:8px 0;touch-action:none;}
        .chart{width:100%;height:${CHART_H}px;display:block;}
        .pt-label{font-size:10px;fill:var(--primary-text-color);}
      .pt-label-bg{fill:var(--primary-text-color);fill-opacity:.3;}
        .ax-label{font-size:10px;fill:var(--secondary-text-color);}
        .fc-list{display:flex;overflow-x:auto;gap:6px;padding:6px 0;margin:8px 0;}
        .fc-item{flex:0 0 auto;min-width:54px;display:flex;flex-direction:column;align-items:center;gap:2px;padding:4px 2px;}
        .fc-time{font-size:11px;color:var(--secondary-text-color);white-space:nowrap;}
        .fc-icon{width:32px;height:32px;}
        .fc-temp{font-size:13px;display:flex;gap:4px;}
        .fc-hi{font-weight:500;}
        .fc-lo{color:var(--secondary-text-color);}
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
        if (auto) this._valueChanged({ entity: auto, show_daily: true, show_hourly: true, show_warnings: true, forecast_style: "list" });
      }
    }
    _valueChanged(ev) {
      const config = ev?.detail?.value || ev;
      this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: { ...this.config, ...config } }, bubbles: true, composed: true }));
    }
    render() {
      if (!this._hass || !this.config) return html``;
      const lang = this._hass.selectedLanguage || this._hass.language || "en";
      const i18n = getI18N()[lang] || getI18N().en || { editor: {} };
      return html`
        <ha-form
          .hass=${this._hass}
          .data=${this.config}
          .schema=${[
            { name: "name", selector: { text: {} } },
            { name: "entity", selector: { entity: { domain: "weather", integration: "qweather_pro" } } },
            { name: "forecast_style", selector: { select: { mode: "dropdown", options: [
              { value: "list", label: i18n.editor.forecast_style_list || "List" },
              { value: "curve", label: i18n.editor.forecast_style_curve || "Curve" }
            ] } } },
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
    description:"A professional weather card with native-SVG forecasts, zero bundled dependencies."
  });
})();