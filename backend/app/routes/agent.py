"""多 Agent 分析路由：跨平台多 Agent 分析任务的创建与查询"""
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity

from app import db
from app.constants import PLATFORMS
from app.models.agent_report import AgentReport
from app.services.agent_engine import is_available
from app.services.agent_service import AgentService

agent_bp = Blueprint('agent', __name__)


@agent_bp.route('/status', methods=['GET'])
@jwt_required()
def get_engine_status():
    """多 Agent 引擎可用性探测"""
    return jsonify(code=200, message='获取成功', data={
        'available': is_available(),
        'platforms': [{'value': k, 'label': v['name']} for k, v in PLATFORMS.items()],
    })


@agent_bp.route('/analyze', methods=['POST'])
@jwt_required()
def create_analysis():
    """创建跨平台多 Agent 分析任务（后台执行）"""
    if not is_available():
        return jsonify(code=503, message='多 Agent 引擎未部署（缺少 agent/multiagent 代码目录）'), 503

    data = request.get_json() or {}
    user_id = get_jwt_identity()

    keyword = (data.get('keyword') or '').strip()
    if not keyword:
        return jsonify(code=400, message='关键词不能为空'), 400

    platforms = data.get('platforms') or []
    invalid = [p for p in platforms if p not in PLATFORMS]
    if invalid:
        return jsonify(code=400, message=f'不支持的平台: {invalid}'), 400

    report = AgentReport(
        task_id=data.get('task_id'),
        user_id=user_id,
        keyword=keyword,
        platforms=','.join(platforms) if platforms else '',
        status='pending',
    )
    db.session.add(report)
    db.session.commit()

    AgentService.run_in_background(current_app._get_current_object(), report.id)

    return jsonify(code=200, message='分析任务已创建，正在后台执行', data=report.to_dict())


@agent_bp.route('/reports', methods=['GET'])
@jwt_required()
def get_reports():
    """获取分析报告列表"""
    user_id = get_jwt_identity()
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 10, type=int)

    pagination = AgentReport.query.filter_by(user_id=user_id) \
        .order_by(AgentReport.created_at.desc()) \
        .paginate(page=page, per_page=page_size, error_out=False)

    return jsonify(code=200, message='获取成功', data={
        'reports': [r.to_dict() for r in pagination.items],
        'total': pagination.total,
        'page': page,
        'page_size': page_size,
    })


@agent_bp.route('/reports/<int:report_id>', methods=['GET'])
@jwt_required()
def get_report(report_id):
    """获取单个分析报告详情（含完整结果）"""
    user_id = get_jwt_identity()
    report = AgentReport.query.filter_by(id=report_id, user_id=user_id).first()
    if not report:
        return jsonify(code=404, message='报告不存在'), 404

    return jsonify(code=200, message='获取成功', data=report.to_dict(include_result=True))
