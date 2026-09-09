"use client";

import { motion, useReducedMotion } from "motion/react";
import { LIEFLAT } from "@/components/lieflatTheme";

const W = 720;
const H = 330;
const PAD_L = 46;
const PAD_R = 14;
const PAD_T = 34;
const PAD_B = 54;
const PLOT_W = W - PAD_L - PAD_R;
const PLOT_H = H - PAD_T - PAD_B;

function xAt(index: number) {
  return PAD_L + (index / 15) * PLOT_W;
}

function yAt(zScore: number) {
  return PAD_T + ((2 - zScore) / 4) * PLOT_H;
}

const SERIES = [
  {
    name: "B站",
    color: LIEFLAT.SERIES[0],
    z: [0, 0.3, 0.8, 1.4, 1.9, 2.1, 2, 1.5, 0.8, 0.1, -0.4, -0.5, -0.3, -0.1, 0, 0],
  },
  {
    name: "微博",
    color: LIEFLAT.SERIES[1],
    z: [-0.2, 0.1, 0.5, 1, 1.4, 1.6, 1.5, 1.1, 0.6, 0.1, -0.2, -0.3, -0.2, -0.1, 0, 0],
  },
  {
    name: "抖音",
    color: LIEFLAT.SERIES[2],
    z: [0, 0, 0.1, 0.2, 0.3, 0.4, 0.7, 1.2, 1.7, 2, 1.8, 1.3, 0.8, 0.4, 0.1, 0],
  },
  {
    name: "小红书",
    color: LIEFLAT.SERIES[3],
    z: [0.1, 0, 0.1, 0, 0.1, 0, 0.1, 0, 0.1, 0, 0.1, 0, 0.1, 0, 0.1, 0],
  },
];

const X_TICKS = [
  { i: 0, label: "8/01" },
  { i: 5, label: "8/06" },
  { i: 10, label: "8/11" },
  { i: 15, label: "8/16" },
];

const seriesPaths = SERIES.map((series) =>
  series.z
    .map(
      (value, index) =>
        `${index === 0 ? "M" : "L"} ${xAt(index).toFixed(1)} ${yAt(value).toFixed(1)}`,
    )
    .join(" "),
);

/**
 * F2 Hairline Line 的多序列适配。
 * 每个时间桶保留地板刻度和数据点，折线不平滑，避免制造不存在的中间趋势。
 */
export default function SignalChart({ className = "" }: { className?: string }) {
  const reduce = useReducedMotion();

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className={className}
      role="img"
      aria-label="跨平台声量时序：B站与微博同步抬升，抖音错峰"
    >
      {Array.from({ length: 16 }, (_, index) => (
        <line
          key={`floor-${index}`}
          x1={xAt(index)}
          x2={xAt(index)}
          y1={PAD_T + PLOT_H}
          y2={PAD_T + PLOT_H + (index % 5 === 0 ? 9 : 5)}
          stroke={LIEFLAT.FLOOR}
          strokeWidth="1"
        />
      ))}

      <rect
        x={xAt(3.4)}
        y={PAD_T}
        width={xAt(7.6) - xAt(3.4)}
        height={PLOT_H}
        fill={LIEFLAT.QUIET}
      />

      {[2, 1, 0, -1, -2].map((zScore) => (
        <g key={zScore}>
          <line
            x1={PAD_L}
            x2={PAD_L + PLOT_W}
            y1={yAt(zScore)}
            y2={yAt(zScore)}
            stroke={zScore === 0 ? LIEFLAT.DATA2 : LIEFLAT.GRID}
            strokeWidth={zScore === 0 ? 1.4 : 0.8}
          />
          <text
            x={PAD_L - 10}
            y={yAt(zScore) + 4}
            textAnchor="end"
            fontSize="11"
            fill={LIEFLAT.MUT}
            fontFamily="var(--font-jetbrains), ui-monospace, monospace"
          >
            {zScore > 0 ? `+${zScore}` : zScore}
          </text>
        </g>
      ))}

      {X_TICKS.map((tick) => (
        <text
          key={tick.label}
          x={xAt(tick.i)}
          y={H - 23}
          textAnchor={tick.i === 0 ? "start" : tick.i === 15 ? "end" : "middle"}
          fontSize="11"
          fill={LIEFLAT.MUT}
          fontFamily="var(--font-jetbrains), ui-monospace, monospace"
        >
          {tick.label}
        </text>
      ))}

      {SERIES.map((series, seriesIndex) => (
        <g key={series.name}>
          <motion.path
            d={seriesPaths[seriesIndex]}
            fill="none"
            stroke={series.color}
            strokeWidth={seriesIndex === 0 ? 2.2 : 1.8}
            strokeLinecap="round"
            strokeLinejoin="round"
            initial={reduce ? false : { pathLength: 0, opacity: 0 }}
            whileInView={reduce ? undefined : { pathLength: 1, opacity: 1 }}
            viewport={{ once: false, margin: "-40px" }}
            transition={{
              pathLength: {
                duration: 1.1,
                ease: [0.16, 1, 0.3, 1],
                delay: seriesIndex * 0.1,
              },
              opacity: { duration: 0.3 },
            }}
          />
          {series.z.map((value, pointIndex) => {
            const weekend = pointIndex % 7 < 2;
            return (
              <motion.circle
                key={`${series.name}-${pointIndex}`}
                cx={xAt(pointIndex)}
                cy={yAt(value)}
                r={seriesIndex === 0 ? 3 : 2.2}
                fill={weekend ? LIEFLAT.BG : series.color}
                stroke={series.color}
                strokeWidth={weekend ? 1.5 : 0.8}
                initial={reduce ? false : { scale: 0, opacity: 0 }}
                whileInView={reduce ? undefined : { scale: 1, opacity: 1 }}
                viewport={{ once: false, margin: "-40px" }}
                transition={{
                  duration: 0.35,
                  delay: 0.2 + seriesIndex * 0.06 + pointIndex * 0.018,
                  ease: [0.16, 1, 0.3, 1],
                }}
              >
                <title>
                  {`${series.name} / 8月${String(pointIndex + 1).padStart(2, "0")}日 / ${value > 0 ? "+" : ""}${value.toFixed(1)}`}
                </title>
              </motion.circle>
            );
          })}
        </g>
      ))}

      <line
        x1={xAt(5)}
        x2={xAt(5)}
        y1={PAD_T + 4}
        y2={PAD_T + PLOT_H}
        stroke={LIEFLAT.HERO}
        strokeWidth="1"
        strokeDasharray="3 3"
      />
      <text
        x={xAt(5) + 6}
        y={PAD_T + 14}
        fontSize="11"
        fontWeight="700"
        fill={LIEFLAT.HERO}
      >
        共振
      </text>

      <text
        x={PAD_L}
        y={H - 5}
        fontSize="9"
        fontWeight="600"
        letterSpacing="0.08em"
        fill={LIEFLAT.FAINT}
      >
        一点代表一个时间桶 / 空心点代表周末 / 浅蓝区代表同步抬升窗口
      </text>
    </svg>
  );
}
