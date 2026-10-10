/** Rendering controls are independent of lighting, materials and animation. */
export type RenderQuality = {
  scale: number;
  pixelRatio: number;
  antialias: "off" | "smaa";
  shadows: number;
  aoSamples: number;
  aoResolution: number;
  depthOfField: number;
  transmission: number;
  anisotropy: number;
};

export const qualityPresets = {
  performance: {
    scale: 80,
    pixelRatio: 1,
    antialias: "off",
    shadows: 1024,
    aoSamples: 0,
    aoResolution: 0.5,
    depthOfField: 0,
    transmission: 0.5,
    // 各向异性过滤几乎不花钱（实测 4×→16× 只差约 1 fps），但档案架是大角度
    // 倾斜视角，竖板标签的清晰度基本由它决定 —— 所以这里保持最高值，
    // 把预算省在真正昂贵的 AO / 景深 / 渲染比例上。
    anisotropy: 16,
  },
  original: {
    scale: 100,
    pixelRatio: 1.5,
    antialias: "off",
    shadows: 2048,
    aoSamples: 32,
    aoResolution: 1,
    depthOfField: 100,
    transmission: 1,
    anisotropy: 16,
  },
  high: {
    scale: 125,
    pixelRatio: 2,
    antialias: "smaa",
    shadows: 4096,
    aoSamples: 32,
    aoResolution: 1,
    depthOfField: 100,
    transmission: 1,
    anisotropy: 16,
  },
  ultra: {
    scale: 150,
    pixelRatio: 2,
    antialias: "smaa",
    shadows: 4096,
    aoSamples: 64,
    aoResolution: 1,
    depthOfField: 100,
    transmission: 1,
    anisotropy: 16,
  },
} as const satisfies Record<string, RenderQuality>;
/** Drops resolution, shadows and postprocessing further than any preset. */
export const superPerformanceQuality: RenderQuality = {
  scale: 60, pixelRatio: 1, antialias: "off", shadows: 0, aoSamples: 0,
  aoResolution: .5, depthOfField: 0, transmission: .25, anisotropy: 2,
};
export type QualityPreset = keyof typeof qualityPresets;
export const presetLabels: Record<QualityPreset, string> = {
  performance: "性能",
  original: "原始",
  high: "高",
  ultra: "极高",
};

/**
 * 首次访问的画质起点。
 *
 * `original` 是按独立显卡定的（pixelRatio 1.5 / AO 32 采样 / 景深 100），
 * 在集成显卡上大分辨率下只剩个位数帧率。这里只在用户**从未保存过**画质偏好时，
 * 按 GPU 能力挑一个跑得顺的起点；用户一旦在设置里改过画质，就永远以用户选择为准。
 */

/** 软件光栅化（无硬件加速）：任何后处理都会拖垮它。 */
const SOFTWARE_RENDERER =
  /swiftshader|llvmpipe|softpipe|software|basic render|microsoft basic/i;
/** 独显与 Apple 统一内存 GPU：吃得下 original 档。 */
const CAPABLE_RENDERER =
  /nvidia|geforce|rtx|quadro|radeon\s*(rx|pro|vii)|arc\s*a\d|apple\s*m\d/i;
/** 集成显卡：共享内存带宽，对 AO 与景深开销最敏感。 */
const INTEGRATED_RENDERER =
  /intel|hd graphics|uhd|iris|radeon|vega|mali|adreno|powervr|qualcomm|graphics/i;

/** 约 2560×1440 的 CSS 像素量；渲染器识别不出来时的兜底阈值。 */
const LARGE_SCREEN_PIXELS = 3_000_000;

export type GpuTier = "software" | "integrated" | "capable" | "unknown";

/** 读 WebGL 渲染器标识；探针上下文用完立即释放，不占用 WebGL 槽位。 */
export function detectRenderer(): string | null {
  try {
    const probe = document.createElement("canvas");
    const gl = (probe.getContext("webgl2") ??
      probe.getContext("webgl")) as WebGLRenderingContext | null;
    if (!gl) return null;
    const info = gl.getExtension("WEBGL_debug_renderer_info");
    const renderer = String(
      (info
        ? gl.getParameter(info.UNMASKED_RENDERER_WEBGL)
        : gl.getParameter(gl.RENDERER)) ?? "",
    );
    gl.getExtension("WEBGL_lose_context")?.loseContext();
    return renderer || null;
  } catch {
    return null;
  }
}

/** 先判软件渲染，再判独显——"AMD Radeon RX" 同时含 radeon，顺序不能反。 */
export function classifyRenderer(renderer: string | null): GpuTier {
  if (!renderer) return "unknown";
  if (SOFTWARE_RENDERER.test(renderer)) return "software";
  if (CAPABLE_RENDERER.test(renderer)) return "capable";
  if (INTEGRATED_RENDERER.test(renderer)) return "integrated";
  return "unknown";
}

function screenPixels(): number {
  try {
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    return (window.screen?.width ?? 0) * (window.screen?.height ?? 0) * ratio * ratio;
  } catch {
    return 0;
  }
}

