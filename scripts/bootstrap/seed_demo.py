"""演示数据初始化脚本：创建演示任务并灌入多平台模拟舆情数据。"""
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / 'backend'))

from app import create_app
from app.services.demo_seed_service import seed_demo_data


def seed():
    app = create_app()
    try:
        results = seed_demo_data(app)
    except RuntimeError as exc:
        raise SystemExit(f"错误：{exc}") from exc

    for result in results:
        action = "创建" if result.created else "跳过已有"
        print(
            f"{action}演示任务 #{result.task_id}: {result.keyword}"
            f"（{result.data_count} 条数据）"
        )
    print('\n演示数据初始化完成！')


if __name__ == '__main__':
    seed()
