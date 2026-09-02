/** 多 Agent 报告的状态映射常量（数据库 report.status 与 CT.CT_status） */

/** 分析任务状态（数据库 report.status） */
export const REPORT_STATUS = {
  pending: { text: '排队中', color: 'default' },
  collecting: { text: '采集中', color: 'processing' },
  running: { text: '分析中', color: 'processing' },
  success: { text: '成功', color: 'success' },
  partial: { text: '部分完成', color: 'warning' },
  failed: { text: '失败', color: 'error' },
}

/** 跨平台终裁状态（CT.CT_status） */
export const CT_STATUS = {
  accepted: { text: '已通过校准', color: 'success' },
  failed_calibration: { text: '校准未通过', color: 'warning' },
  single_platform: { text: '单平台降级', color: 'default' },
  provisional: { text: '待定', color: 'processing' },
}

/** 分析阶段定义（后端 progress.phase -> 展示名与序号） */
export const PHASES = [
  { key: 'collect', index: 1, text: '采集舆情数据' },
  { key: 'clean', index: 2, text: '清洗与情感分析' },
  { key: 'skill', index: 3, text: '单平台 Agent 分析' },
  { key: 'fusion', index: 4, text: '跨平台对齐融合' },
]

/** 平台进度状态 -> 展示 */
export const PLATFORM_STATUS = {
  pending: { text: '等待', color: 'default' },
  running: { text: '采集中', color: 'processing' },
  done: { text: '完成', color: 'success' },
}
