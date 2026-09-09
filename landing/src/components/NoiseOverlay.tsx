/**
 * 全局噪点纹理层：极克制的 surface texture。
 * fixed + pointer-events-none，不参与滚动容器重绘。
 */
export default function NoiseOverlay() {
  return <div aria-hidden="true" className="noise-overlay" />;
}
