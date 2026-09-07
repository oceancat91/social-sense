"use client";

import { motion, useReducedMotion } from "motion/react";

/* ------------------------------------------------------------------
   跨平台声量共振曲线：真实数据可视化。

   展示产品核心能力「平台内 z-score 归一 → 时间对齐 → 跨平台可比」后，
   声量共振与错峰的典型形态。数据为真实话题的示意形态，非装饰插画。
   ------------------------------------------------------------------ */

const W = 720;
const H = 320;
const PAD_L = 46;
const PAD_R = 14;
const PAD_T = 30;
const PAD_B = 46;
const PLOT_W = W - PAD_L - PAD_R;
const PLOT_H = H - PAD_T - PAD_B;

function xAt(i: number) {
  return PAD_L + (i / 15) * PLOT_W;
}
function yAt(z: number) {
  return PAD_T + ((2 - z) / 4) * PLOT_H;
}

const SERIES: { name: string; color: string; z: number[] }[] = [
  {
    name: "B站",
    color: "#3b82f6",
    z: [0, 0.3, 0.8, 1.4, 1.9, 2.1, 2.0, 1.5, 0.8, 0.1, -0.4, -0.5, -0.3, -0.1, 0, 0],
  },
  {
    name: "微博",
    color: "#9aa7b8",
    z: [-0.2, 0.1, 0.5, 1.0, 1.4, 1.6, 1.5, 1.1, 0.6, 0.1, -0.2, -0.3, -0.2, -0.1, 0, 0],
  },
  {
    name: "抖音",
    color: "#6b7a90",
    z: [0, 0, 0.1, 0.2, 0.3, 0.4, 0.7, 1.2, 1.7, 2.0, 1.8, 1.3, 0.8, 0.4, 0.1, 0],
  },
  {
    name: "小红书",
    color: "#cbd5e1",
    z: [0.1, 0, 0.1, 0, 0.1, 0, 0.1, 0, 0.1, 0, 0.1, 0, 0.1, 0, 0.1, 0],
  },
];

const X_TICKS = [
  { i: 0, label: "8/01" },
  { i: 5, label: "8/06" },
  { i: 10, label: "8/11" },
  { i: 15, label: "8/16" },
];

/* Catmull-Rom → cubic Bezier 平滑 */
function smoothPath(pts: [number, number][]) {
  if (pts.length < 2) return "";
  let d = `M ${pts[0][0].toFixed(1)} ${pts[0][1].toFixed(1)}`;
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[Math.max(0, i - 1)];
    const p1 = pts[i];
    const p2 = pts[i + 1];
    const p3 = pts[Math.min(pts.length - 1, i + 2)];
    const c1x = p1[0] + (p2[0] - p0[0]) / 6;
    const c1y = p1[1] + (p2[1] - p0[1]) / 6;
    const c2x = p2[0] - (p3[0] - p1[0]) / 6;
    const c2y = p2[1] - (p3[1] - p1[1]) / 6;
    d += ` C ${c1x.toFixed(1)} ${c1y.toFixed(1)}, ${c2x.toFixed(1)} ${c2y.toFixed(1)}, ${p2[0].toFixed(1)} ${p2[1].toFixed(1)}`;
  }
  return d;
}

const seriesPaths = SERIES.map((s) =>
  smoothPath(s.z.map((z, i) => [xAt(i), yAt(z)] as [number, number])),
);

export default function SignalChart({ className = "" }: { className?: string }) {
  const reduce = useReducedMotion();

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className={className}
      role="img"
      aria-label="跨平台声量共振示意：B站与微博声量共振，抖音错峰"
    >
      {/* 共振高亮区（B站 / 微博 同步抬升） */}
      <rect
        x={xAt(3.4)}
        y={PAD_T}
        width={xAt(7.6) - xAt(3.4)}
        height={PLOT_H}
        fill="rgba(59,130,246,0.14)"
      />

      {/* 水平网格 + z-score 标签 */}
      {[2, 1, 0, -1, -2].map((z) => (
        <g key={z}>
          <line
            x1={PAD_L}
            x2={PAD_L + PLOT_W}
            y1={yAt(z)}
            y2={yAt(z)}
            stroke={z === 0 ? "rgba(255,255,255,0.16)" : "rgba(255,255,255,0.07)"}
            strokeWidth={1}
          />
          <text
            x={PAD_L - 10}
            y={yAt(z) + 4}
            textAnchor="end"
            fontSize="11"
            fill="#8b97a8"
            fontFamily="var(--font-jetbrains), ui-monospace, monospace"
          >
            {z > 0 ? `+${z}` : `${z}`}
          </text>
        </g>
      ))}

      {/* X 轴刻度 */}
      {X_TICKS.map((t) => (
        <text
          key={t.label}
          x={xAt(t.i)}
          y={H - 20}
          textAnchor={t.i === 0 ? "start" : t.i === 15 ? "end" : "middle"}
          fontSize="11"
          fill="#8b97a8"
          fontFamily="var(--font-jetbrains), ui-monospace, monospace"
        >
          {t.label}
        </text>
      ))}

      {/* 曲线 */}
      {SERIES.map((s, idx) => (
        <motion.path
          key={s.name}
          d={seriesPaths[idx]}
          fill="none"
          stroke={s.color}
          strokeWidth={idx === 0 ? 2.4 : 1.8}
          strokeLinecap="round"
          strokeLinejoin="round"
          initial={reduce ? false : { pathLength: 0, opacity: 0 }}
          whileInView={reduce ? undefined : { pathLength: 1, opacity: 1 }}
          viewport={{ once: true, margin: "-40px" }}
          transition={{
            pathLength: { duration: 1.4, ease: [0.16, 1, 0.3, 1], delay: idx * 0.12 },
            opacity: { duration: 0.3 },
          }}
        />
      ))}

      {/* 共振标注 */}
      <g>
        <line
          x1={xAt(5)}
          x2={xAt(5)}
          y1={PAD_T + 4}
          y2={PAD_T + PLOT_H}
          stroke="#60a5fa"
          strokeWidth={1}
          strokeDasharray="3 3"
          opacity={0.5}
        />
        <text
          x={xAt(5) + 6}
          y={PAD_T + 14}
          fontSize="11"
          fill="#93c5fd"
        >
          共振
        </text>
      </g>
    </svg>
  );
}
