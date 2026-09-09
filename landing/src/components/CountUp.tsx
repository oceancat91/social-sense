"use client";

import { useEffect, useRef } from "react";
import {
  motion,
  useMotionValue,
  useTransform,
  useReducedMotion,
  useInView,
  animate,
} from "motion/react";

/**
 * 数字滚动（count-up）：进入视口后把真实指标从 0 滚动到目标值。
 * 用 motion value 直接渲染文本，避免在 rAF 中触碰 React state。
 * 尊重 prefers-reduced-motion（直接落到终值）。
 */
export default function CountUp({
  value,
  format,
  duration = 1.1,
  className = "",
}: {
  value: number;
  format: (v: number) => string;
  duration?: number;
  className?: string;
}) {
  const reduce = useReducedMotion();
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: false, margin: "-40px" });
  const mv = useMotionValue(0);
  const text = useTransform(mv, format);

  useEffect(() => {
    if (!inView) {
      mv.set(0);
      return;
    }
    if (reduce) {
      mv.set(value);
      return;
    }
    const controls = animate(mv, value, {
      duration,
      ease: [0.16, 1, 0.3, 1],
    });
    return () => controls.stop();
  }, [inView, value, reduce, duration, mv]);

  return (
    <motion.span ref={ref} className={className}>
      {text}
    </motion.span>
  );
}
