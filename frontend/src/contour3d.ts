/* 数字化等高线 —— 固定俯视视角（top-down）的地形图。
 *
 * 参考样式：深色底 + 金色等值线 + 峰谷标记 + 同心结构，视角固定不旋转。
 * 按用户要求：不参考真实数据，随机生成，但每个事件必须不同；
 * 同一事件每次打开保持稳定（用 event_id 做种子），换事件就换一张。
 *
 * 实现：Canvas 2D + 真正的 marching squares 等值线，零依赖。
 */

export interface ContourOptions {
  width?: number;
  height?: number;
  cols?: number;
  rows?: number;
  levels?: number;
}

/** FNV-1a 字符串哈希，用作伪随机种子 */
function hashSeed(s: string): number {
  let h = 2166136261 >>> 0;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619) >>> 0;
  }
  return h >>> 0;
}

/** mulberry32：轻量可复现伪随机 */
function makeRng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** 生成随机高度场：若干高斯峰谷叠加 + 轻微纹理，并做圆形衰减形成地形岛 */
function buildField(seed: string, cols: number, rows: number): Float32Array {
  const rng = makeRng(hashSeed(seed));
  const field = new Float32Array(cols * rows);

  type Bump = { cx: number; cy: number; amp: number; sx: number; sy: number };
  const bumps: Bump[] = [];

  // 3~5 个主峰（有一个明显更高的主峰，模拟地形图上的最高点）
  const peakCount = 3 + Math.floor(rng() * 3);
  for (let i = 0; i < peakCount; i++) {
    const main = i === 0;
    bumps.push({
      cx: 0.18 + rng() * 0.64,
      cy: 0.18 + rng() * 0.64,
      amp: main ? 1.15 + rng() * 0.45 : 0.4 + rng() * 0.55,
      sx: main ? 0.12 + rng() * 0.06 : 0.07 + rng() * 0.10,
      sy: main ? 0.12 + rng() * 0.06 : 0.07 + rng() * 0.10,
    });
  }
  // 2~4 个洼地
  const valleyCount = 2 + Math.floor(rng() * 3);
  for (let i = 0; i < valleyCount; i++) {
    bumps.push({
      cx: 0.15 + rng() * 0.7,
      cy: 0.15 + rng() * 0.7,
      amp: -(0.25 + rng() * 0.4),
      sx: 0.08 + rng() * 0.14,
      sy: 0.08 + rng() * 0.14,
    });
  }

  for (let y = 0; y < rows; y++) {
    for (let x = 0; x < cols; x++) {
      const u = x / (cols - 1);
      const v = y / (rows - 1);
      let h = 0;
      for (const b of bumps) {
        const dx = (u - b.cx) / b.sx;
        const dy = (v - b.cy) / b.sy;
        h += b.amp * Math.exp(-(dx * dx + dy * dy) * 0.5);
      }
      // 圆形衰减：边缘压平，形成"岛屿"轮廓而不是满幅噪声
      const rx = (u - 0.5) * 2;
      const ry = (v - 0.5) * 2;
      const r = Math.sqrt(rx * rx + ry * ry);
      const falloff = Math.max(0, 1 - Math.pow(r / 1.02, 3.2));
      h *= falloff;
      // 高频纹理：让等值线不是纯圆
      h += (rng() - 0.5) * 0.045 * falloff;
      field[y * cols + x] = h;
    }
  }

  let lo = Infinity, hi = -Infinity;
  for (const v of field) { if (v < lo) lo = v; if (v > hi) hi = v; }
  const span = hi - lo || 1;
  for (let i = 0; i < field.length; i++) field[i] = (field[i] - lo) / span;
  return field;
}

/** 线性插值出等值线与网格边的交点 */
function lerpEdge(h1: number, h2: number, level: number): number {
  const d = h2 - h1;
  if (Math.abs(d) < 1e-9) return 0.5;
  return (level - h1) / d;
}

/**
 * 固定俯视的等高线地形图。
 * eventId 相同则每次渲染完全一致；换事件就换一张地形。
 */
