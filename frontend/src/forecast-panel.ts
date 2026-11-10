import {
  createRollingNumber,
  type RollingNumberController,
} from "@kitlangton/rolling-number";
import {
  fetchForecastDashboard,
  fetchForecastStatus,
  stripMarkdown,
  type ForecastDashboard,
} from "./forecast-api";
import { ForecastChart } from "./forecast-chart";
import { escapeHtml } from "./html";

const skeleton =
  '<div class="forecast-skeleton" aria-hidden="true"><i></i><i></i><i></i></div>';
const empty = (text: string) => `<p class="forecast-empty">${text}</p>`;

export function forecastMarkup(): string {
  // 预测弹层现在承载【事件级】视图（指数衰减 + 半衰期 + 传播时序）。
  // 用同源 iframe 直接复用后端已部署的 /api/v1/forecast/ui 页面，
  // 而不是在 3D 终端里再维护一份图表代码 —— 两处数据源和渲染逻辑就不会漂移。
  return `<div class="forecast-body" data-state="ready">
    <header class="forecast-head" data-forecast-reveal>
      <div class="forecast-title">
        <span class="forecast-eyebrow">EVENT OBSERVATORY / 事件观测</span>
        <h2>FORECAST<small>事件热度预测与半衰期</small></h2>
        <p>按单个事件组织：衰减预测、半衰期对比、博文→评论传播时序。</p>
      </div>
    </header>
    <iframe
      class="forecast-frame"
      src="/api/v1/forecast/ui?embedded=1"
      title="事件热度预测与半衰期分析"
      loading="lazy"
      referrerpolicy="same-origin"
    ></iframe>
  </div>`;
}

export interface ForecastMotion {
  surfaces: boolean;
  numbers: boolean;
}

/** Own requests, observers and finite animations for exactly one modal lifetime. */
export function mountForecast(
  _root: HTMLElement,
  _motion: ForecastMotion,
): () => void {
  // 内容由 iframe 内部的页面自行加载，这里不需要再挂图表。
  // 仍返回清理函数，保持 main.ts 的调用契约不变。
  return () => { /* 无需清理 */ };
}
