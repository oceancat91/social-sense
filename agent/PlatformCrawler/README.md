# PlatformCrawler（平台采集 Skill）

一句话：输入**话题词 + 时间范围**，自动完成「搜视频 → 抓评论 → 清洗 → 做成标准舆情数据集」。

当前只接了 **B 站**。产出文件符合项目根目录的 [`DATASET_SPEC.md`](../DATASET_SPEC.md)。

---

## 它能干什么？

```text
你给关键词（如「舞剧红楼梦」）
        │
        ▼
  ① 全站搜索相关视频（可按播放量选最热的几个）
        │
        ▼
  ② 抓这些视频下的评论
        │
        ▼
  ③ 自动清洗（去噪、去重、按时间裁剪……）
        │
        ▼
  ④ 生成标准数据包 D_platform.json
     · D_text：一条条评论
     · D_ts  ：按天/小时的声量、评论热度、**话题热度 topic_heat**、情绪、争议等
     · D_meta：任务说明、空窗比例、topic_heat 峰值摘要等
```

`volume`/`heat` 来自评论；`topic_volume`/`topic_heat` 来自搜索视频按**发布日**汇总（适合「爆发→至今」长轴）。

---

## 使用前准备（只需一次）

1. 打开终端，进入**项目根目录**（注意是 `pytorch` 这一层）：

```powershell
cd d:\Pycharm\PycharmProject\cvProject\KobeBryant\pytorch
```

2. 安装依赖（若未装过）：

```powershell
pip install requests pandas playwright
playwright install chromium
```

3. 登录 B 站，保存 Cookie（必须在 `PlatformCrawler\crawler` 里跑）：

```powershell
cd PlatformCrawler\crawler
python auto_get_cookie.py
```

浏览器弹出后扫码/账号登录，看到「登录成功」即可。  
检查是否有效：

```powershell
python setup_cookie.py --check
cd ..\..
```

> Cookie 过期后，搜索或爬评论会失败，再跑一次 `auto_get_cookie.py`。

---

## 最常用：一键跑通

仍在 **`pytorch` 根目录**执行：

```powershell
python -m PlatformCrawler.pipeline 舞剧红楼梦 --since 2026-07-01 --until 2026-08-14 --max-videos 3 --comment-pages 2
```

含义：

| 参数 | 意思 |
|------|------|
| `舞剧红楼梦` | 要分析的话题 |
| `--since` / `--until` | **同时**约束：① 搜索视频的发布时间；② **评论爬取与保留**的时间窗（含首尾两天） |
| `--max-videos 3` | 只抓最热的 3 个视频 |
| `--comment-pages 2` | 每个视频最多爬 2 页一级评论（历史窗请加大，见下文） |

默认已按**播放量**选热门视频（`--order click --rank-by play`）。

跑完后看这里：

| 文件 | 内容 |
|------|------|
| `PlatformCrawler/outputs/search/search_video_*.csv` | 搜到并选中的视频列表 |
| `PlatformCrawler/crawler/*评论*.csv` | 各视频原始评论 |
| `PlatformCrawler/outputs/D_platform_*.json` | **最终标准数据集**（给后续 Skill 用） |

---

## 想选「最热」的视频时

```powershell
# 按播放量 Top3（推荐）
python -m PlatformCrawler.pipeline 期末周破防 --since 2021-12-01 --until 2021-12-21 --max-videos 3 --order click --rank-by play

# 按评论数 Top3
python -m PlatformCrawler.pipeline 期末周破防 --since 2021-12-01 --until 2021-12-21 --max-videos 3 --rank-by review

# 候选再多一点（多翻一页搜索）
python -m PlatformCrawler.pipeline 期末周破防 --since 2021-12-01 --until 2021-12-21 --max-videos 3 --search-pages 2 --rank-by play
```

| `--rank-by` | 本地怎么挑 Top-N |
|-------------|------------------|
| `play` | 播放量最高（默认） |
| `review` | 评论数最高 |
| `favorites` | 收藏最多 |
| `search` | 不重排，跟搜索接口顺序走 |

只要「最新发布」、不看热度：

```powershell
... --order pubdate --rank-by search
```

---

## 已有评论 CSV，只想清洗建库

不爬网，直接用本地 CSV：

```powershell
python -m PlatformCrawler.pipeline --from-csv "PlatformCrawler\crawler\某某_评论_BVxxx.csv" --keyword 舞剧红楼梦 --since 2026-07-01 --until 2026-08-14 --out PlatformCrawler\outputs\out.json
```

或：

