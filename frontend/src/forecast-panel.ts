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
  return `<div class="forecast-body" data-state="loading" aria-busy="true">
    <header class="forecast-head" data-forecast-reveal>
      <div class="forecast-title">
        <span class="forecast-eyebrow">SIGNAL OBSERVATORY / 舆情观测</span>
        <h2>FORECAST<small>热度预测与归因</small></h2>
        <p>从历史信号，读懂下一次变化。</p>
      </div>
      <div class="forecast-actions">
        <span class="forecast-status" id="forecast-status" role="status">正在连接预测数据</span>
        <button type="button" class="forecast-refresh" id="forecast-refresh" disabled><span>刷新数据</span><span class="forecast-refresh-icon" aria-hidden="true">↻</span></button>
      </div>
    </header>
    <section class="forecast-metrics" aria-label="预测摘要" data-forecast-reveal>
      <div class="forecast-metric"><span class="forecast-eyebrow">LATEST / 最新观测</span><strong id="forecast-latest">—</strong><small id="forecast-latest-date">等待历史数据</small></div>
      <div class="forecast-metric"><span class="forecast-eyebrow">OUTLOOK / 预测终点</span><strong id="forecast-outlook">—</strong><small id="forecast-outlook-date">等待预测数据</small></div>
      <div class="forecast-metric"><span class="forecast-eyebrow">EVENTS / 异常事件</span><strong id="forecast-count">—</strong><small id="forecast-window">当前观测窗口</small></div>
    </section>
    <section class="forecast-panel forecast-trend" data-forecast-reveal>
      <div class="forecast-panel-head"><h3><span class="forecast-section-no">01</span>热度轨迹</h3><div class="forecast-badges" id="forecast-badges"></div></div>
      <div class="forecast-chart-meta"><span id="forecast-range">正在读取观测窗口</span><div class="forecast-legend"><span>历史观测</span><span>未来预测</span></div></div>
      <div class="forecast-chart-wrap">
        <canvas id="forecast-chart" class="forecast-chart" height="240" role="img" aria-label="热度曲线，等待数据" aria-describedby="forecast-readout"></canvas>
        <div class="forecast-chart-message" id="forecast-chart-message"><span class="forecast-scan" aria-hidden="true"></span><span>正在读取热度序列</span></div>
      </div>
      <p class="forecast-chart-readout" id="forecast-readout" aria-live="off">历史实线 / 预测虚线</p>
    </section>
    <div class="forecast-split">
      <section class="forecast-panel" data-forecast-reveal>
        <div class="forecast-panel-head"><h3><span class="forecast-section-no">02</span>信号分解</h3><span class="forecast-note">标准化均值</span></div>
        <div class="forecast-components" id="forecast-components">${skeleton}</div>
        <p class="forecast-formula">ŷ = T̂ + Ŝ + Ĉ + R̂ <span>趋势 / 季节 / 冲击 / 残差</span></p>
      </section>
      <section class="forecast-panel" data-forecast-reveal>
        <div class="forecast-panel-head"><h3><span class="forecast-section-no">03</span>异常事件</h3><span class="forecast-note">稳健 z 分数</span></div>
        <div class="forecast-events" id="forecast-events">${skeleton}</div>
      </section>
    </div>
    <section class="forecast-panel forecast-report-panel" data-forecast-reveal>
      <div class="forecast-panel-head"><h3><span class="forecast-section-no">04</span>AI 归因报告</h3><span class="forecast-note">ATTRIBUTION / 事件解读</span></div>
      <article class="forecast-report" id="forecast-report">${skeleton}</article>
    </section>
    <footer class="forecast-footer"><span>SENSE LAB / ANALYSIS OS</span><span>历史信号 <i>→</i> 趋势预测 <i>→</i> 事件归因</span></footer>
  </div>`;
}

function renderComponents(
  host: HTMLElement,
  dashboard: ForecastDashboard,
): void {
  if (!dashboard.components) {
    host.innerHTML = empty("当前结果未提供信号分量。");
    return;
  }
  const rows: [string, string, number[]][] = [
    ["T̂", "趋势", dashboard.components.T],
    ["Ŝ", "季节", dashboard.components.S],
    ["Ĉ", "冲击", dashboard.components.C],
    ["R̂", "残差", dashboard.components.R],
  ];
  host.innerHTML = rows
    .map(([glyph, label, values]) => {
      const mean = values.length
        ? values.reduce((a, b) => a + b, 0) / values.length
        : null;
      const magnitude = Math.min(1, Math.abs(mean ?? 0) / 4);
      return `<div class="forecast-component"><span class="forecast-component-symbol">${glyph}</span><span class="forecast-label">${label}</span><span class="forecast-bar" aria-hidden="true"><i style="--bar-scale:${magnitude}"></i></span><span class="forecast-value">${mean === null ? "—" : mean.toFixed(3)}</span></div>`;
    })
    .join("");
}

