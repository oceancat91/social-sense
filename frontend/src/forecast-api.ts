/**
 * 预测数据源（热度预测 · 事件归因）。
 *
 * 对应后端 `backend/app/routes/forecast.py` 的只读接口：
 *   GET /api/v1/forecast/status          模型与产物状态
 *   GET /api/v1/forecast/dashboard-data  历史序列 + 6 步预测 + 分量 + 异常 + 报告
 *
 * 取数失败一律抛错，由调用方在面板里显示原因 —— 预测是可选功能，
 * 不能因为后端没装 numpy/torch 就影响三维终端本身。
 */

const API_BASE = (import.meta.env.VITE_API_BASE_URL || "/api/v1").replace(/\/+$/, "");
const REQUEST_TIMEOUT_MS = 20000;

export interface ForecastStatus {
  modelLoaded: boolean;
  loadError: string | null;
  checkpointName: string | null;
  servedAt: string | null;
}

export interface ForecastComponents {
  T: number[];
  S: number[];
  C: number[];
  R: number[];
}

export interface ForecastAnomaly {
  date: string;
  zMax: number;
  trigger: string;
  ot: number;
  fact?: string;
}

export interface ForecastDashboard {
  dates: string[];
  ot: number[];
  predictionDates: string[];
  prediction: number[];
  direction: string | null;
  directionDelta: number | null;
  spikeWarning: boolean;
  spikeGain: number | null;
  components: ForecastComponents | null;
  anomalies: ForecastAnomaly[];
  reportMarkdown: string;
  narrative: string | null;
}

interface Envelope<T> {
  code?: number;
  message?: string;
  data?: T;
}

/** 后端沿用 {code, message, data} 信封；兼容直接返回载荷的情况。 */
function unwrap<T>(body: unknown): T {
  if (body && typeof body === "object" && "data" in body) {
    const data = (body as Envelope<T>).data;
    if (data === undefined || data === null) {
      const message = (body as Envelope<T>).message;
      throw new Error(message || "后端未返回 data");
    }
    return data;
  }
  return body as T;
}

async function getJson<T>(path: string): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(`${API_BASE}/forecast${path}`, {
      signal: controller.signal,
      headers: { Accept: "application/json" },
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return unwrap<T>(await response.json());
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error("请求超时");
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

const numArray = (value: unknown): number[] =>
  Array.isArray(value) ? value.map((v) => Number(v)).filter((v) => Number.isFinite(v)) : [];

const strArray = (value: unknown): string[] =>
  Array.isArray(value) ? value.map((v) => String(v)) : [];

export async function fetchForecastStatus(): Promise<ForecastStatus> {
  const raw = await getJson<Record<string, unknown>>("/status");
  const model = (raw.model ?? null) as Record<string, unknown> | null;
  return {
    modelLoaded: Boolean(raw.model_loaded),
    loadError: typeof raw.load_error === "string" && raw.load_error ? raw.load_error : null,
    checkpointName:
      (typeof raw.checkpoint_name === "string" && raw.checkpoint_name) ||
      (model && typeof model.name === "string" ? model.name : null),
    servedAt: typeof raw.served_at === "string" ? raw.served_at : null,
  };
}

export async function fetchForecastDashboard(historyDays = 90): Promise<ForecastDashboard> {
  const raw = await getJson<Record<string, unknown>>(
    `/dashboard-data?hist=${encodeURIComponent(String(historyDays))}`,
  );

  const history = (raw.history ?? {}) as Record<string, unknown>;
  const prediction = (raw.prediction ?? {}) as Record<string, unknown>;
  const components = (raw.components ?? null) as Record<string, unknown> | null;

  const anomalies = Array.isArray(raw.anomalies)
    ? raw.anomalies.map((item) => {
        const a = (item ?? {}) as Record<string, unknown>;
        return {
          date: String(a.date ?? ""),
          zMax: Number(a.z_max ?? 0),
          trigger: String(a.trigger ?? ""),
          ot: Number(a.OT ?? a.ot ?? 0),
          fact: typeof a.fact === "string" ? a.fact : undefined,
        };
      })
    : [];

  return {
    dates: strArray(history.dates),
    ot: numArray(history.ot),
    predictionDates: strArray(prediction.dates),
    prediction: numArray(prediction.yhat_raw ?? prediction.yhat),
    direction: typeof prediction.direction === "string" ? prediction.direction : null,
    directionDelta: Number.isFinite(Number(prediction.direction_delta))
      ? Number(prediction.direction_delta)
      : null,
    spikeWarning: Boolean(prediction.spike_warning),
    spikeGain: Number.isFinite(Number(prediction.spike_gain)) ? Number(prediction.spike_gain) : null,
    components: components
      ? {
          T: numArray(components.T),
          S: numArray(components.S),
          C: numArray(components.C),
          R: numArray(components.R),
        }
      : null,
    anomalies,
    reportMarkdown: typeof raw.report_md === "string" ? raw.report_md : "",
    narrative: typeof raw.narrative === "string" ? raw.narrative : null,
  };
}

/** 去掉 markdown 标记，面板里按纯文本显示（不引入额外的 markdown 依赖）。 */
export function stripMarkdown(markdown: string): string {
  return markdown
    .replace(/```[\s\S]*?```/g, (block) => block.replace(/```[a-z]*\n?/g, ""))
    .replace(/^#{1,6}\s*/gm, "")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/^\s*[-*+]\s+/gm, "· ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}
