"""数据采集命令行脚本：采集 → 清洗 → 情感分析 → 入库"""
import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from app import create_app
from app.models.task import MonitorTask
from app.models.user import User
from app.services.crawler_service import SUPPORTED_PLATFORMS
from app.services.pipeline_service import PipelineService


def main():
    parser = argparse.ArgumentParser(description='Social Sense 数据采集脚本')
    parser.add_argument('--keyword', required=True, help='监控关键词（事件主题）')
    parser.add_argument('--platform', default='all',
                        choices=['all'] + SUPPORTED_PLATFORMS, help='目标平台')
    parser.add_argument('--days', type=int, default=14, help='事件回溯天数')
    parser.add_argument('--limit', type=int, default=600, help='采集数据量上限')
    parser.add_argument('--user', default='admin', help='任务归属用户名')
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        user = User.query.filter_by(username=args.user).first()
        if not user:
            print(f'用户 {args.user} 不存在，请先运行 init_db.py 初始化')
            sys.exit(1)

        task = MonitorTask.query.filter_by(
            user_id=user.id, keywords=args.keyword, platform=args.platform
        ).first()
        if not task:
            task = MonitorTask(
                user_id=user.id, keywords=args.keyword,
                platform=args.platform, status='collecting',
            )
            from app import db
            db.session.add(task)
            db.session.commit()
            print(f'已创建任务 #{task.id}: {args.keyword} @ {args.platform}')

    print(f'开始采集: keyword={args.keyword} platform={args.platform} '
          f'days={args.days} limit={args.limit}')
    PipelineService.run_task_pipeline(app, task.id, days=args.days, limit=args.limit)

    with app.app_context():
        from app import db
        task = db.session.get(MonitorTask, task.id)
        print(f'完成！任务 #{task.id} 当前共 {task.data_count} 条数据')


if __name__ == '__main__':
    main()
