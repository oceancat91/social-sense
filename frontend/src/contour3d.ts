/* 事件热度轨迹 + 信号分解 + 异常事件。
 *
 * 版式参考用户给的预测面板：
 *   01 热度轨迹   历史观测（墨色实线）+ 预测（铜色点线）+ 预测区间（浅底 + 虚线分隔）
 *   02 信号分解   T/S/C/R 四条横条 + 标准化均值
 *   03 异常事件   按稳健 z 分数排序的异常日列表
 *
 * 全部 Canvas 2D + DOM 手绘，不引 Chart.js（独立 bundle 里不值得加 200KB 依赖）。
 */

export interface TrajectoryPoint {
  date: string;
  volume: number;
}

export interface TrajectoryData {
  history: TrajectoryPoint[];
  prediction: { dates: string[]; volume: number[]; tau_days?: number };
  actual: { dates: string[]; volume: number[] };
  peak_day?: string;
  peak_volume?: number;
  half_life_days?: number;
  decay_to_10pct_days?: number;
  scores?: {
    backtest_self_tau?: { rel_error?: number };
    live_global_tau?: { rel_error?: number };
  };
  caveat?: string;
}

export interface ComponentData {
  components?: Record<string, number[]>;
  direction_delta?: number;
  spike_gain?: number;
  model?: { name?: string };
  caveat?: string;
}

const INK = "#141a1f";
const INK_SOFT = "rgba(20,26,31,0.55)";
const BRONZE = "#a8753f";
const BRONZE_FILL = "rgba(168,117,63,0.07)";
const GRID = "rgba(20,26,31,0.09)";
const AXIS = "rgba(20,26,31,0.42)";
const PAPER = "#faf8f4";

/**
 * 构建完整的溯源 & 预测面板。
 * data 为空时返回一句提示，不抛错。
 */
export function createContour3D(
  data: TrajectoryData | null,
  comps?: ComponentData | null,
  opts: { width?: number } = {},
): HTMLElement {
  const wrap = document.createElement("div");
  wrap.className = "trace-panel";

  if (!data || (!data.history?.length && !data.prediction?.volume?.length)) {
    const p = document.createElement("p");
    p.className = "prediction-loading";
    p.textContent = "该事件暂无热度轨迹数据。";
    wrap.appendChild(p);
    return wrap;
  }

  wrap.appendChild(chartBlock(data, opts.width ?? 760));
  if (comps && comps.components) wrap.appendChild(componentBlock(comps));
  wrap.appendChild(anomalyBlock(data));
  return wrap;
}

/* ================= 01 热度轨迹 ================= */

function chartBlock(data: TrajectoryData, width: number): HTMLElement {
  const section = document.createElement("section");
  section.className = "trace-block";

  const hist = data.history ?? [];
  const predDates = data.prediction?.dates ?? [];
  const predVals = data.prediction?.volume ?? [];
  const nHist = hist.length;
  const nPred = predVals.length;

  const head = document.createElement("div");
  head.className = "trace-head";
  head.innerHTML = `
    <div>
      <h3><span class="trace-no">01</span>热度轨迹</h3>
      <p class="trace-sub">${nHist} 个历史观测 → ${nPred} 个预测值</p>
    </div>
    <div class="trace-badges">
      ${data.prediction?.tau_days != null ? `<span class="trace-badge">τ ${data.prediction.tau_days} 天</span>` : ""}
      ${data.half_life_days != null ? `<span class="trace-badge">半衰期 ${data.half_life_days} 天</span>` : ""}
    </div>`;
  section.appendChild(head);

  const height = 320;
  const canvas = document.createElement("canvas");
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = width * dpr;
  canvas.height = height * dpr;
  canvas.style.width = "100%";
  canvas.style.height = "auto";
  canvas.style.display = "block";
  canvas.setAttribute("role", "img");
  canvas.setAttribute("aria-label", "事件热度轨迹：历史观测与预测曲线");

  const ctx = canvas.getContext("2d");
  if (ctx) {
    ctx.scale(dpr, dpr);
    drawChart(ctx, width, height, data);
  }
  section.appendChild(canvas);

  // 图例
  const legend = document.createElement("div");
  legend.className = "trace-legend";
  legend.innerHTML = `
    <span><i class="lg-line lg-ink"></i>历史观测</span>
    <span><i class="lg-dot lg-bronze"></i>未来预测</span>
    ${data.actual?.volume?.length ? `<span><i class="lg-line lg-orange"></i>真实值</span>` : ""}`;
  section.appendChild(legend);

  return section;
}