/** 首次访问建议的画质。返回预设副本，设置面板能正确显示对应档位。 */
export function recommendedQuality(): RenderQuality {
  const renderer = detectRenderer();
  const tier = classifyRenderer(renderer);
  const pixels = screenPixels();
  const light =
    tier === "software" ||
    tier === "integrated" ||
    (tier === "unknown" && pixels >= LARGE_SCREEN_PIXELS);
  console.info(
    `[quality] GPU 类型 ${tier} · ${renderer ?? "无法识别"} · ` +
      `${Math.round(pixels / 1000)}k px → 初始画质 ${light ? "性能" : "原始"}` +
      "（可在系统设置中更改）",
  );
  return light ? { ...qualityPresets.performance } : { ...qualityPresets.original };
}

/**
 * performance 预设曾把 anisotropy 定为 4，而各向异性过滤决定了档案架竖板上
 * 标签在倾斜视角下的清晰度（16× 只贵约 1 fps）。已经落盘的旧值需要抬回来，
 * 否则改预设也救不到老访客。
 *
 * 只在存储值**恰好等于旧预设指纹**时迁移——那是自动选档写进去的，用户自己的
 * 任何微调都不会命中，因此不会被覆盖。
 */
const LEGACY_PERFORMANCE_ANISOTROPY: RenderQuality = {
  scale: 80,
  pixelRatio: 1,
  antialias: "off",
  shadows: 1024,
  aoSamples: 0,
  aoResolution: 0.5,
  depthOfField: 0,
  transmission: 0.5,
  anisotropy: 4,
};

export function migrateStoredQuality(value: unknown): unknown {
  if (!value || typeof value !== "object" || Array.isArray(value)) return value;
  const stored = value as Record<string, unknown>;
  const matchesLegacy = (
    Object.keys(LEGACY_PERFORMANCE_ANISOTROPY) as (keyof RenderQuality)[]
  ).every((key) => stored[key] === LEGACY_PERFORMANCE_ANISOTROPY[key]);
  if (!matchesLegacy) return value;
  console.info("[quality] 迁移旧的“性能”预设：anisotropy 4 → 16（恢复竖板标签清晰度）");
  return { ...stored, anisotropy: 16 };
}

const member = <T>(value: unknown, choices: readonly T[], fallback: T): T =>
  choices.includes(value as T) ? (value as T) : fallback;
const range = (
  value: unknown,
  min: number,
  max: number,
  step: number,
  fallback: number,
) =>
  typeof value === "number" && Number.isFinite(value)
    ? Math.min(max, Math.max(min, Math.round(value / step) * step))
    : fallback;

export function normalizeQuality(
  value: unknown,
  legacyHigh = true,
): RenderQuality {
  const base = qualityPresets.original;
  const v =
    value && typeof value === "object"
      ? (value as Record<string, unknown>)
      : {};
  // Older low quality retained full resolution, shadows and transmission.
  const fallback = legacyHigh
    ? base
    : { ...base, pixelRatio: 1, aoSamples: 0, depthOfField: 0 };
  return {
    scale: range(v.scale, 50, 200, 5, fallback.scale),
    pixelRatio: member(v.pixelRatio, [1, 1.5, 2, 3], fallback.pixelRatio),
    antialias: member(
      v.antialias,
      ["off", "smaa"] as const,
      fallback.antialias,
    ),
    shadows: member(v.shadows, [0, 1024, 2048, 4096], fallback.shadows),
    aoSamples: member(v.aoSamples, [0, 16, 32, 64], fallback.aoSamples),
    aoResolution: member(v.aoResolution, [0.5, 0.75, 1], fallback.aoResolution),
    depthOfField: range(v.depthOfField, 0, 150, 5, fallback.depthOfField),
    transmission: member(
      v.transmission,
      [0.25, 0.5, 0.75, 1],
      fallback.transmission,
    ),
    anisotropy: member(v.anisotropy, [1, 2, 4, 8, 16], fallback.anisotropy),
  };
}

export function matchingPreset(
  quality: RenderQuality,
): QualityPreset | "custom" {
  return (
    (Object.keys(qualityPresets) as QualityPreset[]).find((key) =>
      Object.entries(qualityPresets[key]).every(
        ([field, value]) => quality[field as keyof RenderQuality] === value,
      ),
    ) ?? "custom"
  );
}

export function renderDimensions(
  quality: RenderQuality,
  width: number,
  height: number,
  stageScale: number,
  deviceRatio: number,
  maxTextureSize: number,
  pixelBudget = 8_294_400,
) {
  const requested =
    (Math.min(deviceRatio, quality.pixelRatio) * stageScale * quality.scale) /
    100;
  // Bound all full-resolution postprocessing targets to 8.3 MP and device limits.
  const ratio = Math.min(
    requested,
    Math.sqrt(pixelBudget / Math.max(1, width * height)),
    maxTextureSize / Math.max(1, width, height),
  );
  return {
    ratio,
    width: Math.max(1, Math.floor(width * ratio)),
    height: Math.max(1, Math.floor(height * ratio)),
    limited: ratio < requested - 0.0001,
  };
}
