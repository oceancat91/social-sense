"""数据分析路由：跨平台多维舆情分析"""
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func

from app import db
from app.constants import PLATFORMS
from app.models.sentiment import SentimentData
from app.models.task import MonitorTask

analysis_bp = Blueprint('analysis', __name__)


def _base_query(user_id):
    """构造当前用户数据范围查询，支持 task_id / platform / days 过滤"""
    task_ids = [t.id for t in MonitorTask.query.filter_by(user_id=user_id).all()]
    query = SentimentData.query.filter(SentimentData.task_id.in_(task_ids or [-1]))

    task_id = request.args.get('task_id', type=int)
    if task_id:
        query = query.filter(SentimentData.task_id == task_id)

    platform = request.args.get('platform')
    if platform and platform != 'all':
        query = query.filter(SentimentData.platform == platform)

    days = request.args.get('days', type=int)
    if days:
        since = datetime.now() - timedelta(days=days)
        query = query.filter(SentimentData.published_at >= since)

    return query


def _sentiment_counts(query):
    """按情感标签统计数量"""
    rows = query.with_entities(SentimentData.sentiment, func.count()) \
        .group_by(SentimentData.sentiment).all()
    counts = {'positive': 0, 'neutral': 0, 'negative': 0}
    for sentiment, count in rows:
        if sentiment in counts:
            counts[sentiment] = count
    return counts


@analysis_bp.route('/overview', methods=['GET'])
@jwt_required()
def get_overview():
    """舆情总览：总量、情感分布、覆盖平台"""
    user_id = get_jwt_identity()
    query = _base_query(user_id)

    counts = _sentiment_counts(query)
    total = sum(counts.values())

    platform_rows = query.with_entities(SentimentData.platform, func.count()) \
        .group_by(SentimentData.platform).all()
    platforms = [
        {'platform': p, 'platform_name': PLATFORMS.get(p, {}).get('name', p), 'count': c}
        for p, c in sorted(platform_rows, key=lambda x: x[1], reverse=True)
    ]

    avg_score = query.with_entities(func.avg(SentimentData.score)).scalar() or 0

    return jsonify(code=200, message='获取成功', data={
        'total': total,
        **counts,
        'negative_ratio': round(counts['negative'] / total, 4) if total else 0,
        'avg_score': round(float(avg_score), 4),
        'platform_count': len(platforms),
        'platforms': platforms,
    })


@analysis_bp.route('/platform-comparison', methods=['GET'])
@jwt_required()
def get_platform_comparison():
    """跨平台对比：各平台情感分布、平均情感分、互动总量"""
    user_id = get_jwt_identity()
    query = _base_query(user_id)

    rows = query.with_entities(
        SentimentData.platform,
        SentimentData.sentiment,
        func.count().label('cnt'),
        func.avg(SentimentData.score).label('avg_score'),
        func.sum(SentimentData.like_count).label('likes'),
        func.sum(SentimentData.comment_count).label('comments'),
        func.sum(SentimentData.share_count).label('shares'),
    ).group_by(SentimentData.platform, SentimentData.sentiment).all()

    stats = defaultdict(lambda: {
        'total': 0, 'positive': 0, 'neutral': 0, 'negative': 0,
        'score_sum': 0.0, 'likes': 0, 'comments': 0, 'shares': 0,
    })
    for row in rows:
        s = stats[row.platform]
        sentiment = row.sentiment if row.sentiment in ('positive', 'neutral', 'negative') else 'neutral'
        s[sentiment] += row.cnt
        s['total'] += row.cnt
        s['likes'] += row.likes or 0
        s['comments'] += row.comments or 0
        s['shares'] += row.shares or 0

    # 平均情感分需要独立聚合（按平台整体）
    avg_rows = query.with_entities(
        SentimentData.platform, func.avg(SentimentData.score)
    ).group_by(SentimentData.platform).all()
    avg_map = {p: float(a) for p, a in avg_rows}

    data = []
    for platform, s in stats.items():
        data.append({
            'platform': platform,
            'platform_name': PLATFORMS.get(platform, {}).get('name', platform),
            **{k: s[k] for k in ('total', 'positive', 'neutral', 'negative')},
            'avg_score': round(avg_map.get(platform, 0), 4),
            'negative_ratio': round(s['negative'] / s['total'], 4) if s['total'] else 0,
            'engagement': s['likes'] + s['comments'] * 2 + s['shares'] * 3,
            'likes': s['likes'], 'comments': s['comments'], 'shares': s['shares'],
        })
    data.sort(key=lambda x: x['total'], reverse=True)

    return jsonify(code=200, message='获取成功', data={'items': data})


