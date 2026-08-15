# dataset/ — 单事件舆情标准数据集仓库

这里存放**单个舆情事件 / 话题**经 PlatformCrawler + StanceProfiler 处理后的正式数据包，供后续分析 Skill 与实验复用。

当前数据源平台：**哔哩哔哩（Bilibili）**。

---

## 目录约定

```text
dataset/
├── README.md                 ← 本说明
├── INDEX.md                  ← 事件索引表（每入库一条就追加一行）
└── events/
    └── <event_id>/
        ├── meta.json         ← 事件介绍、来源、时间窗、处理链路
        ├── D_platform.json   ← 标准数据包（DATASET_SPEC）
        └── stance_profile.json  ← 立场画像摘要（可选但推荐）
```

### `event_id` 命名建议

```text
{platform}_{keyword简写}_{since}_{until}
```

示例：`bilibili_期末周破防_20260801_20260815`

- 只用英文、数字、下划线，避免空格与特殊符号  
- `keyword` 可用拼音或压缩中文文件名安全形式  

---

## `meta.json` 必填字段

```json
{
  "event_id": "bilibili_示例_20260801_20260815",
  "title": "人类可读事件名",
  "keyword": "原始搜索/分析关键词",
  "platform": "bilibili",
  "platform_name_zh": "哔哩哔哩",
  "time_range": {
    "since": "YYYY-MM-DD",
    "until": "YYYY-MM-DD",
    "timezone": "Asia/Shanghai"
  },
  "granularity": "day",
  "description": "一两句话说明这个事件为什么采、分析什么",
  "source": {
    "type": "bilibili_video_comments",
    "method": "keyword_search + comment_crawl + clean_c1c8 + stance_profiler",
    "tools": [
      "PlatformCrawler",
      "StanceProfiler"
    ],
    "notes": "例如：按播放量取 Top-N 视频；评论模式 latest；页数限制等"
  },
  "files": {
    "D_platform": "D_platform.json",
    "stance_profile": "stance_profile.json"
  },
  "stats": {
    "n_text": 0,
    "n_buckets": 0,
    "empty_ratio": 0.0,
    "stance_global": "neutral",
    "is_empty": true
  },
  "schema_version": "dataset_schema_v1",
  "created_at": "ISO8601",
  "pipeline_versions": {
    "platform_crawler": "...",
    "stance_profiler": "..."
  }
}
```

---

## 来源说明（B 站）

| 项 | 说明 |
|----|------|
| 平台 | 哔哩哔哩（`platform=bilibili`） |
| 内容类型 | 关键词检索到的**视频**及其**评论区**（含部分二级回复，视采集参数） |
| 采集工具 | `PlatformCrawler`（搜索 + 评论爬虫 + C1–C8 清洗） |
| 画像工具 | `StanceProfiler`（立场/情绪/议题 + 重算时序指标） |
| 合规 | 使用个人账号 Cookie 拉取公开页面可读内容；仅供研究/课程项目，注意平台 ToS 与隐私 |

**不是**：全站全量评论、弹幕全量、用户私信，或官方商业数据授权库。

---

## 入库方式

### 推荐：StanceProfiler 一键写入

```powershell
cd d:\Pycharm\PycharmProject\cvProject\KobeBryant\pytorch

python -m StanceProfiler.pipeline `
  --in PlatformCrawler\outputs\D_platform_xxx.json `
  --to-dataset `
  --event-title "期末周破防（示例）" `
  --description "考试周破防相关视频评论舆情样本"
```

会在 `dataset/events/<event_id>/` 写出三件套，并更新 `INDEX.md`。

### 手动

把已校验的 `D_platform.json` 与 `stance_profile.json` 拷入对应事件目录，补齐 `meta.json`，并在 `INDEX.md` 登记一行。

---

## 质量门槛（入库前自检）

- [ ] `D_platform` 通过 `DATASET_SPEC` 校验  
- [ ] `D_meta.ext.stance_provisional == false`（已经过 StanceProfiler）  
- [ ] `meta.json` 来源与时间窗填写完整  
- [ ] 若 `is_empty=true`，仍可入库但须在 `description`/`notes` 写明原因（如时间窗错位）  

---

## 与代码模块关系

```text
PlatformCrawler  →  初版 D_platform（可 provisional）
StanceProfiler   →  正式画像 + 刷新 D_platform
dataset/events/* →  单事件归档（本目录）
```
