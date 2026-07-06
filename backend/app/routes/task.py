"""监控任务路由"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models.task import MonitorTask

task_bp = Blueprint('task', __name__)


@task_bp.route('', methods=['POST'])
@jwt_required()
def create_task():
    """创建监控任务"""
    data = request.get_json()
    user_id = get_jwt_identity()

    task = MonitorTask(
        user_id=user_id,
        keywords=','.join(data.get('keywords', [])),
        platform=data.get('platform', 'weibo')
    )
    db.session.add(task)
    db.session.commit()

    return jsonify(code=200, message='任务创建成功', data=task.to_dict())


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


@task_bp.route('/<int:task_id>', methods=['DELETE'])
@jwt_required()
def delete_task(task_id):
    """删除监控任务"""
    user_id = get_jwt_identity()
    task = MonitorTask.query.filter_by(id=task_id, user_id=user_id).first()

    if not task:
        return jsonify(code=404, message='任务不存在'), 404

    db.session.delete(task)
    db.session.commit()

    return jsonify(code=200, message='删除成功')
