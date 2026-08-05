"""演示数据初始化脚本：创建演示任务并灌入多平台模拟舆情数据"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from app import create_app, db
from app.models.task import MonitorTask
from app.models.user import User
from app.services.pipeline_service import PipelineService

DEMO_EVENTS = [
    {'keyword': '校园食品安全', 'platform': 'all', 'days': 14, 'limit': 600},
]


def seed():
    app = create_app()
    with app.app_context():
        db.create_all()

        user = User.query.filter_by(username='admin').first()
        if not user:
            print('请先运行 scripts/init_db.py 创建管理员账户')
            sys.exit(1)

        for event in DEMO_EVENTS:
            task = MonitorTask.query.filter_by(
                user_id=user.id, keywords=event['keyword']
            ).first()
            if task:
                print(f"任务已存在，跳过: {event['keyword']} (#{task.id})")
                continue

            task = MonitorTask(
                user_id=user.id,
                keywords=event['keyword'],
                platform=event['platform'],
                status='collecting',
            )
            db.session.add(task)
            db.session.commit()
            print(f"创建演示任务 #{task.id}: {event['keyword']} @ {event['platform']}")

            PipelineService.run_task_pipeline(
                app, task.id, days=event['days'], limit=event['limit']
            )

            # 管道在独立会话中提交，需过期本地缓存以读取最新计数
            db.session.expire_all()
            task = db.session.get(MonitorTask, task.id)
            print(f"  -> 完成，共 {task.data_count} 条数据")

    print('\n演示数据初始化完成！')


if __name__ == '__main__':
    seed()
