"""多 Agent 分析路由：跨平台多 Agent 分析任务的创建与查询"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy.orm import defer

from app.constants import PLATFORMS
from app.models.agent_report import AgentReport
from app.services.agent_engine import is_available

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
    """创建跨平台多 Agent 分析任务（已停用：前端不再开放自定义搜索/分析）。"""
    return jsonify(code=403, message='自定义搜索分析功能已停用，当前仅支持查看历史分析报告'), 403


@agent_bp.route('/reports', methods=['GET'])
@jwt_required()
def get_reports():
    """获取分析报告列表"""
    user_id = get_jwt_identity()
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 10, type=int)

    # 列表只投影轻量字段：result 为 LONGTEXT（单条可达数 MB），
    # 若随列表一起 SELECT，每次请求都要搬运几十 MB，会打满低内存服务器导致偶发不可用。
    pagination = AgentReport.query.options(defer(AgentReport.result)) \
        .filter_by(user_id=user_id) \
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
