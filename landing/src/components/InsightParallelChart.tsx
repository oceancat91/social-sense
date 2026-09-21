"use client";

import { motion, useReducedMotion } from "motion/react";
import { LIEFLAT } from "@/components/lieflatTheme";

type Insight = {
  topic: string;
  points: number;
  resonance: number;
  echo: number;
};

const W = 860;
const H = 330;
const TOP = 54;
const BOTTOM = 270;
const AXES = [92, 430, 768];

const DIMS = [
  { key: "points", label: "时序点", min: 2600, max: 3400, format: (v: number) => Math.round(v).toLocaleString("en-US") },
  { key: "resonance", label: "声量共振", min: 0, max: 0.3, format: (v: number) => v.toFixed(2) },
  { key: "echo", label: "回声室", min: 0.2, max: 0.35, format: (v: number) => v.toFixed(2) },
] as const;

function yFor(dim: (typeof DIMS)[number], value: number) {
  return BOTTOM - ((value - dim.min) / (dim.max - dim.min)) * (BOTTOM - TOP);
}

function pathFor(values: number[]) {
  const ys = values.map((value, index) => yFor(DIMS[index], value));
  let path = `M ${AXES[0]} ${ys[0].toFixed(1)}`;
  for (let index = 0; index < AXES.length - 1; index += 1) {
    const middle = (AXES[index] + AXES[index + 1]) / 2;
    path += ` C ${middle} ${ys[index].toFixed(1)}, ${middle} ${ys[index + 1].toFixed(1)}, ${AXES[index + 1]} ${ys[index + 1].toFixed(1)}`;
  }
  return { path, ys };
}

/**
 * L20 Parallel Coordinates。
 * 一根发丝线代表一个真实话题，三根轴保留原始单位，不合并成虚构总分。
 */
export default function InsightParallelChart({ insights }: { insights: Insight[] }) {
  const reduce = useReducedMotion();
  const ranked = insights.map((item) => {
    const values = [item.points, item.resonance, item.echo];
    const score = values.reduce((sum, value, index) => {
      const dim = DIMS[index];
      return sum + (value - dim.min) / (dim.max - dim.min);
    }, 0);
    return { item, values, score, ...pathFor(values) };
  });
  const hero = ranked.reduce((best, current) =>
    current.score > best.score ? current : best,
  );

  return (
    <div className="lf-parallel">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label="四个真实话题在时序点、声量共振和回声室三个维度上的平行坐标比较"
      >
        {DIMS.map((dim, index) => (
          <g key={dim.key}>
            <line
              x1={AXES[index]}
              x2={AXES[index]}
              y1={TOP - 8}
              y2={BOTTOM + 8}
              stroke={LIEFLAT.FLOOR}
              strokeWidth="1.4"
            />
            {[TOP - 8, BOTTOM + 8].map((y) => (
              <line
                key={y}
                x1={AXES[index] - 5}
                x2={AXES[index] + 5}
                y1={y}
                y2={y}
                stroke={LIEFLAT.FLOOR}
                strokeWidth="1.4"
              />
            ))}
            <text
              x={AXES[index]}
              y={TOP - 22}
              textAnchor="middle"
              fontSize="11"
              fontWeight="800"
              letterSpacing="0.08em"
              fill={LIEFLAT.LAB}
            >
              {dim.label}
            </text>
            <text x={AXES[index] + 10} y={TOP - 3} fontSize="9" fill={LIEFLAT.FAINT}>
              {dim.format(dim.max)}
            </text>
            <text x={AXES[index] + 10} y={BOTTOM + 12} fontSize="9" fill={LIEFLAT.FAINT}>
              {dim.format(dim.min)}
            </text>
          </g>
        ))}

        {ranked.map(({ item, values, path, ys }, index) => {
          const isHero = item === hero.item;
          const stroke = isHero ? LIEFLAT.HERO : LIEFLAT.DATA2;
          return (
            <g key={item.topic}>
              <motion.path
                d={path}
                fill="none"
                stroke={stroke}
                strokeWidth={isHero ? 3 : 1.8}
                opacity={isHero ? 1 : 0.72}
                initial={reduce ? false : { pathLength: 0, opacity: 0 }}
                whileInView={reduce ? undefined : { pathLength: 1, opacity: isHero ? 1 : 0.72 }}
                viewport={{ once: false, margin: "-40px" }}
                transition={{ duration: 0.8, delay: index * 0.1, ease: [0.16, 1, 0.3, 1] }}
              >
                <title>
                  {`${item.topic} / 时序点 ${values[0]} / 声量共振 ${values[1].toFixed(2)} / 回声室 ${values[2].toFixed(2)}`}
                </title>
              </motion.path>
              {ys.map((y, axisIndex) => (
                <motion.circle
                  key={`${item.topic}-${axisIndex}`}
                  cx={AXES[axisIndex]}
                  cy={y}
                  r={isHero ? 4 : 2.7}
                  fill={stroke}
                  initial={reduce ? false : { scale: 0 }}
                  whileInView={reduce ? undefined : { scale: 1 }}
                  viewport={{ once: false, margin: "-40px" }}
                  transition={{ duration: 0.35, delay: 0.25 + index * 0.08 + axisIndex * 0.05 }}
                />
              ))}
            </g>
          );
        })}
      </svg>

      <ol className="lf-parallel__legend">
        {ranked.map(({ item }) => (
          <li key={item.topic}>
            <span
              className="lf-parallel__key"
              style={{ backgroundColor: item === hero.item ? LIEFLAT.HERO : LIEFLAT.DATA2 }}
            />
            <span>{item.topic}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
