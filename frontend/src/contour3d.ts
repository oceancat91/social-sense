/* 3D 数字化等高线 —— 每个事件一张随机的三维曲面。
 *
 * 按用户要求：不参考真实数据，随机生成，但每个事件必须不同。
 * 同一事件每次打开保持稳定（用 event_id 做种子），换事件就换一张。
 *
 * 实现方式：不引入 Three.js（那要额外 600KB），改用 Canvas 2D 画等距投影的
 * 线框曲面 —— 视觉上就是三维等高线图，但零依赖、加载快。
 */
export interface ContourOptions {
  width?: number;
  height?: number;
  cols?: number;
  rows?: number;
  levels?: number;
}

/** 32 位字符串哈希，用作伪随机种子 */
function hashSeed(s: string): number {
  let h = 2166136261 >>> 0;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619) >>> 0;
  }
  return h >>> 0;
}

/** mulberry32 —— 轻量可复现伪随机 */
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

/** 生成一张随机但确定的高度场：若干高斯峰谷叠加 + 轻微噪声 */
function buildField(seed: string, cols: number, rows: number): Float32Array {
  const rng = makeRng(hashSeed(seed));
  const field = new Float32Array(cols * rows);

  // 3~6 个峰 + 2~4 个谷，位置与高度都随机
  const peaks = 3 + Math.floor(rng() * 4);
  const valleys = 2 + Math.floor(rng() * 3);
  type Bump = { cx: number; cy: number; amp: number; sx: number; sy: number };
  const bumps: Bump[] = [];
  for (let i = 0; i < peaks; i++) {
    bumps.push({
      cx: 0.1 + rng() * 0.8,
      cy: 0.1 + rng() * 0.8,
      amp: 0.55 + rng() * 0.75,
      sx: 0.08 + rng() * 0.16,
      sy: 0.08 + rng() * 0.16,
    });
  }
  for (let i = 0; i < valleys; i++) {
    bumps.push({
      cx: 0.1 + rng() * 0.8,
      cy: 0.1 + rng() * 0.8,
      amp: -(0.3 + rng() * 0.45),
      sx: 0.10 + rng() * 0.18,
      sy: 0.10 + rng() * 0.18,
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
      // 一点高频纹理，让曲面不是纯高斯
      h += (rng() - 0.5) * 0.06;
      field[y * cols + x] = h;
    }
  }

  // 归一到 0..1
  let lo = Infinity, hi = -Infinity;
  for (const v of field) { if (v < lo) lo = v; if (v > hi) hi = v; }
  const span = hi - lo || 1;
  for (let i = 0; i < field.length; i++) field[i] = (field[i] - lo) / span;
  return field;
}

/**
 * 画出等距投影的三维等高线。
 * 返回的元素可直接插入 DOM；eventId 相同则每次生成完全一致。
 */
export function createContour3D(eventId: string, opts: ContourOptions = {}): HTMLCanvasElement {
  const width = opts.width ?? 720;
  const height = opts.height ?? 420;
  const cols = opts.cols ?? 46;
  const rows = opts.rows ?? 30;
  const levels = opts.levels ?? 14;

  const canvas = document.createElement("canvas");
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = width * dpr;
  canvas.height = height * dpr;
  canvas.style.width = "100%";
  canvas.style.height = "auto";
  canvas.style.display = "block";
  canvas.setAttribute("role", "img");
  canvas.setAttribute("aria-label", "事件热度三维等高线（随机生成示意）");

  const ctx = canvas.getContext("2d");
  if (!ctx) return canvas;
  ctx.scale(dpr, dpr);

  const field = buildField(eventId, cols, rows);

  // 等距投影：把 (u,v,h) 映射到屏幕
  const cx = width * 0.5;
  const cy = height * 0.62;
  const scaleX = width * 0.44;
  const scaleY = height * 0.30;
  const liftZ = height * 0.34;

  const project = (u: number, v: number, h: number) => {
    // 平面上的菱形
    const px = (u - v) * scaleX;
    const py = (u + v - 1) * scaleY;
    return {
      x: cx + px,
      y: cy + py - h * liftZ,
    };
  };

  // 背景
  ctx.fillStyle = "#f3f1ee";
  ctx.fillRect(0, 0, width, height);

  // 底面网格（很淡）
  ctx.strokeStyle = "rgba(8,10,8,0.07)";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 8; i++) {
    const t = i / 8;
    let a = project(t, 0, 0), b = project(t, 1, 0);
    ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
    a = project(0, t, 0); b = project(1, t, 0);
    ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
  }

  // 按高度分层画等值线（从低到高，高的后画覆盖低的）
  for (let l = 0; l < levels; l++) {
    const level = (l + 0.5) / levels;
    const t = l / (levels - 1);
    // 低处铜色、高处橙色
    const r = Math.round(166 + (237 - 166) * t);
    const g = Math.round(125 + (130 - 125) * t);
    const bch = Math.round(72 + (27 - 72) * t);
    ctx.strokeStyle = `rgba(${r},${g},${bch},${(0.22 + 0.55 * t).toFixed(3)})`;
    ctx.lineWidth = 0.8 + 1.2 * t;

    // marching squares 的简化版：逐格取边中点连成折线
    ctx.beginPath();
    let started = false;
    for (let y = 0; y < rows - 1; y++) {
      for (let x = 0; x < cols - 1; x++) {
        const h00 = field[y * cols + x];
        const h10 = field[y * cols + x + 1];
        const h01 = field[(y + 1) * cols + x];
        const h11 = field[(y + 1) * cols + x + 1];
        const inside = (h00 > level ? 1 : 0) + (h10 > level ? 1 : 0) + (h01 > level ? 1 : 0) + (h11 > level ? 1 : 0);
        if (inside === 0 || inside === 4) continue;
        const u = x / (cols - 1);
        const v = y / (rows - 1);
        const du = 1 / (cols - 1);
        const dv = 1 / (rows - 1);
        const p = project(u + du * 0.5, v + dv * 0.5, level);
        if (!started) { ctx.moveTo(p.x, p.y); started = true; }
        else { ctx.lineTo(p.x, p.y); }
      }
    }
    ctx.stroke();
  }

  // 描一遍曲面主线框，强化"立体"感
  ctx.strokeStyle = "rgba(8,10,8,0.22)";
  ctx.lineWidth = 1;
  for (let y = 0; y < rows; y += 3) {
    ctx.beginPath();
    for (let x = 0; x < cols; x++) {
      const u = x / (cols - 1);
      const v = y / (rows - 1);
      const p = project(u, v, field[y * cols + x]);
      if (x === 0) ctx.moveTo(p.x, p.y); else ctx.lineTo(p.x, p.y);
    }
    ctx.stroke();
  }
  for (let x = 0; x < cols; x += 4) {
    ctx.beginPath();
    for (let y = 0; y < rows; y++) {
      const u = x / (cols - 1);
      const v = y / (rows - 1);
      const p = project(u, v, field[y * cols + x]);
      if (y === 0) ctx.moveTo(p.x, p.y); else ctx.lineTo(p.x, p.y);
    }
    ctx.stroke();
  }

  // 角标
  ctx.fillStyle = "rgba(8,10,8,0.45)";
  ctx.font = '10px ui-monospace, Consolas, monospace';
  ctx.fillText("3D CONTOUR · RANDOMIZED", 14, height - 14);
  ctx.fillText(eventId, width - 14 - ctx.measureText(eventId).width, height - 14);

  return canvas;
}
