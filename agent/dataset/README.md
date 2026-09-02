# dataset/ — 单事件舆情标准数据集仓库

这里存放**单个舆情事件 / 话题**经 PlatformCrawler + StanceProfiler 处理后的正式数据包，供后续分析 Skill 与实验复用。

当前数据源平台：**哔哩哔哩、微博、小红书**。

---

## 目录约定

```text
dataset/
├── README.md                 ← 本说明
├── INDEX.md                  ← 事件索引表（每入库一条就追加一行）
├── real_multiplatform/       ← 清洗后真实多平台 ZIP 的接入结果
│   ├── manifest.json         ← 文件名解码、哈希、行数、时间窗与产物索引
│   ├── raw/                  ← 本地 CSV（已由 .gitignore 排除）
│   ├── reports/              ← 平台报告（含 D_ts、Skill2、Skill3）
│   └── fusion/               ← 同话题跨平台主控融合结果
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

## 清洗后多平台 ZIP 接入

`tools/import_clean_zips.py` 处理统一清洗 CSV，并完成：

1. 根据 ZIP UTF-8 标志解码中文文件名；旧式 ZIP 再尝试 CP437 → UTF-8/GB18030 恢复。
2. 文件名统一为 Unicode NFC，拒绝绝对路径与 `..` 路径穿越。
3. 识别 `platform / domain / broad|hot / hot_topic`，映射平台别名
   `bili → bilibili`、`xhs → xiaohongshu`。
4. 生成稳定内容 ID，执行 C1–C8、构建 `D_platform`、运行 Skill2 和 Skill3。
5. broad 数据按领域做 B站/微博融合；hot 数据按话题做 B站/微博/小红书融合。

```powershell
python agent/tools/import_clean_zips.py `
  --archive "bilibili=D:/data/data_bili_clean.zip" `
  --archive "weibo=D:/data/data_weibo_clean.zip" `
  --archive "xiaohongshu=D:/data/data_xhs_clean.zip"
```

可用 `--sample 1000` 做快速抽样验证，或用 `--text-tower` 在 Skill3 中同时启用
文本语义漂移分析。默认全量运行多尺度时序检测，但关闭高成本文本塔。

本次接入结果：60 个 CSV、391,187 条原始记录、390,015 条有效文本、60 份平台报告、
24 份跨平台融合结果。原始 CSV 只保存在本机；可复现的 manifest、报告与融合结果可入库。

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
