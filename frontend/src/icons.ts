/**
 * 箭头图标。
 *
 * 原先用的是 → ↗ ← ↑ ↓ 这些字体字形：不同平台会落到不同字体上，笔画粗细、
 * 箭头大小、基线位置各不相同（iOS 与 Windows 差异尤其明显），在大号标题旁边
 * 显得很随意。改成内联 SVG 后：
 *   - 宽高用 1em，跟随所在元素的 font-size，各处尺寸自动协调；
 *   - 描边用 currentColor，跟随悬浮/激活状态变色；
 *   - 线宽与端点形状完全可控，不再受字体影响。
 *
 * 注意：<kbd> 里的 ← → ↑ ↓ 是真实按键提示，必须保持字形，不要替换。
 */
const ARROW_PATHS = {
  right: "M4 12H19M13.5 6.5L19 12L13.5 17.5",
  left: "M20 12H5M10.5 6.5L5 12L10.5 17.5",
  up: "M12 20V5M6.5 10.5L12 5L17.5 10.5",
  down: "M12 4V19M6.5 13.5L12 19L17.5 13.5",
  "up-right": "M7 17L17 7M8.5 7H17V15.5",
  horizontal: "M4 12H20M7.5 8.5L4 12L7.5 15.5M16.5 8.5L20 12L16.5 15.5",
} as const;

export type ArrowDirection = keyof typeof ARROW_PATHS;

export function arrow(direction: ArrowDirection) {
  return `<svg class="arrow-glyph" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="${ARROW_PATHS[direction]}"/></svg>`;
}
