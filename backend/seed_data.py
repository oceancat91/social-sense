"""部署后种子数据脚本：在 Docker 容器内运行，灌入跨平台演示舆情数据"""
import sys

sys.path.insert(0, '.')
from app import create_app, db
from app.models.user import User
from app.models.task import MonitorTask
from app.services.pipeline_service import PipelineService

app = create_app()
with app.app_context():
    user = User.query.filter_by(username='admin').first()
    if not user:
        print('错误: 管理员账户不存在')
        sys.exit(1)

    task = MonitorTask.query.filter_by(
        user_id=user.id, keywords='校园食品安全'
    ).first()
    if not task:
        task = MonitorTask(
            user_id=user.id,
            keywords='校园食品安全',
            platform='all',
            status='collecting'
        )
        db.session.add(task)
        db.session.commit()

    PipelineService.run_task_pipeline(app, task.id, days=14, limit=600)
    db.session.expire_all()
    task = db.session.get(MonitorTask, task.id)
    print(f'演示数据已生成: {task.data_count} 条')
    print(f'覆盖平台: 抖音/微博/小红书/B站/知乎/快手')
