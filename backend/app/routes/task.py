"""监控任务路由"""
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.constants import PLATFORMS
from app.models.task import MonitorTask
from app.services.crawler_service import SUPPORTED_PLATFORMS
from app.services.pipeline_service import PipelineService

task_bp = Blueprint('task', __name__)


@task_bp.route('/platforms', methods=['GET'])
@jwt_required()
def get_platforms():
    """获取支持的平台列表"""
    return jsonify(code=200, message='获取成功', data={
        'platforms': [
            {'value': code, 'label': info['name'], 'color': info['color']}
            for code, info in PLATFORMS.items()
        ]
    })


@task_bp.route('', methods=['POST'])
@jwt_required()
def create_task():
    """创建监控任务，默认自动触发首轮数据采集"""
    data = request.get_json()
    user_id = get_jwt_identity()

    platform = data.get('platform', 'all')
    if platform != 'all' and platform not in SUPPORTED_PLATFORMS:
        return jsonify(code=400, message=f'不支持的平台: {platform}'), 400

    keywords = data.get('keywords', [])
    if not keywords:
        return jsonify(code=400, message='关键词不能为空'), 400

    task = MonitorTask(
        user_id=user_id,
        keywords=','.join(keywords),
        platform=platform,
        status='collecting',
    )
    db.session.add(task)
    db.session.commit()

    if data.get('auto_collect', True):
        PipelineService.run_in_background(
            current_app._get_current_object(), task.id,
            days=data.get('days', 14),
        )
    else:
        task.status = 'active'
        db.session.commit()

    return jsonify(code=200, message='任务创建成功，正在采集数据', data=task.to_dict())


@task_bp.route('', methods=['GET'])
@jwt_required()
def get_tasks():
    """获取任务列表"""
    user_id = get_jwt_identity()
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 10, type=int)

    pagination = MonitorTask.query.filter_by(user_id=user_id) \
        .order_by(MonitorTask.created_at.desc()) \
        .paginate(page=page, per_page=page_size, error_out=False)

    return jsonify(code=200, message='获取成功', data={
        'tasks': [t.to_dict() for t in pagination.items],
        'total': pagination.total,
        'page': page,
        'page_size': page_size
    })


@task_bp.route('/<int:task_id>/collect', methods=['POST'])
@jwt_required()
def collect_task(task_id):
    """手动触发任务数据采集（后台执行）"""
    user_id = get_jwt_identity()
    task = MonitorTask.query.filter_by(id=task_id, user_id=user_id).first()
    if not task:
        return jsonify(code=404, message='任务不存在'), 404
    if task.status == 'collecting':
        return jsonify(code=409, message='任务正在采集中，请稍候'), 409

    data = request.get_json(silent=True) or {}
    PipelineService.run_in_background(
        current_app._get_current_object(), task.id, days=data.get('days', 14)
    )
    return jsonify(code=200, message='采集已启动', data={'task_id': task_id})


@task_bp.route('/<int:task_id>', methods=['DELETE'])
@jwt_required()
def delete_task(task_id):
    """删除监控任务及其关联数据"""
    user_id = get_jwt_identity()
    task = MonitorTask.query.filter_by(id=task_id, user_id=user_id).first()

    if not task:
        return jsonify(code=404, message='任务不存在'), 404

    from app.models.sentiment import SentimentData
    SentimentData.query.filter_by(task_id=task_id).delete()
    db.session.delete(task)
    db.session.commit()

    return jsonify(code=200, message='删除成功')
