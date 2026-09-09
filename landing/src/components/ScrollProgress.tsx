"use client";

import { motion, useScroll, useSpring, useReducedMotion } from "motion/react";

/**
 * 顶部滚动进度条（Scroll Progress Path）
 * 传达「当前阅读进度」，细线 + 渐变深蓝，克制。
 * 用 useScroll + useSpring 驱动 scaleX，不触碰 React state，零重渲染。
 */
export default function ScrollProgress() {
  const reduce = useReducedMotion();
  const { scrollYProgress } = useScroll();
  const scaleX = useSpring(scrollYProgress, {
    stiffness: 120,
    damping: 30,
    restDelta: 0.001,
  });

  if (reduce) return null;

  return (
    <motion.div
      aria-hidden="true"
      style={{ scaleX }}
      className="fixed inset-x-0 top-0 z-[60] h-[2px] origin-left bg-gradient-to-r from-accent to-accent-deep"
    />
  );
}
