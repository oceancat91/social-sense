/* 事件热度轨迹折线图 —— 版式对齐预测页（/api/v1/forecast/ui）的主图。
 *
 * 三条线：
 *   历史声量（墨色实线 + 浅填充）
 *   预测（指数衰减，铜色虚线）
 *   真实值（橙色实线，用于回测对比）
 *
 * 为什么不用 Chart.js：3D 终端是独立打包的 Vite bundle，为一张图引 200KB
 * 依赖不划算；这里用 Canvas 2D 手绘，样式与预测页保持一致即可。
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

const INK = "rgba(8,10,8,0.55)";
const INK_FILL = "rgba(8,10,8,0.05)";
const BRONZE = "#a67d48";
const ORANGE = "#ed821b";
const GRID = "rgba(8,10,8,0.08)";
const AXIS = "rgba(8,10,8,0.42)";

/**
 * 绘制热度轨迹折线图。
 * 数据为空或异常时画一句提示，不抛错 —— 避免拖垮整个详情页。
 */
export function createTrajectoryChart(
  data: TrajectoryData | null,
  opts: { width?: number; height?: number } = {},
): HTMLCanvasElement {
  const width = opts.width ?? 760;
  const height = opts.height ?? 400;

  const canvas = document.createElement("canvas");
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = width * dpr;
  canvas.height = height * dpr;
  canvas.style.width = "100%";
  canvas.style.height = "auto";
  canvas.style.display = "block";
  canvas.setAttribute("role", "img");
  canvas.setAttribute("aria-label", "事件热度轨迹图：历史声量、预测曲线与真实值对比");

  const ctx = canvas.getContext("2d");
  if (!ctx) return canvas;
  ctx.scale(dpr, dpr);

  // 白纸底
  ctx.fillStyle = "#fbfaf8";
  ctx.fillRect(0, 0, width, height);

  const hist = data?.history ?? [];
  const predDates = data?.prediction?.dates ?? [];
  const predVals = data?.prediction?.volume ?? [];
  const actVals = data?.actual?.volume ?? [];

  if (!hist.length && !predVals.length) {
    ctx.fillStyle = AXIS;
    ctx.font = '13px "Microsoft YaHei", "PingFang SC", sans-serif';
    ctx.fillText("该事件暂无热度轨迹数据", 24, height / 2);
    return canvas;
  }

  // ---------- 布局 ----------
  const padL = 52;
  const padR = 24;
  const padT = 34;
  const padB = 46;
  const plotW = width - padL - padR;
  const plotH = height - padT - padB;

  const nHist = hist.length;
  const nPred = predVals.length;
  const total = nHist + nPred;
  const maxV = Math.max(
    ...hist.map((h) => h.volume),
    ...predVals,
    ...actVals,
    1,
  );
  // Y 轴取整到好看的刻度
  const step = niceStep(maxV / 4);
  const yMax = Math.ceil(maxV / step) * step;

  const toX = (i: number) => padL + (total <= 1 ? 0 : (i / (total - 1)) * plotW);
  const toY = (v: number) => padT + plotH - (v / yMax) * plotH;

  // ---------- 网格与刻度 ----------
  ctx.strokeStyle = GRID;
  ctx.lineWidth = 1;
  ctx.fillStyle = AXIS;
  ctx.font = '10px ui-monospace, "SFMono-Regular", Consolas, monospace';
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  for (let i = 0; i <= 4; i++) {
    const v = step * i;
    const y = toY(v);
    ctx.beginPath();
    ctx.moveTo(padL, y);
    ctx.lineTo(padL + plotW, y);
    ctx.stroke();
    ctx.fillText(formatNum(v), padL - 8, y);
  }

  // X 轴刻度：抽稀，最多 8 个
  const allDates = [...hist.map((h) => h.date), ...predDates];
  const stride = Math.max(1, Math.ceil(total / 8));
  ctx.textAlign = "center";
  ctx.textBaseline = "top";
  for (let i = 0; i < total; i += stride) {
    ctx.fillText(shortDate(allDates[i] ?? ""), toX(i), padT + plotH + 8);
  }

  // 峰值分隔线（历史 / 预测交界）
  if (nHist > 0 && nPred > 0) {
    const x = toX(nHist - 1);
    ctx.strokeStyle = "rgba(8,10,8,0.16)";
    ctx.setLineDash([3, 4]);
    ctx.beginPath();
    ctx.moveTo(x, padT);
    ctx.lineTo(x, padT + plotH);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = "rgba(8,10,8,0.38)";
    ctx.font = '9px ui-monospace, Consolas, monospace';
    ctx.textAlign = "center";
    ctx.textBaseline = "bottom";
    ctx.fillText("峰值", x, padT - 6);
  }

  // ---------- 历史面积填充 ----------
  if (nHist > 1) {
    ctx.beginPath();
    ctx.moveTo(toX(0), padT + plotH);
    hist.forEach((h, i) => ctx.lineTo(toX(i), toY(h.volume)));
    ctx.lineTo(toX(nHist - 1), padT + plotH);
    ctx.closePath();
    ctx.fillStyle = INK_FILL;
    ctx.fill();
  }

  // ---------- 历史线 ----------
  if (nHist > 0) {
    ctx.strokeStyle = INK;
    ctx.lineWidth = 2;
    ctx.beginPath();
    hist.forEach((h, i) => {
      const x = toX(i), y = toY(h.volume);
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    ctx.stroke();
  }

  // ---------- 预测线（从历史末点接过去，铜色虚线）----------
  if (nPred > 0) {
    ctx.strokeStyle = BRONZE;
    ctx.lineWidth = 2;
    ctx.setLineDash([5, 4]);
    ctx.beginPath();
    if (nHist > 0) {
      ctx.moveTo(toX(nHist - 1), toY(hist[nHist - 1].volume));
    } else {
      ctx.moveTo(toX(0), toY(predVals[0]));
    }
    predVals.forEach((v, i) => ctx.lineTo(toX(nHist + i), toY(v)));
    ctx.stroke();
    ctx.setLineDash([]);
  }

  // ---------- 真实值（橙色实线）----------
  if (actVals.length > 0) {
    ctx.strokeStyle = ORANGE;
    ctx.lineWidth = 1.8;
    ctx.beginPath();
    if (nHist > 0) {
      ctx.moveTo(toX(nHist - 1), toY(hist[nHist - 1].volume));
    } else {
      ctx.moveTo(toX(nHist), toY(actVals[0]));
    }
    actVals.forEach((v, i) => ctx.lineTo(toX(nHist + i), toY(v)));
    ctx.stroke();
  }

  // ---------- 峰值点 ----------
  if (nHist > 0) {
    let pi = 0;
    for (let i = 1; i < nHist; i++) if (hist[i].volume > hist[pi].volume) pi = i;
    const px = toX(pi), py = toY(hist[pi].volume);
    ctx.fillStyle = "#080a08";
    ctx.beginPath();
    ctx.arc(px, py, 3.2, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = "rgba(8,10,8,0.18)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.arc(px, py, 8, 0, Math.PI * 2);
    ctx.stroke();
  }

  // ---------- 图例 ----------
  const legend: [string, string, boolean][] = [
    ["历史声量", INK, false],
    ["预测（指数衰减）", BRONZE, true],
    ["真实值", ORANGE, false],
  ];
  let lx = padL;
  const ly = 16;
  ctx.font = '11px "Microsoft YaHei", "PingFang SC", sans-serif';
  ctx.textAlign = "left";
  ctx.textBaseline = "middle";
  for (const [label, color, dashed] of legend) {
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.setLineDash(dashed ? [4, 3] : []);
    ctx.beginPath();
    ctx.moveTo(lx, ly);
    ctx.lineTo(lx + 18, ly);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = "rgba(8,10,8,0.68)";
    ctx.fillText(label, lx + 24, ly);
    lx += 24 + ctx.measureText(label).width + 22;
  }

  // ---------- 右下角关键指标 ----------
  if (data) {
    const bits: string[] = [];
    if (data.prediction?.tau_days != null) bits.push(`τ ${data.prediction.tau_days}d`);
    if (data.half_life_days != null) bits.push(`半衰期 ${data.half_life_days}d`);
    const err = data.scores?.backtest_self_tau?.rel_error;
    if (err != null) bits.push(`回测误差 ${err}`);
    if (bits.length) {
      ctx.fillStyle = "rgba(8,10,8,0.45)";
      ctx.font = '10px ui-monospace, "SFMono-Regular", Consolas, monospace';
      ctx.textAlign = "right";
      ctx.textBaseline = "bottom";
      ctx.fillText(bits.join("   "), width - padR, height - 8);
    }
  }

  return canvas;
}

function niceStep(raw: number): number {
  const exp = Math.floor(Math.log10(Math.max(raw, 1e-6)));
  const base = Math.pow(10, exp);
  const norm = raw / base;
  const mult = norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10;
  return mult * base;
}

function formatNum(v: number): string {
  if (v >= 10000) return (v / 10000).toFixed(v >= 100000 ? 0 : 1) + "万";
  if (v >= 1000) return (v / 1000).toFixed(v >= 10000 ? 0 : 1) + "k";
  return String(Math.round(v));
}

function shortDate(d: string): string {
  // 2021-05-31 → 05-31
  return d.length >= 10 ? d.slice(5, 10) : d;
}
