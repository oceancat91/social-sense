"""
把 agent/dataset/real_multiplatform 下已离线算好的平台报告 + 融合结果，
重新生成（含对齐字段 aligned）后导入后端数据库 agent_reports 表，
让前端「多 Agent 分析」页面能直接展示历史真实数据。

用法（在仓库根或 backend 目录均可）：
    python backend/scripts/import_history_reports.py
"""
import json
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"
sys.path.insert(0, str(BACKEND))   # import app
sys.path.insert(0, str(REPO))      # import multiagent

from app import create_app, db  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.agent_report import AgentReport  # noqa: E402
from multiagent.master import run_master  # noqa: E402

DATA = REPO / "agent" / "dataset" / "real_multiplatform"
REPORTS = DATA / "reports"
FUSION = DATA / "fusion"


def main() -> None:
    app = create_app()
    with app.app_context():
        user = User.query.order_by(User.id.asc()).first()
        if not user:
            print("数据库无用户，请先启动后端创建 admin 账户")
            return
        uid = user.id

        created = 0
        skipped = 0
        for f in sorted(FUSION.glob("*.json")):
            if f.name == "index.json":
                continue
            stem = f.stem  # e.g. culture_history__hot
            with open(f, encoding="utf-8") as fh:
                fusion = json.load(fh)
            keyword = (fusion.get("keyword") or "").strip() or stem.split("__")[0]

            # 收集该 (topic, scope) 对应的各平台报告
            reports = []
            for pdir in sorted(REPORTS.iterdir()):
                if not pdir.is_dir():
                    continue
                rp = pdir / f"{stem}.json"
                if rp.exists():
                    with open(rp, encoding="utf-8") as rh:
                        reports.append(json.load(rh))
            if not reports:
                print(f"跳过 {stem}：无对应平台报告")
                continue

            platforms = [str(r.get("platform")) for r in reports]
            platforms_key = ",".join(platforms)

            # 幂等：同 (user, keyword, platforms) 不重复导入
            dup = AgentReport.query.filter_by(
                user_id=uid, keyword=keyword, platforms=platforms_key
            ).first()
            if dup:
                skipped += 1
                continue

            # 重新生成 CT（use_llm=False，含 aligned 对齐字段，纯计算）
            ct = run_master(reports, use_llm=False)
            result = {
                "platform_reports": reports,
                "cross_platform": ct,
                "generated_at": datetime.now().isoformat(timespec="seconds"),
            }
            status = "success" if ct.get("CT_status") == "accepted" else "partial"

            rep = AgentReport(
                user_id=uid,
                keyword=keyword,
                platforms=platforms_key,
                status=status,
                result=json.dumps(result, ensure_ascii=False),
            )
            db.session.add(rep)
            created += 1
            print(f"[+] {stem} -> {keyword}（{platforms_key}，{len(reports)} 平台，status={status}）")

        db.session.commit()
        print(f"\n导入完成：新增 {created} 条，跳过已存在 {skipped} 条")


if __name__ == "__main__":
    main()