function drawChart(
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  data: TrajectoryData,
): void {
  const hist = data.history ?? [];
  const predVals = data.prediction?.volume ?? [];
  const predDates = data.prediction?.dates ?? [];
  const actVals = data.actual?.volume ?? [];
  const nHist = hist.length;
  const nPred = predVals.length;
  const total = nHist + nPred;

  ctx.fillStyle = PAPER;
  ctx.fillRect(0, 0, width, height);

  const padL = 52;
  const padR = 26;
  const padT = 42;
  const padB = 46;
  const plotW = width - padL - padR;
  const plotH = height - padT - padB;

  const maxV = Math.max(...hist.map((h) => h.volume), ...predVals, ...actVals, 1);
  const step = niceStep(maxV / 3.2);
  const yMax = Math.ceil(maxV / step) * step;

  const toX = (i: number) => padL + (total <= 1 ? 0 : (i / (total - 1)) * plotW);
  const toY = (v: number) => padT + plotH - (v / yMax) * plotH;

  // ---- 预测区间底色 ----
  if (nPred > 0) {
    const x0 = toX(Math.max(0, nHist - 1));
    ctx.fillStyle = BRONZE_FILL;
    ctx.fillRect(x0, padT, padL + plotW - x0, plotH);

    // 虚线分隔
    ctx.strokeStyle = "rgba(168,117,63,0.42)";
    ctx.setLineDash([4, 4]);
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x0, padT);
    ctx.lineTo(x0, padT + plotH);
    ctx.stroke();
    ctx.setLineDash([]);

    // 区间标签
    ctx.fillStyle = "rgba(168,117,63,0.8)";
    ctx.font = '10px "Microsoft YaHei", "PingFang SC", sans-serif';
    ctx.textAlign = "left";
    ctx.textBaseline = "bottom";
    ctx.fillText("预测区间", x0 + 6, padT - 8);
  }

  // ---- 水平网格 + Y 刻度 ----
  ctx.font = '10px ui-monospace, "SFMono-Regular", Consolas, monospace';
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  for (let i = 0; i <= 3; i++) {
    const v = (yMax / 3) * i;
    const y = toY(v);
    ctx.strokeStyle = GRID;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(padL, y);
    ctx.lineTo(padL + plotW, y);
    ctx.stroke();
    ctx.fillStyle = AXIS;
    ctx.fillText(fmtNum(v), padL - 10, y);
  }

  // ---- X 轴：只标首尾两个日期 ----
  const allDates = [...hist.map((h) => h.date), ...predDates];
  ctx.fillStyle = AXIS;
  ctx.font = '10px ui-monospace, "SFMono-Regular", Consolas, monospace';
  ctx.textBaseline = "top";
  if (allDates.length) {
    ctx.textAlign = "left";
    ctx.fillText(allDates[0] ?? "", padL, padT + plotH + 10);
    if (allDates.length > 1) {
      const last = allDates[allDates.length - 1] ?? "";
      ctx.textAlign = "right";
      ctx.fillText(last, padL + plotW, padT + plotH + 10);
    }
  }

  // ---- 历史线（墨色细线）----
  if (nHist > 0) {
    ctx.strokeStyle = INK;
    ctx.lineWidth = 1.5;
    ctx.lineJoin = "round";
    ctx.beginPath();
    hist.forEach((h, i) => {
      const x = toX(i), y = toY(h.volume);
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    ctx.stroke();
  }

  // ---- 预测（铜色圆点连线，参考图就是这个样式）----
  if (nPred > 0) {
    ctx.strokeStyle = "rgba(168,117,63,0.55)";
    ctx.lineWidth = 1;
    ctx.setLineDash([2, 3]);
    ctx.beginPath();
    if (nHist > 0) ctx.moveTo(toX(nHist - 1), toY(hist[nHist - 1].volume));
    else ctx.moveTo(toX(0), toY(predVals[0]));
    predVals.forEach((v, i) => ctx.lineTo(toX(nHist + i), toY(v)));
    ctx.stroke();
    ctx.setLineDash([]);

    // 圆点（点多时抽稀）
    const dotStride = Math.max(1, Math.round(nPred / 28));
    ctx.fillStyle = BRONZE;
    predVals.forEach((v, i) => {
      if (i % dotStride !== 0 && i !== nPred - 1) return;
      ctx.beginPath();
      ctx.arc(toX(nHist + i), toY(v), 2.1, 0, Math.PI * 2);
      ctx.fill();
    });
  }

  // ---- 真实值（橙色实线）----
  if (actVals.length > 0) {
    ctx.strokeStyle = "#e08b2a";
    ctx.lineWidth = 1.6;
    ctx.beginPath();
    if (nHist > 0) ctx.moveTo(toX(nHist - 1), toY(hist[nHist - 1].volume));
    else ctx.moveTo(toX(nHist), toY(actVals[0]));
    actVals.forEach((v, i) => ctx.lineTo(toX(nHist + i), toY(v)));
    ctx.stroke();
  }
}

/* ================= 02 信号分解 ================= */

function componentBlock(comps: ComponentData): HTMLElement {
  const section = document.createElement("section");
  section.className = "trace-block";
  const c = comps.components ?? {};
  const keys = ["T", "S", "C", "R"];
  const names: Record<string, string> = {
    T: "趋势", S: "季节", C: "冲击", R: "残差",
  };
  const glyphs: Record<string, string> = {
    T: "T̂", S: "Ŝ", C: "Ĉ", R: "R̂",
  };

  const means = keys.map((k) => {
    const arr = Array.isArray(c[k]) ? c[k] : [];
    if (!arr.length) return 0;
    return arr.reduce((a, b) => a + b, 0) / arr.length;
  });
  const maxAbs = Math.max(...means.map(Math.abs), 1e-6);

  const rows = keys
    .map((k, i) => {
      const m = means[i];
      const pct = (Math.abs(m) / maxAbs) * 100;
      return `<div class="trace-row">
        <span class="trace-glyph">${glyphs[k]}</span>
        <span class="trace-name">${names[k]}</span>
        <span class="trace-bar"><i style="width:${pct.toFixed(1)}%"></i></span>
        <span class="trace-val">${m.toFixed(3)}</span>
      </div>`;
    })
    .join("");

  section.innerHTML = `
    <div class="trace-head">
      <div>
        <h3><span class="trace-no">02</span>信号分解</h3>
        <p class="trace-sub">ŷ = T̂ + Ŝ + Ĉ + R̂　趋势 / 季节 / 冲击 / 残差</p>
      </div>
      <div class="trace-badges">
        ${comps.model?.name ? `<span class="trace-badge">${esc(comps.model.name)}</span>` : ""}
        ${comps.direction_delta != null ? `<span class="trace-badge">方向 Δ ${comps.direction_delta}</span>` : ""}
        ${comps.spike_gain != null ? `<span class="trace-badge">尖峰增益 ${comps.spike_gain}</span>` : ""}
      </div>
    </div>
    <div class="trace-rows">
      <div class="trace-row trace-row-head">
        <span class="trace-glyph"></span><span class="trace-name"></span>
        <span class="trace-bar"></span><span class="trace-val">标准化均值</span>
      </div>
      ${rows}
    </div>`;
  return section;
}

/* ================= 03 异常事件 ================= */

function anomalyBlock(data: TrajectoryData): HTMLElement {
  const section = document.createElement("section");
  section.className = "trace-block";
  const hist = data.history ?? [];

  // 稳健 z：用中位数与 MAD，避免被峰值本身带偏
  const vals = hist.map((h) => h.volume);
  const sorted = [...vals].sort((a, b) => a - b);
  const med = sorted.length ? sorted[Math.floor(sorted.length / 2)] : 0;
  const deviations = vals.map((v) => Math.abs(v - med)).sort((a, b) => a - b);
  const mad = deviations.length ? deviations[Math.floor(deviations.length / 2)] || 1 : 1;
  const z = (v: number) => (0.6745 * (v - med)) / mad;

  const rows = hist
    .map((h, i) => ({ ...h, z: z(h.volume), i }))
    .filter((r) => Math.abs(r.z) >= 2.5)
    .sort((a, b) => Math.abs(b.z) - Math.abs(a.z))
    .slice(0, 8);

  section.innerHTML = `
    <div class="trace-head">
      <div>
        <h3><span class="trace-no">03</span>异常事件</h3>
        <p class="trace-sub">按稳健 z 分数排序（中位数 + MAD）</p>
      </div>
      <div class="trace-badges"><span class="trace-badge">稳健 z 分数</span></div>
    </div>
    <div class="trace-anoms">
      ${
        rows.length
          ? rows
              .map(
                (r) => `<div class="trace-anom">
                  <span class="anom-date">${esc(r.date)}</span>
                  <span class="anom-z">z ${r.z.toFixed(1)}</span>
                  <span class="anom-type">${Math.abs(r.z) >= 4 ? "regime" : "OT"}</span>
                  <span class="anom-val">声量 ${Math.round(r.volume).toLocaleString()}</span>
                </div>`,
              )
              .join("")
          : `<p class="trace-sub" style="padding:10px 0">该事件窗口内没有 |z| ≥ 2.5 的异常日。</p>`
      }
    </div>`;
  return section;
}

/* ================= 工具 ================= */

function niceStep(raw: number): number {
  const exp = Math.floor(Math.log10(Math.max(raw, 1e-6)));
  const base = Math.pow(10, exp);
  const norm = raw / base;
  const mult = norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10;
  return mult * base;
}

function fmtNum(v: number): string {
  if (v >= 100000) return Math.round(v / 10000) + "万";
  if (v >= 10000) return (v / 10000).toFixed(1) + "万";
  if (v >= 1000) return (v / 1000).toFixed(1) + "k";
  return String(Math.round(v));
}

function esc(s: string): string {
  return s.replace(/[&<>"']/g, (ch) =>
    ch === "&" ? "&amp;" : ch === "<" ? "&lt;" : ch === ">" ? "&gt;" : ch === '"' ? "&quot;" : "&#39;",
  );
}
