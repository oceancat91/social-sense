import content from "../content/archives.json" with { type: "json" };
import {
  validatePayload,
  type ArchiveRecord,
  type ArchivesPayload,
} from "./archives-api";

export type { ArchiveRecord } from "./archives-api";

/** 数据实际来自后端还是构建期兜底，导出按钮据此选择下载地址。 */
export type ArchiveSource = "api" | "static";

/**
 * 构建期快照先顶上：本模块的导出在 `main.ts` 里被模块级代码同步读取
 * （件位表、列记忆、初始选中项），必须 import 完就可用。
 * 后端数据在启动流程中经 `hydrate()` 替换进来，界面无需感知。
 */
const initial: ArchivesPayload = validatePayload(content);
let source: ArchiveSource = "static";

export let records: ArchiveRecord[] = initial.records;
export let categories: string[] = ["全部档案", ...initial.categories];
export let archiveColumns: string[] = initial.columns;

export const archiveSource = (): ArchiveSource => source;

/**
 * 用后端数据替换构建期快照。
 *
 * 只在阵列结构（分类顺序）一致时才接受：件位与列号是索引契约，
 * 列顺序一变，`fileLocation` / `fileAtSlot` 的既有结果就会错位。
 */
export function hydrate(next: ArchivesPayload): ArchiveSource {
  const validated = validatePayload(next);
  if (validated.columns.join("\u0000") !== archiveColumns.join("\u0000")) {
    throw new Error("档案阵列的列顺序与当前快照不一致，拒绝热替换");
  }
  records = validated.records;
  categories = ["全部档案", ...validated.categories];
  archiveColumns = validated.columns;
  source = "api";
  return source;
}

export function columnFiles(lane: number) {
  return records
    .map((record, index) => ({ record, index }))
    .filter(({ record }) => record.category === archiveColumns[lane])
    .map(({ index }) => index);
}
export function fileLocation(index: number) {
  const lane = archiveColumns.indexOf(records[index].category);
  const row = 12 + columnFiles(lane).indexOf(index);
  return { lane, row, slot: lane * 32 + row };
}
export function fileAtSlot(slot: number) {
  const files = columnFiles(Math.floor(slot / 32));
  return files[Math.max(0, Math.min(files.length - 1, (slot % 32) - 12))];
}
