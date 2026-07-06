"""数据分析路由"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models.sentiment import SentimentData
from app.models.task import MonitorTask

analysis_bp = Blueprint('analysis', __name__)


@analysis_bp.route('/overview', methods=['GET'])
@jwt_required()
def get_overview():
    """获取舆情概览"""
    user_id = get_jwt_identity()

    task_ids = [t.id for t in MonitorTask.query.filter_by(user_id=user_id).all()]

    total = SentimentData.query.filter(SentimentData.task_id.in_(task_ids)).count()
    positive = SentimentData.query.filter(
        SentimentData.task_id.in_(task_ids),
        SentimentData.sentiment == 'positive'
    ).count()
    negative = SentimentData.query.filter(
        SentimentData.task_id.in_(task_ids),
        SentimentData.sentiment == 'negative'
    ).count()
    neutral = total - positive - negative

    return jsonify(code=200, message='获取成功', data={
        'total': total,
        'positive': positive,
        'negative': negative,
        'neutral': neutral
    })


@analysis_bp.route('/sentiment', methods=['GET'])
@jwt_required()
def get_sentiment():
    """获取情感分析结果"""
    task_id = request.args.get('task_id', type=int)
    if not task_id:
        return jsonify(code=400, message='缺少 task_id 参数'), 400

    data_list = SentimentData.query.filter_by(task_id=task_id) \
        .order_by(SentimentData.collected_at.desc()) \
        .limit(100).all()

    return jsonify(code=200, message='获取成功', data={
        'items': [d.to_dict() for d in data_list]
    })


@analysis_bp.route('/trending', methods=['GET'])
@jwt_required()
def get_trending():
    """获取热点话题（占位接口）"""
    return jsonify(code=200, message='获取成功', data={
        'topics': []
    })