@analysis_bp.route('/trend', methods=['GET'])
@jwt_required()
def get_trend():
    """声量与情感趋势：按天聚合，支持按平台拆分"""
    user_id = get_jwt_identity()
    days = request.args.get('days', 14, type=int)
    query = _base_query(user_id)
    since = (datetime.now() - timedelta(days=days - 1)).date()

    day_col = func.date(SentimentData.published_at)
    platform_rows = query.with_entities(day_col.label('d'), SentimentData.platform, func.count()) \
        .group_by('d', SentimentData.platform).all()
    sentiment_rows = query.with_entities(day_col.label('d'), SentimentData.sentiment, func.count()) \
        .group_by('d', SentimentData.sentiment).all()

    dates = [(since + timedelta(days=i)).isoformat() for i in range(days)]

    platform_daily = defaultdict(lambda: defaultdict(int))
    for d, platform, count in platform_rows:
        key = d if isinstance(d, str) else d.isoformat()
        platform_daily[platform][key] += count

    sentiment_daily = defaultdict(lambda: {'positive': 0, 'neutral': 0, 'negative': 0})
    for d, sentiment, count in sentiment_rows:
        key = d if isinstance(d, str) else d.isoformat()
        if sentiment in ('positive', 'neutral', 'negative'):
            sentiment_daily[key][sentiment] += count

    return jsonify(code=200, message='获取成功', data={
        'dates': dates,
        'platforms': [
            {
                'platform': p,
                'platform_name': PLATFORMS.get(p, {}).get('name', p),
                'data': [platform_daily[p].get(d, 0) for d in dates],
            }
            for p in sorted(platform_daily, key=lambda x: sum(platform_daily[x].values()), reverse=True)
        ],
        'sentiment_trend': [
            {'date': d, **sentiment_daily.get(d, {'positive': 0, 'neutral': 0, 'negative': 0})}
            for d in dates
        ],
    })


@analysis_bp.route('/keywords', methods=['GET'])
@jwt_required()
def get_keywords():
    """高频关键词聚合（用于词云展示）"""
    user_id = get_jwt_identity()
    top_k = request.args.get('top_k', 50, type=int)
    query = _base_query(user_id)

    counter = Counter()
    rows = query.with_entities(SentimentData.keywords) \
        .filter(SentimentData.keywords.isnot(None)).all()
    for (keywords_json,) in rows:
        try:
            counter.update(json.loads(keywords_json))
        except (ValueError, TypeError):
            continue

    items = [
        {'word': word, 'count': count}
        for word, count in counter.most_common(top_k)
    ]
    return jsonify(code=200, message='获取成功', data={'keywords': items})


@analysis_bp.route('/propagation', methods=['GET'])
@jwt_required()
def get_propagation():
    """跨平台传播溯源：各平台首发时间、峰值时间、日声量序列"""
    user_id = get_jwt_identity()
    days = request.args.get('days', 14, type=int)
    query = _base_query(user_id)
    since = (datetime.now() - timedelta(days=days - 1)).date()

    day_col = func.date(SentimentData.published_at)
    rows = query.with_entities(
        SentimentData.platform,
        day_col.label('d'),
        func.count().label('cnt'),
        func.min(SentimentData.published_at).label('first_seen'),
    ).group_by(SentimentData.platform, 'd').all()

    daily = defaultdict(dict)
    first_seen = {}
    totals = Counter()
    for row in rows:
        key = row.d if isinstance(row.d, str) else row.d.isoformat()
        daily[row.platform][key] = row.cnt
        totals[row.platform] += row.cnt
        if row.platform not in first_seen or row.first_seen < first_seen[row.platform]:
            first_seen[row.platform] = row.first_seen

    earliest = min(first_seen.values()) if first_seen else None
    dates = [(since + timedelta(days=i)).isoformat() for i in range(days)]

    items = []
    for platform, day_counts in daily.items():
        series = [day_counts.get(d, 0) for d in dates]
        peak_idx = series.index(max(series)) if series else 0
        items.append({
            'platform': platform,
            'platform_name': PLATFORMS.get(platform, {}).get('name', platform),
            'first_seen': first_seen[platform].isoformat() if first_seen.get(platform) else None,
            'delay_hours': round(
                (first_seen[platform] - earliest).total_seconds() / 3600, 1
            ) if earliest and first_seen.get(platform) else 0,
            'peak_date': dates[peak_idx],
            'total': totals[platform],
            'daily': series,
        })
    items.sort(key=lambda x: x['first_seen'] or '')

    return jsonify(code=200, message='获取成功', data={'dates': dates, 'items': items})


@analysis_bp.route('/hot-content', methods=['GET'])
@jwt_required()
def get_hot_content():
    """热门内容排行：按互动热度排序"""
    user_id = get_jwt_identity()
    limit = request.args.get('limit', 10, type=int)
    query = _base_query(user_id)

    engagement = (
        SentimentData.like_count
        + SentimentData.comment_count * 2
        + SentimentData.share_count * 3
    )
    items = query.order_by(engagement.desc()).limit(limit).all()

    return jsonify(code=200, message='获取成功', data={
        'items': [d.to_dict() for d in items]
    })


@analysis_bp.route('/sentiment', methods=['GET'])
@jwt_required()
def get_sentiment():
    """获取情感分析明细（最近 100 条）"""
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
    """热点话题（基于高频关键词的简易实现）"""
    user_id = get_jwt_identity()
    query = _base_query(user_id)

    counter = Counter()
    heat = Counter()
    rows = query.with_entities(
        SentimentData.keywords, SentimentData.like_count,
        SentimentData.comment_count, SentimentData.share_count
    ).filter(SentimentData.keywords.isnot(None)).limit(2000).all()

    for keywords_json, likes, comments, shares in rows:
        try:
            words = json.loads(keywords_json)
        except (ValueError, TypeError):
            continue
        engagement = (likes or 0) + (comments or 0) * 2 + (shares or 0) * 3
        for word in words[:3]:
            counter[word] += 1
            heat[word] += engagement

    topics = [
        {'topic': word, 'mentions': counter[word], 'heat': heat[word]}
        for word, _ in counter.most_common(10)
    ]
    return jsonify(code=200, message='获取成功', data={'topics': topics})