function renderEvents(host: HTMLElement, dashboard: ForecastDashboard): void {
  host.innerHTML = dashboard.anomalies.length
    ? dashboard.anomalies
        .slice(0, 8)
        .map(
          (event) =>
            `<div class="forecast-event"><span class="forecast-date">${escapeHtml(event.date)}</span><span class="forecast-z">z ${event.zMax.toFixed(1)}</span><span class="forecast-trigger">${escapeHtml(event.trigger)}</span><span class="forecast-ot">OT ${event.ot.toLocaleString("zh-CN")}</span></div>`,
        )
        .join("")
    : empty("最近观测窗口内没有异常日。");
}

function renderBadges(host: HTMLElement, dashboard: ForecastDashboard): void {
  const badges: string[] = [];
  if (dashboard.direction === "up" || dashboard.direction === "down") {
    const up = dashboard.direction === "up";
    badges.push(
      `<span class="forecast-badge">${up ? "↗ 上升趋势" : "↘ 下降趋势"}${dashboard.directionDelta !== null ? ` ${dashboard.directionDelta.toFixed(2)}` : ""}</span>`,
    );
  }
  if (dashboard.spikeWarning)
    badges.push(
      `<span class="forecast-badge warn">尖峰预警${dashboard.spikeGain !== null ? ` +${dashboard.spikeGain.toFixed(2)}` : ""}</span>`,
    );
  host.innerHTML = badges.join("");
}

export interface ForecastMotion {
  surfaces: boolean;
  numbers: boolean;
}

