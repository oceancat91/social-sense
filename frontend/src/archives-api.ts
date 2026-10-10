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
 * 阵列结构契约。件位（slot）、列（lane）与行（row）都由数组下标派生，
 * 所以分类数、每类档案数、编号顺序都不能变——否则热替换会错位。
 */
const REQUIRED_CATEGORIES = 5;
const REQUIRED_RECORDS = 40;
const REQUIRED_PER_CATEGORY = 8;

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
    if (!Array.isArray(names) || names.length !== REQUIRED_CATEGORIES || !names.every(isText)) {
      fail(`${key}：必须包含 ${REQUIRED_CATEGORIES} 个非空分类名称`);
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
  if (!Array.isArray(records) || records.length !== REQUIRED_RECORDS) {
    fail(`records：当前阵列要求 ${REQUIRED_RECORDS} 份档案`);
  }

  records.forEach((record, index) => {
    const label = `records[${index}]`;
    if (!record || typeof record !== "object" || Array.isArray(record)) fail(`${label}：必须是档案对象`);
    const entry = record as Partial<ArchiveRecord>;
    for (const key of ["title", "en", "department", "category", "date", "lead", "clearance", "abstract", "source"] as const) {
      if (!isText(entry[key])) fail(`${label}.${key}：必须是非空文本`);
    }
    const expectedId = `X-${String(index + 1).padStart(3, "0")}`;
    if (entry.id !== expectedId) fail(`${label}.id：应为 ${expectedId}，编号须按顺序保持稳定`);
    if (!cats.includes(entry.category as string)) fail(`${label}.category：未知分类 ${entry.category}`);
    const findings = entry.findings;
    if (!Array.isArray(findings) || findings.length === 0 || !findings.every(isText)) {
      fail(`${label}.findings：必须包含至少一条非空研究记录`);
    }
  });

  for (const name of cols) {
    if (records.filter((r) => (r as ArchiveRecord).category === name).length !== REQUIRED_PER_CATEGORY) {
      fail(`分类「${name}」：当前阵列要求 ${REQUIRED_PER_CATEGORY} 份档案`);
    }
  }

  return value as ArchivesPayload;
}

/** 从后端拉取档案阵列。失败时抛错，由调用方决定是否回落到静态副本。 */
export async function fetchArchives(): Promise<ArchivesPayload> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(`${API_BASE}/archives`, {
      signal: controller.signal,
      headers: { Accept: "application/json" },
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const body: unknown = await response.json();
    // 后端沿用 {code, message, data} 信封；兼容直接返回载荷的情况。
    const payload =
      body && typeof body === "object" && "data" in body
        ? (body as { data: unknown }).data
        : body;
    return validatePayload(payload);
  } finally {
    clearTimeout(timer);
  }
}

/** 单份档案的导出地址（对应界面上的 EXPORT 按钮）。 */
export function archiveDownloadUrl(id: string): string {
  return `${API_BASE}/archives/${encodeURIComponent(id)}/download`;
}