export function createContour3D(eventId: string, opts: ContourOptions = {}): HTMLCanvasElement {
  const width = opts.width ?? 760;
  const height = opts.height ?? 460;
  const cols = opts.cols ?? 96;
  const rows = opts.rows ?? 96;
  const levels = opts.levels ?? 16;

  const canvas = document.createElement("canvas");
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = width * dpr;
  canvas.height = height * dpr;
  canvas.style.width = "100%";
  canvas.style.height = "auto";
  canvas.style.display = "block";
  canvas.setAttribute("role", "img");
  canvas.setAttribute("aria-label", "事件热度等高线地形图（随机生成示意）");

  const ctx = canvas.getContext("2d");
  if (!ctx) return canvas;
  ctx.scale(dpr, dpr);

  const field = buildField(eventId, cols, rows);
  const rng = makeRng(hashSeed(eventId) ^ 0x9e3779b9);

  // ---------- 底色 ----------
  ctx.fillStyle = "#0e1114";
  ctx.fillRect(0, 0, width, height);

  // 网格底纹
  ctx.strokeStyle = "rgba(255,255,255,0.035)";
  ctx.lineWidth = 1;
  const grid = 40;
  for (let gx = 0; gx <= width; gx += grid) {
    ctx.beginPath(); ctx.moveTo(gx, 0); ctx.lineTo(gx, height); ctx.stroke();
  }
  for (let gy = 0; gy <= height; gy += grid) {
    ctx.beginPath(); ctx.moveTo(0, gy); ctx.lineTo(width, gy); ctx.stroke();
  }

  // 正俯视投影：等距映射到画布
  const pad = 28;
  const sx = (width - pad * 2) / (cols - 1);
  const sy = (height - pad * 2) / (rows - 1);
  const toX = (x: number) => pad + x * sx;
  const toY = (y: number) => pad + y * sy;

  // ---------- 高度分层填色（模拟地形图的色带）----------
  const bands = 8;
  for (let b = 0; b < bands; b++) {
    const t = b / (bands - 1);
    // 从深青到金色
    const r = Math.round(12 + (214 - 12) * Math.pow(t, 1.5));
    const g = Math.round(20 + (168 - 20) * Math.pow(t, 1.4));
    const bl = Math.round(26 + (78 - 26) * Math.pow(t, 1.3));
    ctx.fillStyle = `rgba(${r},${g},${bl},${0.10 + 0.30 * t})`;
    const lo = b / bands;
    const hi = (b + 1) / bands;
    for (let y = 0; y < rows - 1; y++) {
      for (let x = 0; x < cols - 1; x++) {
        const h = field[y * cols + x];
        if (h < lo || h >= hi) continue;
        ctx.fillRect(toX(x) - sx * 0.5, toY(y) - sy * 0.5, sx + 1, sy + 1);
      }
    }
  }

  // ---------- 等值线（marching squares）----------
  for (let l = 0; l < levels; l++) {
    const level = (l + 0.5) / levels;
    const t = l / (levels - 1);
    const alpha = 0.20 + 0.62 * t;
    // 低处偏青，高处金色
    const r = Math.round(90 + (255 - 90) * t);
    const g = Math.round(150 + (210 - 150) * t);
    const bl = Math.round(120 + (90 - 120) * t);
    ctx.strokeStyle = `rgba(${r},${g},${bl},${alpha.toFixed(3)})`;
    ctx.lineWidth = 0.7 + 1.1 * t;
    ctx.beginPath();

    for (let y = 0; y < rows - 1; y++) {
      for (let x = 0; x < cols - 1; x++) {
        const h00 = field[y * cols + x];
        const h10 = field[y * cols + x + 1];
        const h01 = field[(y + 1) * cols + x];
        const h11 = field[(y + 1) * cols + x + 1];

        // 四个角是否高于等值线：组成 4 位掩码
        const code =
          (h00 > level ? 1 : 0) |
          (h10 > level ? 2 : 0) |
          (h11 > level ? 4 : 0) |
          (h01 > level ? 8 : 0);
        if (code === 0 || code === 15) continue;

        // 四条边上的交点（边编号：0 上 1 右 2 下 3 左）
        const top = { x: toX(x + lerpEdge(h00, h10, level)), y: toY(y) };
        const right = { x: toX(x + 1), y: toY(y + lerpEdge(h10, h11, level)) };
        const bottom = { x: toX(x + lerpEdge(h01, h11, level)), y: toY(y + 1) };
        const left = { x: toX(x), y: toY(y + lerpEdge(h00, h01, level)) };

        // 查表：每种掩码对应 1~2 段线
        const seg = (a: { x: number; y: number }, b: { x: number; y: number }) => {
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
        };
        switch (code) {
          case 1: case 14: seg(left, top); break;
          case 2: case 13: seg(top, right); break;
          case 3: case 12: seg(left, right); break;
          case 4: case 11: seg(right, bottom); break;
          case 5: seg(left, top); seg(right, bottom); break;
          case 6: case 9: seg(top, bottom); break;
          case 7: case 8: seg(left, bottom); break;
          case 10: seg(left, bottom); seg(top, right); break;
          default: break;
        }
      }
    }
    ctx.stroke();
  }

  // ---------- 峰顶标记（等高线图上的高程点）----------
  let peak = { i: 0, h: -1 };
  for (let i = 0; i < field.length; i++) if (field[i] > peak.h) peak = { i, h: field[i] };
  const px = toX(peak.i % cols);
  const py = toY(Math.floor(peak.i / cols));

  // 主峰十字准星 + 光晕
  const glow = ctx.createRadialGradient(px, py, 0, px, py, 46);
  glow.addColorStop(0, "rgba(255,210,90,0.55)");
  glow.addColorStop(1, "rgba(255,210,90,0)");
  ctx.fillStyle = glow;
  ctx.beginPath(); ctx.arc(px, py, 46, 0, Math.PI * 2); ctx.fill();

  ctx.strokeStyle = "#ffd25a";
  ctx.lineWidth = 1.6;
  ctx.beginPath(); ctx.arc(px, py, 7, 0, Math.PI * 2); ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(px - 16, py); ctx.lineTo(px - 9, py);
  ctx.moveTo(px + 9, py); ctx.lineTo(px + 16, py);
  ctx.moveTo(px, py - 16); ctx.lineTo(px, py - 9);
  ctx.moveTo(px, py + 9); ctx.lineTo(px, py + 16);
  ctx.stroke();

  // 3~5 个随机次要兴趣点
  const dots = 3 + Math.floor(rng() * 3);
  for (let d = 0; d < dots; d++) {
    const di = Math.floor(rng() * field.length);
    const dx = toX(di % cols);
    const dy = toY(Math.floor(di / cols));
    const dh = field[di];
    if (dh < 0.35) continue;
    const isHigh = dh > 0.72;
    ctx.fillStyle = isHigh ? "rgba(255,210,90,0.95)" : "rgba(255,140,60,0.85)";
    ctx.beginPath(); ctx.arc(dx, dy, isHigh ? 3.6 : 2.6, 0, Math.PI * 2); ctx.fill();
    if (isHigh) {
      ctx.strokeStyle = "rgba(255,210,90,0.45)";
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.arc(dx, dy, 9, 0, Math.PI * 2); ctx.stroke();
    }
  }

  // ---------- 外框与角标 ----------
  ctx.strokeStyle = "rgba(255,210,90,0.20)";
  ctx.lineWidth = 1;
  ctx.strokeRect(pad * 0.5, pad * 0.5, width - pad, height - pad);

  ctx.fillStyle = "rgba(255,210,90,0.72)";
  ctx.font = '10px ui-monospace, "SFMono-Regular", Consolas, monospace';
  ctx.fillText("TOP-DOWN CONTOUR · RANDOMIZED", 16, 20);
  ctx.fillText("ELEV " + (0.6 + rng() * 0.4).toFixed(2), 16, height - 14);
  const tag = eventId.length > 26 ? eventId.slice(0, 26) + "…" : eventId;
  ctx.fillText(tag, width - 16 - ctx.measureText(tag).width, height - 14);

  return canvas;
}
