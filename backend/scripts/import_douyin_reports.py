"""
把抖音 broad 平台报告融入 real_multiplatform fusion 后，同步数据库：
对每条 broad fusion（fusion/{domain}__broad.json，现含 douyin 平台），
删除旧的 bilibili+weibo 记录，插入含 douyin 的新 AgentReport。

hot fusion 不涉及（抖音 CSV 无 hot 粒度），保持不变。

用法（在仓库根）：
    python backend/scripts/import_douyin_reports.py
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

FUSION = REPO / "agent" / "dataset" / "real_multiplatform" / "fusion"
REPORTS = REPO / "agent" / "dataset" / "real_multiplatform" / "reports"


def main() -> None:
    app = create_app()
    with app.app_context():
        user = User.query.order_by(User.id.asc()).first()
        if not user:
            print("数据库无用户，请先启动后端创建 admin 账户")
            return
        uid = user.id

        created = 0
        removed = 0
        for f in sorted(FUSION.glob("*.json")):
            if f.name == "index.json":
                continue
            stem = f.stem
            if not stem.endswith("__broad"):
                continue  # 只更新 broad fusion
            with open(f, encoding="utf-8") as fh:
                fusion = json.load(fh)
            platforms_key = ",".join(fusion.get("platforms") or [])
            if "douyin" not in platforms_key:
                continue  # 该域 fusion 尚未包含 douyin
            keyword = (fusion.get("keyword") or "").strip() or stem.split("__")[0]

            # 收集该 (domain) 各平台报告
            reports = []
            for pdir in sorted(REPORTS.iterdir()):
                if not pdir.is_dir():
                    continue
                rp = pdir / f"{stem}.json"
                if rp.exists():
                    with open(rp, encoding="utf-8") as rh:
                        reports.append(json.load(rh))

            # 删除同 keyword 的旧 broad 记录（不含 douyin 或此前遗留）
            old = AgentReport.query.filter(
                AgentReport.user_id == uid,
                AgentReport.keyword == keyword,
            ).all()
            for rep in old:
                plats = [p for p in (rep.platforms or "").split(",") if p]
                if "xiaohongshu" in plats:
                    continue  # hot 记录保留
                if set(plats) == {"bilibili", "weibo", "douyin"}:
                    continue  # 已是最新，无需删
                db.session.delete(rep)
                removed += 1
                print(f"[del] {keyword} <- {rep.platforms}")

            # 幂等：存在含 douyin 的新记录则跳过
            dup = AgentReport.query.filter_by(
                user_id=uid, keyword=keyword, platforms=platforms_key
            ).first()
            if dup:
                print(f"[skip] {keyword}（{platforms_key}）已存在 id={dup.id}")
                continue

            result = {
                "platform_reports": reports,
                "cross_platform": fusion,
                "generated_at": datetime.now().isoformat(timespec="seconds"),
            }
            status = "success" if fusion.get("CT_status") == "accepted" else "partial"
            rep = AgentReport(
                user_id=uid,
                keyword=keyword,
                platforms=platforms_key,
                status=status,
                result=json.dumps(result, ensure_ascii=False),
            )
            db.session.add(rep)
            created += 1
            print(
                f"[+] {keyword}（{platforms_key}，{len(reports)} 平台，"
                f"CT={fusion.get('CT_status')}）"
            )

        db.session.commit()
        print(f"\n导入完成：新增 {created} 条，删除旧记录 {removed} 条")


if __name__ == "__main__":
    main()
