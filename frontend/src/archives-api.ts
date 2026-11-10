/**
 * 运行期档案数据源。
 *
 * 档案阵列此前由 `content/archives.json` 在构建期静态导入，观测数据一变就得重新
 * 构建并部署前端。现在改为向后端 `GET /api/v1/archives` 取数，构建产物里的那份
 * JSON 降级为「后端不可用 / 离线」时的兜底，界面本身无需改动。
 */

export interface ArchiveRecord {
  id: string;
  title: string;
  en: string;
  department: string;
  category: string;
  date: string;
  lead: string;
  clearance: string;
  abstract: string;
  findings: string[];
  source: string;
}

export interface ArchivesPayload {
  categories: string[];
  columns: string[];
  records: ArchiveRecord[];
}

/**
 * 阵列结构契约。
 *
 * 件位（slot）与列（lane）仍由数组下标派生，所以【同一次运行内】的分类顺序必须稳定；
 * 但阵列规模不再写死 —— 现在数据源是 6 个舆情事件（1 个分类），
 * 之前的 5 分类 / 40 条 / 每类 8 条是针对旧档案集的，换成事件集后必须放宽，
 * 否则页面直接抛校验错误、3D 场景起不来。
 *
 * 保留的约束（这些才是渲染真正依赖的）：
 *   - 分类与列必须一一对应、不重复
 *   - 每条记录的 category 必须属于分类集合
 *   - id / title / en 等字段非空、findings 非空
 *   - 编号唯一（不再强制 X-001 这种按序格式）
 */
const MIN_CATEGORIES = 1;
const MIN_RECORDS = 1;

const API_BASE = (import.meta.env.VITE_API_BASE_URL || "/api/v1").replace(/\/+$/, "");
const REQUEST_TIMEOUT_MS = 8000;

const isText = (value: unknown): value is string =>
  typeof value === "string" && value.trim().length > 0;

function fail(reason: string): never {
  throw new Error(`档案数据校验失败：${reason}`);
}

/** 校验后端（或兜底文件）下发的载荷，避免把渲染不了的数据交给界面。 */
export function validatePayload(value: unknown): ArchivesPayload {
  if (!value || typeof value !== "object" || Array.isArray(value)) fail("必须是 JSON 对象");
  const source = value as Partial<ArchivesPayload>;

  const categories = source.categories;
  const columns = source.columns;
  for (const [key, names] of [["categories", categories], ["columns", columns]] as const) {
    if (!Array.isArray(names) || names.length < MIN_CATEGORIES || !names.every(isText)) {
      fail(`${key}：至少需要 ${MIN_CATEGORIES} 个非空分类名称`);
    }
  }
  const cats = categories as string[];
  const cols = columns as string[];
  if (new Set(cats).size !== cats.length || new Set(cols).size !== cols.length) {
    fail("分类名称不能重复");
  }
  if (cats.some((name) => !cols.includes(name)) || cols.some((name) => !cats.includes(name))) {
    fail("categories 与 columns 必须包含相同的分类");
  }

  const records = source.records;
  if (!Array.isArray(records) || records.length < MIN_RECORDS) {
    fail(`records：至少需要 ${MIN_RECORDS} 条记录`);
  }

  const seenIds = new Set<string>();
  records.forEach((record, index) => {
    const label = `records[${index}]`;
    if (!record || typeof record !== "object" || Array.isArray(record)) fail(`${label}：必须是档案对象`);
    const entry = record as Partial<ArchiveRecord>;
    for (const key of ["title", "en", "department", "category", "date", "lead", "clearance", "abstract", "source"] as const) {
      if (!isText(entry[key])) fail(`${label}.${key}：必须是非空文本`);
    }
    if (!isText(entry.id)) fail(`${label}.id：必须是非空文本`);
    if (seenIds.has(entry.id as string)) fail(`${label}.id：编号重复 ${entry.id}`);
    seenIds.add(entry.id as string);
    if (!cats.includes(entry.category as string)) fail(`${label}.category：未知分类 ${entry.category}`);
    const findings = entry.findings;
    if (!Array.isArray(findings) || findings.length === 0 || !findings.every(isText)) {
      fail(`${label}.findings：必须包含至少一条非空研究记录`);
    }
  });

  for (const name of cols) {
    if (!records.some((r) => (r as ArchiveRecord).category === name)) {
      fail(`分类「${name}」下没有任何记录`);
    }
  }

  return value as ArchivesPayload;
}

/** 从后端拉取档案阵列。失败时抛错，由调用方决定是否回落到静态副本。 */
type EventItem = {
  event_id: string;
  name: string;
  description?: string;
  keywords?: string[];
  start: string;
  end: string;
  days: number;
  volume: number;
  peak: number;
  peak_day: string;
  tau_days?: number | null;
  half_life_days?: number | null;
  decay_to_10pct_days?: number | null;
};

/**
 * 把事件接口的返回折算成档案阵列载荷。
 *
 * 为什么在前端折算而不改后端 `/archives`：那个端点服务于旧的「5 分类 × 8 领域」
 * 观测报告体系，数据源是 cross-platform 报告目录；事件体系是另一套语义，
 * 硬塞进同一个端点会把两套契约搅在一起。这里只做形状适配，语义各归各。
 */
function eventsToPayload(events: EventItem[]): ArchivesPayload {
  const records: ArchiveRecord[] = events.map((e, index) => {
    const findings: string[] = [
      `峰值日 ${e.peak_day}，峰值声量 ${Math.round(e.peak).toLocaleString()}`,
      `观测区间 ${e.start} ~ ${e.end}（${e.days} 天，累计 ${Math.round(e.volume).toLocaleString()}）`,
    ];
    if (e.tau_days) {
      findings.push(
        `舆论半衰期 ${e.half_life_days ?? "—"} 天（τ=${e.tau_days} 天，衰减到 1/10 需 ${e.decay_to_10pct_days ?? "—"} 天）`,
      );
    }
    if (e.keywords?.length) findings.push(`关键词：${e.keywords.join("、")}`);
    return {
      id: `E-${String(index + 1).padStart(3, "0")}`,
      title: e.name,
      en: e.event_id.replace(/_/g, " ").toUpperCase(),
      department: "多平台观测",
      category: "事件",
      date: `${e.start} 至 ${e.end}`,
      lead: `${e.days} 天 / ${Math.round(e.volume).toLocaleString()}`,
      clearance: `PEAK ${Math.round(e.peak).toLocaleString()}`,
      abstract: e.description || "",
      findings,
      source: "政策舆情研究数据集",
    };
  });
  return { categories: ["事件"], columns: ["事件"], records };
}

export async function fetchArchives(): Promise<ArchivesPayload> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    // 首选事件接口；失败再退回旧的档案端点（构建期静态副本仍是最终兜底）。
    const response = await fetch(`${API_BASE}/forecast/events`, {
      signal: controller.signal,
      headers: { Accept: "application/json" },
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const body: unknown = await response.json();
    const data =
      body && typeof body === "object" && "data" in body
        ? (body as { data: { events?: EventItem[] } }).data
        : (body as { events?: EventItem[] });
    const events = data?.events;
    if (!Array.isArray(events) || events.length === 0) throw new Error("事件列表为空");
    return validatePayload(eventsToPayload(events));
  } finally {
    clearTimeout(timer);
  }
}

/** 单份档案的导出地址（对应界面上的 EXPORT 按钮）。 */
export function archiveDownloadUrl(id: string): string {
  return `${API_BASE}/archives/${encodeURIComponent(id)}/download`;
}