/** Own requests, observers and finite animations for exactly one modal lifetime. */
export function mountForecast(
  root: HTMLElement,
  motion: ForecastMotion,
): () => void {
  const pick = <T extends HTMLElement>(selector: string) =>
    root.querySelector<T>(selector)!;
  const status = pick("#forecast-status");
  const refresh = pick<HTMLButtonElement>("#forecast-refresh");
  const components = pick("#forecast-components");
  const events = pick("#forecast-events");
  const report = pick("#forecast-report");
  const chartMessage = pick("#forecast-chart-message");
  const request = new AbortController();
  const animations = new Set<Animation>();
  const counters = new Map<string, RollingNumberController>();
  let disposed = false;
  let loading = false;
  let hasData = false;
  root.dataset.motion = motion.surfaces ? "full" : "reduced";
  const chart = new ForecastChart(
    pick<HTMLCanvasElement>("#forecast-chart"),
    pick("#forecast-readout"),
    () => motion.surfaces,
  );

  const animate = (
    element: HTMLElement,
    frames: Keyframe[],
    delay = 0,
    duration = 620,
  ) => {
    if (!motion.surfaces) return;
    const animation = element.animate(frames, {
      duration,
      delay,
      easing: "cubic-bezier(0.22, 1, 0.36, 1)",
      fill: "backwards",
    });
    animations.add(animation);
    void animation.finished
      .then(() => animations.delete(animation))
      .catch(() => {});
  };
  const reveal = (element: HTMLElement, delay = 0) =>
    animate(
      element,
      [
        { opacity: 0, transform: "translateY(14px)" },
        { opacity: 1, transform: "translateY(0)" },
      ],
      delay,
    );
  // Sections below the fold enter when read, instead of finishing offscreen.
  const observer = new IntersectionObserver(
    (entries) => {
      entries
        .filter((entry) => entry.isIntersecting)
        .forEach((entry, index) => {
          const element = entry.target as HTMLElement;
          reveal(element, index * 65);
          element.classList.add("is-revealed");
          observer.unobserve(element);
        });
    },
    { root, threshold: 0.08 },
  );
  root
    .querySelectorAll<HTMLElement>("[data-forecast-reveal]")
    .forEach((element) => observer.observe(element));

  const setStatus = (message: string, kind = "") => {
    status.textContent = message;
    status.className = `forecast-status ${kind}`;
  };
  const setNumber = (selector: string, value: number | undefined) => {
    const host = pick(selector);
    if (value === undefined) {
      counters.get(selector)?.destroy();
      counters.delete(selector);
      host.textContent = "—";
      return;
    }
    let counter = counters.get(selector);
    if (!counter) {
      counter = createRollingNumber(host, {
        value: 0,
        animated: false,
        duration: 650,
        motionBlur: true,
        locales: "zh-CN",
        format: { maximumFractionDigits: 1 },
      });
      counters.set(selector, counter);
    }
    counter.update({ value, animated: motion.numbers });
  };
  const fetchDashboard = async () => {
    try {
      return await fetchForecastDashboard(90, request.signal);
    } catch (error) {
      if (disposed) throw error;
      setStatus("连接暂时中断，正在重试", "warn");
      await new Promise((resolve) => setTimeout(resolve, 800));
      if (disposed) throw error;
      return fetchForecastDashboard(90, request.signal);
    }
  };
  const load = async () => {
    if (loading || disposed) return;
    loading = true;
    root.dataset.state = "loading";
    root.setAttribute("aria-busy", "true");
    refresh.disabled = true;
    setStatus(hasData ? "正在更新观测数据" : "正在连接预测数据");
    if (!hasData)
      chartMessage.innerHTML =
        '<span class="forecast-scan" aria-hidden="true"></span><span>正在读取热度序列</span>';
    try {
      const [model, dashboard] = await Promise.all([
        fetchForecastStatus(request.signal).catch(() => null),
        fetchDashboard(),
      ]);
      if (disposed) return;
      renderBadges(pick("#forecast-badges"), dashboard);
      setNumber("#forecast-latest", dashboard.ot[dashboard.ot.length - 1]);
      setNumber(
        "#forecast-outlook",
        dashboard.prediction[dashboard.prediction.length - 1],
      );
      setNumber("#forecast-count", dashboard.anomalies.length);
      pick("#forecast-latest-date").textContent =
        dashboard.dates[dashboard.dates.length - 1] ?? "暂无历史观测";
      pick("#forecast-outlook-date").textContent =
        dashboard.predictionDates[dashboard.predictionDates.length - 1] ??
        "暂无预测结果";
      pick("#forecast-window").textContent =
        `${dashboard.ot.length} 个历史观测中的异常日`;
      pick("#forecast-range").textContent =
        `${dashboard.ot.length} 个历史观测 → ${dashboard.prediction.length} 个预测值`;
      chartMessage.hidden =
        dashboard.ot.length + dashboard.prediction.length > 0;
      if (!chartMessage.hidden)
        chartMessage.textContent = "当前观测窗口暂无热度序列";
      chart.update(dashboard);
      renderComponents(components, dashboard);
      renderEvents(events, dashboard);
      report.textContent =
        stripMarkdown(dashboard.reportMarkdown) || "当前结果尚未生成归因报告。";
      if (hasData)
        [components, events, report].forEach((element, index) =>
          reveal(element, index * 60),
        );
      components
        .querySelectorAll<HTMLElement>(".forecast-bar i")
        .forEach((bar, index) =>
          animate(
            bar,
            [
              { transform: "scaleX(0)" },
              {
                transform: `scaleX(${bar.style.getPropertyValue("--bar-scale")})`,
              },
            ],
            index * 65,
            850,
          ),
        );
      root.dataset.state = "ready";
      hasData = true;
      if (model?.modelLoaded) setStatus("预测数据已同步", "ok");
      else if (model) setStatus("模型未就绪 · 已显示可用数据", "warn");
      else setStatus("数据已读取 · 模型状态暂不可用", "warn");
    } catch (error) {
      if (disposed) return;
      root.dataset.state = "error";
      const message = error instanceof Error ? error.message : String(error);
      setStatus(
        `${hasData ? "更新失败，保留上次结果" : "暂时无法读取数据"} · ${message}`,
        "error",
      );
      if (!hasData) {
        chartMessage.textContent = "数据暂不可用，点击「刷新数据」重试";
        components.innerHTML = empty("连接恢复后显示信号分量。");
        events.innerHTML = empty("连接恢复后显示异常事件。");
        report.textContent = "暂时无法读取归因报告，请稍后刷新。";
        pick("#forecast-range").textContent = "等待连接恢复";
      }
    } finally {
      loading = false;
      if (!disposed) {
        root.setAttribute("aria-busy", "false");
        refresh.disabled = false;
      }
    }
  };
  const onRefresh = () => void load();
  refresh.addEventListener("click", onRefresh);
  void load();

  return () => {
    disposed = true;
    request.abort();
    observer.disconnect();
    chart.dispose();
    animations.forEach((animation) => animation.cancel());
    counters.forEach((counter) => counter.destroy());
    refresh.removeEventListener("click", onRefresh);
  };
}
