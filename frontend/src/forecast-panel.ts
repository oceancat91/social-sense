/**
 * 热度预测 · 事件归因面板。
 *
 * 作为三维终端内的一个模态视图（与「设置 / 检索 / 收藏」同级），
 * 不再是独立的 /forecast 页面。图表用 canvas 2D 手绘，不引入 Chart.js。
 */

import { fetchForecastDashboard, fetchForecastStatus, stripMarkdown, type ForecastDashboard, type ForecastStatus } from "./forecast-api";
import { escapeHtml } from "./html";

export interface ForecastElements {
  status: HTMLElement;
  chart: HTMLCanvasElement;
  components: HTMLElement;
  events: HTMLElement;
  report: HTMLElement;
  refresh: HTMLButtonElement;
}

/** 面板骨架。数据由 mountForecast 异步填充。 */
export function forecastMarkup(): string {
  return `<div class="forecast-body">
    <div class="forecast-head">
      <div class="forecast-title">
        <h2>热度预测 <small>FORECAST &amp; ATTRIBUTION</small></h2>
        <p>ŷ = T̂ + Ŝ + Ĉ + R̂ · 历史 28 天 → 预测 6 天</p>
      </div>
      <div class="forecast-actions">
        <span class="forecast-status" id="forecast-status" aria-live="polite">加载中…</span>
        <button type="button" class="ghost" id="forecast-refresh">刷新</button>
      </div>
    </div>

    <section class="forecast-panel">
      <div class="forecast-panel-head">
        <h3>近期热度与 6 日预测</h3>
        <div class="forecast-badges" id="forecast-badges"></div>
      </div>
      <canvas id="forecast-chart" class="forecast-chart" height="220"></canvas>
    </section>

    <div class="forecast-split">
      <section class="forecast-panel">
        <div class="forecast-panel-head"><h3>分量（标准化空间）</h3></div>
        <div class="forecast-components" id="forecast-components"></div>
      </section>

      <section class="forecast-panel">
        <div class="forecast-panel-head"><h3>异常事件（稳健 z）</h3></div>
        <div class="forecast-events" id="forecast-events"></div>
      </section>
    </div>

    <section class="forecast-panel">
      <div class="forecast-panel-head"><h3>AI 归因报告</h3></div>
      <article class="forecast-report" id="forecast-report"></article>
    </section>
  </div>`;
}

function collect(root: HTMLElement): ForecastElements {
  const pick = <T extends Element>(selector: string): T => {
    const el = root.querySelector<T>(selector);
    if (!el) throw new Error(`预测面板缺少元素：${selector}`);
    return el;
  };
  return {
    status: pick<HTMLElement>("#forecast-status"),
    chart: pick<HTMLCanvasElement>("#forecast-chart"),
    components: pick<HTMLElement>("#forecast-components"),
    events: pick<HTMLElement>("#forecast-events"),
    report: pick<HTMLElement>("#forecast-report"),
    refresh: pick<HTMLButtonElement>("#forecast-refresh"),
  };
}