```powershell
python -m PlatformCrawler.dataloader.cli --csv a.csv b.csv --keyword 话题 --since 2026-07-01 --until 2026-08-14 --out PlatformCrawler\outputs\out.json
```

---

## 拆开用（可选）

```powershell
cd PlatformCrawler\crawler

# 只搜索
python B站关键词搜索.py 科比 --pages 1 --max-videos 10 --order click

# 只抓某个视频评论（可带评论时间窗；latest 越过 since 会早停）
python B站评论爬虫.py BV1xxxxxxxx --pages 2 --mode latest --since 2026-07-01 --until 2026-08-14

# 历史评论窗：页数要加大，否则翻不到 since
python B站评论爬虫.py BV1xxxxxxxx --pages 50 --mode latest --since 2020-01-01 --until 2020-05-31
```

---

## 目录说明（看哪里改什么）

```text
PlatformCrawler/
├── README.md                 ← 你正在看的说明
├── pipeline.py               ← 一键流水线入口
├── crawler/                  ← 登录、搜索、爬评论
│   ├── auto_get_cookie.py
│   ├── B站关键词搜索.py
│   └── B站评论爬虫.py
├── dataloader/               ← 清洗 + 按规范做数据集
│   ├── cleaner.py            ← 清洗规则 C1–C8
│   ├── builder.py            ← 组装 D_platform
│   └── validate.py           ← 规范校验
└── outputs/                  ← 搜索结果与最终 JSON
```

---

## 输出长什么样？（一眼看懂）

打开 `D_platform_*.json`：

- **`D_meta`**：这次任务的关键词、时间、有多少条评论、空了多少天、整体立场等  
- **`D_text`**：清洗后的每条评论（文本、时间、点赞、临时情绪标签……）  
- **`D_ts`**：按天（或小时）汇总的声量、热度、情绪均值、争议度；某天没数据也会留空桶，时间轴不断

字段细节见：[`DATASET_SPEC.md`](../DATASET_SPEC.md)

---

## 常见问题

**1. 提示找不到模块 / import 失败**  
请在 `pytorch` 根目录运行 `python -m PlatformCrawler...`，不要只在子文件夹里乱跑。

**2. 搜索成功、评论也爬了，但 JSON 里 `D_text` 是空的**  
多半是**页数不够**：`--comment-mode latest` 从最新往旧翻，若 `--comment-pages` 太小，还没翻进 `--since/--until` 就停了。  
流水线会把同一时间窗传给评论爬虫（窗外不写入 CSV）；清洗 C6 仍会再裁一次。  
看 `D_meta.n_text_raw_in` 与 `ext.n_out_of_range`；爬虫日志里的「时间窗统计 / 早停」也有用。

**3. 参数黏在一起报错**  
错误示例：`--until 2026-08-14--max-videos 3`  
正确：`--until 2026-08-14 --max-videos 3`（中间有空格）

**4. 被限流、很慢**  
先把 `--max-videos`、`--comment-pages` 调小；不要一次抓太多。

**5. 立场/情绪准不准？**  
目前是内置的**轻量规则**（占位），正式「平台立场画像 Skill」接上后会替换。`D_meta.ext.stance_provisional=true` 表示还是临时标签。

---

## 已知限制 / 隐藏坑（指令写对也可能踩）

| 问题 | 说明 |
|------|------|
| 时间窗双重含义 | `--since/--until`：**视频发布时间**（搜索）+ **评论发言时间**（爬取过滤 + 清洗 C6） |
| 历史窗依赖翻页配额 | 评论接口无按日随机访问；`latest` 从新往旧翻，越过 `since` 早停。历史区间须加大 `--comment-pages`，仍可能因限流/评论过多而拿不全 |
| `hot` 模式无时间早停 | 热门排序不按时间，只会跳过窗外评论，不会因 `since` 停翻 |
| 标题前缀撞名 | 评论文件名用标题前 10 字，极端情况下两视频可能互相覆盖（现已按 `*_BVxxx.csv` 收集，仍建议留意） |
| 空结果仍退出码 0 | 规范允许空时间轴；对「抓到又裁光」仍有严重告警 |
| Cookie / 限流 | 失败时可能无评论 CSV；现已检查子进程退出码并拒绝「零 CSV 继续装成功」 |

---

## 和整条 Agent 的关系

本目录 = 设计文档里的 **Skill1 PlatformCrawler（采集 + 清洗）**。  
它负责把网上的讨论变成干净、可对齐的 `D_platform`；不负责写最终舆情结论（那是后面的分析 / LLM Skill）。
