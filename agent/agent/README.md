# 单平台舆情 Agent（Skill1 + Skill2）

## 分工

| 谁 | 负责什么 |
|----|----------|
| **你（人工）** | 只输入**话题** |
| **LLM（DeepSeek）** | 定位事件爆发日，规划 **爆发→至今** 分析窗、热度搜索池与评论配额 |
| **Agent** | 依次调用 PlatformCrawler → StanceProfiler，并核验 |

## 用法

先 `Ctrl+C` 停掉旧的交互进程，再在 `pytorch` 根目录：

```powershell
python -m Agent --topic 科比去世
```

或：

```powershell
python -m Agent
# 只问话题，不再问日期
```

需要 `.env` 中有 `DEEPSEEK_API_KEY`。可选 `DEEPSEEK_MODEL=deepseek-chat`。

## 规划策略

| 用途 | 参数 | 规则 |
|------|------|------|
| **时序热度长轴** | `since`/`until` | 爆发日 → 今天 → 写入 `D_ts.topic_heat` |
| **评论文本** | `comment_since`/`comment_until` + `comment_pages` | **固定 2 页**，只用近期窗抽样 |

不要用深翻评论去填长轴；长轴靠搜索视频的发布日热度。

## 时序里有哪些「热度」

| 字段 | 含义 |
|------|------|
| `volume` / `heat` | **评论侧**：近期 2 页抽样评论的条数与 \(\sum interact\) |
| `topic_volume` / `topic_heat` | **内容侧**：相关视频按 `pubdate` 入桶（爆发→至今主轴） |