/** 画一条折线图：实线历史 + 虚线预测，带极值与首尾日期标注。 */
function drawChart(canvas: HTMLCanvasElement, dashboard: ForecastDashboard): void {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const cssWidth = canvas.clientWidth || 640;
  const cssHeight = canvas.clientHeight || 220;
  canvas.width = Math.round(cssWidth * dpr);
  canvas.height = Math.round(cssHeight * dpr);
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, cssWidth, cssHeight);

  const history = dashboard.ot;
  const forecast = dashboard.prediction;
  if (history.length === 0 && forecast.length === 0) return;

  const pad = { top: 16, right: 14, bottom: 26, left: 46 };
  const plotW = Math.max(10, cssWidth - pad.left - pad.right);
  const plotH = Math.max(10, cssHeight - pad.top - pad.bottom);

  const all = [...history, ...forecast];
  const min = Math.min(...all);
  const max = Math.max(...all);
  const span = max - min || 1;
  const total = Math.max(1, history.length + forecast.length - 1);

  const xAt = (index: number): number => pad.left + (plotW * index) / total;
  const yAt = (value: number): number => pad.top + plotH * (1 - (value - min) / span);

  const styles = getComputedStyle(canvas);
  const lineColor = styles.getPropertyValue("--forecast-line").trim() || "#ed821b";
  const forecastColor = styles.getPropertyValue("--forecast-predict").trim() || "#6fd3ff";
  const gridColor = styles.getPropertyValue("--forecast-grid").trim() || "rgba(255,255,255,0.12)";
  const textColor = styles.getPropertyValue("--forecast-text").trim() || "rgba(255,255,255,0.55)";

  // 横向网格 + 纵轴刻度
  ctx.strokeStyle = gridColor;
  ctx.fillStyle = textColor;
  ctx.lineWidth = 1;
  ctx.font = "11px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace";
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  for (let i = 0; i <= 3; i += 1) {
    const y = pad.top + (plotH * i) / 3;
    ctx.beginPath();
    ctx.moveTo(pad.left, y);
    ctx.lineTo(pad.left + plotW, y);
    ctx.stroke();
    const value = max - (span * i) / 3;
    ctx.fillText(value.toFixed(1), pad.left - 8, y);
  }

  // 历史
  if (history.length > 1) {
    ctx.beginPath();
    ctx.strokeStyle = lineColor;
    ctx.lineWidth = 1.6;
    ctx.lineJoin = "round";
    history.forEach((value, index) => {
      const x = xAt(index);
      const y = yAt(value);
      if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
  }

  // 预测（从最后一个历史点接出，虚线）
  if (forecast.length > 0) {
    const start = Math.max(0, history.length - 1);
    ctx.beginPath();
    ctx.strokeStyle = forecastColor;
    ctx.lineWidth = 2;
    ctx.setLineDash([5, 4]);
    forecast.forEach((value, index) => {
      const x = xAt(start + index + (history.length ? 1 : 0));
      const y = yAt(value);
      if (index === 0 && history.length > 0) {
        ctx.moveTo(xAt(start), yAt(history[history.length - 1]));
        ctx.lineTo(x, y);
      } else if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
    ctx.setLineDash([]);

    // 预测点
    ctx.fillStyle = forecastColor;
    forecast.forEach((value, index) => {
      const x = xAt(start + index + (history.length ? 1 : 0));
      ctx.beginPath();
      ctx.arc(x, yAt(value), 2.4, 0, Math.PI * 2);
      ctx.fill();
    });
  }

  // 横轴首尾日期
  ctx.fillStyle = textColor;
  ctx.textBaseline = "top";
  ctx.textAlign = "left";
  const firstDate = dashboard.dates[0] ?? "";
  if (firstDate) ctx.fillText(firstDate, pad.left, pad.top + plotH + 8);
  ctx.textAlign = "right";
  const lastDate =
    dashboard.predictionDates[dashboard.predictionDates.length - 1] ??
    dashboard.dates[dashboard.dates.length - 1] ??
    "";
  if (lastDate) ctx.fillText(lastDate, pad.left + plotW, pad.top + plotH + 8);
}

function renderComponents(host: HTMLElement, dashboard: ForecastDashboard): void {
  const components = dashboard.components;
  if (!components) {
    host.innerHTML = `<p class="forecast-muted">无分量数据</p>`;
    return;
  }
  const rows: [string, string, number[]][] = [
    ["T̂", "趋势", components.T],
    ["Ŝ", "季节", components.S],
    ["Ĉ", "冲击", components.C],
    ["R̂", "残差", components.R],
  ];
  host.innerHTML = rows
    .map(([glyph, label, values]) => {
      const mean = values.length ? values.reduce((a, b) => a + b, 0) / values.length : 0;
      const magnitude = Math.min(1, Math.abs(mean) / 4);
      return `<div class="forecast-component">
        <span class="forecast-glyph">${glyph}</span>
        <span class="forecast-label">${label}</span>
        <span class="forecast-bar"><i style="width:${(magnitude * 100).toFixed(1)}%"></i></span>
        <span class="forecast-value">${mean.toFixed(3)}</span>
      </div>`;
    })
    .join("");
}

function renderEvents(host: HTMLElement, dashboard: ForecastDashboard): void {
  if (dashboard.anomalies.length === 0) {
    host.innerHTML = `<p class="forecast-muted">最近窗口内没有异常日</p>`;
    return;
  }
  host.innerHTML = dashboard.anomalies
    .slice(0, 8)
    .map(
      (event) => `<div class="forecast-event">
        <span class="forecast-date">${escapeHtml(event.date)}</span>
        <span class="forecast-z">z=${event.zMax.toFixed(1)}</span>
        <span class="forecast-trigger">${escapeHtml(event.trigger)}</span>
        <span class="forecast-ot">OT ${event.ot.toLocaleString("zh-CN")}</span>
      </div>`,
    )
    .join("");
}

function renderBadges(host: HTMLElement, dashboard: ForecastDashboard): void {
  const badges: string[] = [];
  if (dashboard.direction) {
    const up = dashboard.direction === "up";
    badges.push(
      `<span class="forecast-badge ${up ? "up" : "down"}">${up ? "↑" : "↓"} ${up ? "看涨" : "看跌"}${
        dashboard.directionDelta !== null ? ` ${dashboard.directionDelta.toFixed(2)}` : ""
      }</span>`,
    );
  }
  if (dashboard.spikeWarning) {
    badges.push(
      `<span class="forecast-badge warn">尖峰预警${
        dashboard.spikeGain !== null ? ` +${dashboard.spikeGain.toFixed(2)}` : ""
      }</span>`,
    );
  }
  host.innerHTML = badges.join("");
}

/** 挂载：拉数据 → 渲染。任何失败都只影响面板自身。 */
export async function mountForecast(root: HTMLElement): Promise<void> {
  const el = collect(root);

  /** 拉一次数据。可重试：部署重启后端时会出现极短窗口的瞬时失败。 */
  const fetchOnce = async (): Promise<ForecastDashboard> => fetchForecastDashboard();

  const load = async (): Promise<void> => {
    el.status.textContent = "加载中…";
    el.status.className = "forecast-status";
    el.refresh.disabled = true;
    try {
      // 先看模型状态：未加载时给出明确原因，而不是让图表空着。
      let status: ForecastStatus | null = null;
      try {
        status = await fetchForecastStatus();
      } catch {
        status = null;
      }
      if (status && !status.modelLoaded) {
        el.status.textContent = `模型未加载${status.loadError ? `：${status.loadError}` : ""}`;
        el.status.className = "forecast-status warn";
      }

      // 首次失败自动重试一次（800ms 后），盖住后端重启的瞬时不可用。
      let dashboard: ForecastDashboard;
      try {
        dashboard = await fetchOnce();
      } catch {
        el.status.textContent = "网络不稳定，正在重试…";
        el.status.className = "forecast-status warn";
        await new Promise((resolve) => setTimeout(resolve, 800));
        dashboard = await fetchOnce();
      }

      renderBadges(document.getElementById("forecast-badges") ?? el.status, dashboard);
      drawChart(el.chart, dashboard);
      renderComponents(el.components, dashboard);
      renderEvents(el.events, dashboard);
      el.report.textContent = stripMarkdown(dashboard.reportMarkdown) || "尚无归因报告，请先运行 workflow。";

      if (status && status.modelLoaded) {
        el.status.textContent = status.checkpointName ? `模型就绪 · ${status.checkpointName}` : "模型就绪";
        el.status.className = "forecast-status ok";
      } else if (!status) {
        el.status.textContent = "已取到预测数据（模型状态未知）";
        el.status.className = "forecast-status";
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      el.status.textContent = `取数失败：${message}（点「刷新」重试）`;
      el.status.className = "forecast-status error";
      el.report.textContent = "预测数据暂时不可用。可能是后端正在重启、未安装 numpy/torch，或权重未就位。";
    } finally {
      el.refresh.disabled = false;
    }
  };

  el.refresh.addEventListener("click", () => void load());
  // 模态的 clientWidth 在插入后下一帧才有效，所以首屏用 rAF 触发。
  // 不挂 window resize 监听：每次打开模态都会新建 DOM，挂了会累积。
  requestAnimationFrame(() => void load());
}
