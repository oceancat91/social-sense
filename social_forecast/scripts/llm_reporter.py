"""LLM attribution report — pluggable backend (Ollama / OpenAI-compatible).

只依赖标准库 + requests，不需要任何 SDK、不写死任何厂商。

后端两种：
  - ollama : 本地免费，POST {base_url}/api/generate（无 key）
  - openai  : OpenAI 兼容协议，POST {base_url}/chat/completions
              任何 OpenAI 协议服务都能接：LM Studio / vLLM / llama.cpp server
              / DeepSeek / Qwen(通义) / Kimi(Moonshot) / GLM / OpenAI 官方 …

配置优先级（后者覆盖前者）：
  1. 内置默认（ollama, qwen2.5:0.5b）
  2. 配置文件（默认读 social_forecast/llm_config.json）
  3. .env（DEEPSEEK_API_KEY / LLM_API_KEY）
  4. 命令行参数 --backend --base-url --model --api-key

用法：
  python scripts/llm_reporter.py                       # 用 llm_config.json + .env
  python scripts/llm_reporter.py --template            # 不用 LLM，输出模板
  python scripts/llm_reporter.py --config llm_config.json --top 10

输入 : data/social/anomalies.csv  (来自 anomaly_detect.py)
输出 : data/social/report.md
未接 LLM 时回退模板报告，永不崩溃。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

ROOT = Path(__file__).resolve().parents[1]
ANOMALIES = ROOT / "data" / "social" / "anomalies.csv"
OUT_MD = ROOT / "data" / "social" / "report.md"
DEFAULT_CONFIG = ROOT / "llm_config.json"
ENV_FILE = ROOT / ".env"


def load_dotenv(path: Path = ENV_FILE) -> None:
    """把 .env 里的 KEY=VALUE 写入 os.environ（不覆盖已有环境变量）。"""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v
ENV_FILE = ROOT / ".env"


def load_dotenv(path: Path = ENV_FILE) -> None:
    """把 social_forecast/.env 载入 os.environ（不覆盖已有环境变量）。

    格式：KEY=VALUE，支持 # 注释与空行。不依赖 python-dotenv。
    """
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v

# 常见 OpenAI 兼容 base_url 速查（写进 llm_config.json 即可，无需改代码）
BACKEND_HINTS = {
    "ollama": "http://127.0.0.1:11434",
    "lmstudio": "http://localhost:1234/v1",
    "vllm": "http://localhost:8000/v1",
    "llamacpp": "http://localhost:8080/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "kimi": "https://api.moonshot.cn/v1",
    "glm": "https://open.bigmodel.cn/api/paas/v4",
    "openai": "https://api.openai.com/v1",
}


# ---------------------------------------------------------------------------
# Prompt（结构化事件 + 预测 → 融合归因报告）
# ---------------------------------------------------------------------------
def build_prompt(events: list[dict], forecast_brief: dict | None = None) -> str:
    brief = []
    for e in events:
        brief.append(
            {
                "date": e["date"],
                "z_score": round(float(e["z_max"]), 2),
                "trigger": e["trigger_metric"],
                "anomaly_type": str(e.get("anomaly_source", "")),
                "OT": int(e["OT"]),
                "likes": int(e["like_sum"]),
                "views": int(e["view_sum"]),
                "platforms": {k: int(e[k]) for k in
                              ("bilibili", "douyin", "kuaishou", "weibo", "xhs")
                              if k in e and int(e[k]) > 0},
                "top_text": str(e["fact"])[:120],
            }
        )

    lines = [
        "你是社交媒体热度分析助手。下面是两类信息，请融合成一份完整的"
        "「异常归因 + 前瞻预测」报告：",
        "1) 一段时间内检测到的热度异常事件（按稳健 z 分数排序，z 越大越异常；"
        "anomaly_type 为 spike=单日尖峰、regime=持续水平跃迁）；",
    ]
    if forecast_brief:
        narr = forecast_brief.get("forecast") or {}
        wins = forecast_brief.get("window_briefs") or []
        lines.append(
            "2) 数值模型（ŷ = T̂+Ŝ+Ĉ+R̂）对未来多个窗口的预测：方向（up/down）"
            "与尖峰预警（spike_warning，基于排名口径阈值）。"
        )
        lines.append(
            f"   预测概况：上涨={narr.get('n_up', 0)} 回落={narr.get('n_down', 0)} "
            f"尖峰预警={narr.get('n_spike', 0)}。窗口明细："
        )
        lines.append(json.dumps(wins, ensure_ascii=False))
    lines += [
        "",
        "请用简洁中文写一份报告，包含：",
        "1) 总体概况（异常事件数量、时间跨度、主要平台）；",
        "2) 逐个重点事件：日期、触发指标、异常类型、可能的主题/成因"
        "（依据 top_text 推断）；",
        "3) 未来热度走向：结合预测的方向与尖峰预警，给出短期判断；",
        "4) 三条给运营的建议（结合异常成因与预测方向）。",
        "",
        "不要编造数据，只基于给定字段推断。事件列表(JSON)：",
        json.dumps(brief, ensure_ascii=False, indent=2),
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 后端调用
# ---------------------------------------------------------------------------
def call_ollama(model: str, prompt: str, base_url: str, timeout: int = 600) -> str:
    url = base_url.rstrip("/") + "/api/generate"
    r = requests.post(url, json={"model": model, "prompt": prompt, "stream": False},
                      timeout=timeout)
    r.raise_for_status()
    return r.json()["response"]


def call_openai_compat(model: str, prompt: str, base_url: str,
                       api_key: str = "", timeout: int = 600) -> str:
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "stream": False,
    }
    r = requests.post(url, json=payload, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def call_llm(backend: str, model: str, prompt: str,
             base_url: str, api_key: str = "") -> str:
    if requests is None:
        raise RuntimeError("requests 未安装：pip install requests")
    if backend == "ollama":
        return call_ollama(model, prompt, base_url)
    if backend == "openai":
        return call_openai_compat(model, prompt, base_url, api_key)
    raise ValueError(f"未知 backend={backend}，可选 ollama / openai")


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
def load_config(cfg_path: Path | None) -> dict:
    cfg = {"backend": "ollama",
           "base_url": "http://127.0.0.1:11434",
           "model": "qwen2.5:0.5b",
           "api_key": ""}

    path = cfg_path if cfg_path is not None else DEFAULT_CONFIG
    if path is not None and Path(path).exists():
        with open(path, encoding="utf-8") as f:
            user = json.load(f)
        cfg.update({k: v for k, v in user.items() if v not in ("", None)})
    return cfg


def resolve(cfg: dict, args) -> dict:
    """命令行覆盖配置文件；支持 --backend 用速查名；key 从 .env / 环境变量补。"""
    load_dotenv()
    if args.backend:
        cfg["backend"] = ("openai" if args.backend in BACKEND_HINTS
                          and args.backend != "ollama" else args.backend)
        if args.backend in BACKEND_HINTS and args.backend != "ollama":
            cfg["base_url"] = BACKEND_HINTS[args.backend]
            if args.backend == "deepseek" and not args.model:
                cfg["model"] = cfg.get("model") or "deepseek-chat"
    if args.base_url:
        cfg["base_url"] = args.base_url
    if args.model:
        cfg["model"] = args.model
    if args.api_key:
        cfg["api_key"] = args.api_key
    # 环境变量 / .env 补充（DeepSeek 优先读 DEEPSEEK_API_KEY）
    if not cfg.get("api_key"):
        cfg["api_key"] = (
            os.environ.get("LLM_API_KEY")
            or os.environ.get("DEEPSEEK_API_KEY")
            or ""
        )
    # base_url 指向 deepseek 且未填 key → 再试一次专用变量
    if (not cfg.get("api_key")
            and "deepseek" in str(cfg.get("base_url", "")).lower()):
        cfg["api_key"] = os.environ.get("DEEPSEEK_API_KEY", "")
    return cfg


# ---------------------------------------------------------------------------
# 报告
# ---------------------------------------------------------------------------
def template_report(events: list[dict]) -> str:
    lines = ["# 社交热度异常事件报告（模板版，未接入 LLM）", ""]
    lines.append(f"检测到 {len(events)} 个异常日。")
    lines.append("")
    for e in events:
        plats = ", ".join(
            f"{k}={int(e[k])}" for k in
            ("bilibili", "douyin", "kuaishou", "weibo", "xhs")
            if k in e and int(e[k]) > 0
        )
        fact = str(e.get("fact", ""))[:100].replace("\n", " ")
        atype = str(e.get("anomaly_source", "") or "")
        atype_label = {"spike": "尖峰", "regime": "跃迁", "both": "尖峰+跃迁"}.get(atype, "")
        lines.append(
            f"- **{e['date']}**  z={float(e['z_max']):.1f}  触发={e['trigger_metric']}"
            f"{(' [' + atype_label + ']') if atype_label else ''}  "
            f"OT={int(e['OT'])}  likes={int(e['like_sum']):,}  views={int(e['view_sum']):,}"
        )
        if plats:
            lines.append(f"   平台: {plats}")
        if fact:
            lines.append(f"   文本: {fact}")
        lines.append("")
    lines.append(
        "> 提示：在 `llm_config.json` 配置你的 LLM（本地 Ollama 或任意 OpenAI 兼容服务）"
        "后重跑本脚本，即可得到自然语言报告。"
    )
    return "\n".join(lines)


def load_top_events(top_n: int) -> list[dict]:
    import pandas as pd

    df = pd.read_csv(ANOMALIES)
    anoms = df[df["is_anomaly"]].sort_values("z_max", ascending=False)
    anoms = anoms.head(top_n)
    for p in ("bilibili", "douyin", "kuaishou", "weibo", "xhs"):
        if p not in anoms.columns:
            anoms[p] = 0
    if "anomaly_source" not in anoms.columns:
        anoms["anomaly_source"] = anoms["trigger_metric"].map(
            lambda t: "regime" if str(t) == "regime" else "spike")
    return anoms.to_dict("records")


def load_forecast_brief() -> dict | None:
    """读 workflow 产出的 llm_forecast_brief.json（预测方向/尖峰预警）。"""
    for p in (
        ROOT / "results" / "workflow" / "llm_forecast_brief.json",
        ROOT / "data" / "social" / "llm_forecast_brief.json",
    ):
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception as e:  # noqa: BLE001
                print(f"[llm] 读 forecast brief 失败: {e}")
    return None


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, default=None,
                    help="JSON 配置文件路径（默认读 llm_config.json）")
    ap.add_argument("--backend", default=None,
                    help="ollama / openai，或速查名 deepseek/qwen/kimi/glm/lmstudio/vllm/llamacpp/openai")
    ap.add_argument("--base-url", default=None, help="服务地址")
    ap.add_argument("--model", default=None, help="模型名")
    ap.add_argument("--api-key", default=None, help="API key（也可用环境变量 LLM_API_KEY）")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--template", action="store_true", help="强制模板输出，不调 LLM")
    args = ap.parse_args()

    events = load_top_events(args.top)
    print(f"[llm] loaded {len(events)} events from {ANOMALIES}")

    forecast_brief = load_forecast_brief()
    if forecast_brief:
        n_wins = len(forecast_brief.get("window_briefs") or [])
        print(f"[llm] loaded forecast brief ({n_wins} windows)")

    cfg = resolve(load_config(args.config), args)
    print(f"[llm] backend={cfg['backend']} model={cfg['model']} base_url={cfg['base_url']}")

    report = None
    if not args.template:
        try:
            prompt = build_prompt(events, forecast_brief)
            print("[llm] calling model ...")
            text = call_llm(cfg["backend"], cfg["model"], prompt,
                            cfg["base_url"], cfg.get("api_key", ""))
            report = (f"# 社交热度异常事件报告\n\n"
                      f"> 生成模型：`{cfg['model']}`（backend={cfg['backend']}）\n\n{text}")
            print("[llm] responded.")
        except Exception as e:  # noqa: BLE001
            print(f"[llm] 调用失败，退回模板报告: {e}")

    if report is None:
        report = template_report(events)

    OUT_MD.write_text(report, encoding="utf-8")
    print(f"[llm] wrote {OUT_MD}")
    print("\n----- 报告预览 -----")
    print(report[:1200])


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
