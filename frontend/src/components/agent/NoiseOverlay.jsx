/**
 * 全局噪点纹理层：打破数字平面感（surface texture）。
 * 固定定位、pointer-events 穿透，低透明度 SVG feTurbulence 颗粒。
 */
export default function NoiseOverlay() {
  return <div className="noise-overlay" aria-hidden="true" />
}
