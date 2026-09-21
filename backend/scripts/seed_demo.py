"""部署后种子数据脚本：在 Docker 容器内灌入跨平台演示数据。"""
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app import create_app
from app.services.demo_seed_service import seed_demo_data


def main() -> None:
    app = create_app()
    try:
        results = seed_demo_data(app)
    except RuntimeError as exc:
        raise SystemExit(f"错误：{exc}") from exc

    for result in results:
        action = "已生成" if result.created else "已存在"
        print(
            f"演示任务 #{result.task_id} {action}: "
            f"{result.keyword}（{result.data_count} 条数据）"
        )
    print("覆盖平台: 抖音/微博/小红书/B站/知乎/快手")


if __name__ == "__main__":
    main()
