"use client";

import { motion, useScroll, useTransform, useReducedMotion } from "motion/react";

/**
 * 全局背景层次层（从后到前）：
 * 1. atmosphere-base：浅冷白到冰蓝的空气渐变
 * 2. atmosphere-wave：远近三层柔性波场
 * 3. ambient-glow：大气光晕，随滚动视差缓慢下移
 * 均 fixed + pointer-events-none，不参与滚动容器重绘。
 */
export default function BackgroundLayers() {
  const reduce = useReducedMotion();
  const { scrollYProgress } = useScroll();
  const glowY = useTransform(scrollYProgress, [0, 1], ["0vh", "14vh"]);

  return (
    <>
      <div className="atmosphere-base" aria-hidden="true">
        <span className="atmosphere-wave atmosphere-wave--far" />
        <span className="atmosphere-wave atmosphere-wave--mid" />
        <span className="atmosphere-wave atmosphere-wave--near" />
      </div>
      <motion.div
        className="ambient-glow"
        style={reduce ? undefined : { y: glowY }}
        aria-hidden="true"
      />
    </>
  );
}
