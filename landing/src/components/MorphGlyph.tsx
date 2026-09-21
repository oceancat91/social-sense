"use client";

import { MorphIcon } from "morphicons/react";
import type { IconInput } from "morphicons/react";

/**
 * 全站唯一图标出口。
 *
 * 图标数据来自 `lucide`（数据包，非组件包），形变由 morphicons 的
 * 2D Procrustes + 极坐标插值完成：两个图形之间的旋转由数学推导，
 * 不需要手工声明 rotate。
 *
 * 静态用法（icon 不变）只渲染一次，无额外开销；
 * 一旦 icon 真的换了一个（FAQ 展开、菜单开合、刷新完成），
 * 形变会自动接管，无需 AnimatePresence 或 from/to 配对。
 *
 * strokeWidth 全局锁定为 2，与 Lucide 原始描边一致。
 *
 * 其余 props 一律透传到 svg：antd 的 Input.Password 会用 cloneElement
 * 往图标上注入 onClick 来切换密码可见性，包装层必须放行，否则开关会失效。
 */
export default function MorphGlyph({
  icon,
  size = 20,
  strokeWidth = 2,
  className,
  ...rest
}: {
  icon: IconInput;
  size?: number;
  strokeWidth?: number;
  className?: string;
} & Omit<
  React.SVGProps<SVGSVGElement>,
  // from / to 在此为 SVG 属性，但 MorphIcon 用它们表示受控变形的起止端点；
  // ref 也必须是 MorphHandle（morphTo / set），不是 SVGSVGElement
  "from" | "to" | "size" | "strokeWidth" | "className" | "ref"
>) {
  return (
    <MorphIcon
      icon={icon}
      size={size}
      strokeWidth={strokeWidth}
      className={className}
      reducedMotion="user"
      {...rest}
    />
  );
}
