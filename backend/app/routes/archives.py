"""档案阵列路由：为 SENSE LAB 档案终端提供运行期数据。

这些端点取代了原先烘焙进前端构建产物的 content/archives.json，
因此更新观测数据不再需要重新构建前端。

档案内容本身是已归档的聚合结论（此前就随前端 bundle 公开发布），
故读取端点不要求登录；刷新缓存会改动服务端状态，需要管理员令牌。
"""
from datetime import datetime, timezone

from flask import Blueprint, Response, jsonify
from flask_jwt_extended import get_jwt_identity, jwt_required

from app import db
from app.models.user import User
from app.services import archive_service

archives_bp = Blueprint('archives', __name__)


@archives_bp.route('/archives', methods=['GET'])
def list_archives():
    """返回完整档案阵列。前端启动时调用一次。"""
    try:
        payload, source = archive_service.get_payload()
    except RuntimeError as exc:
        return jsonify(code=503, message=str(exc)), 503

    return jsonify(
        code=200,
        message='获取成功',
        data=payload,
        meta={
            'source': source,          # live=按报告实时计算，snapshot=镜像内快照
            'count': len(payload['records']),
            'categories': len(payload['categories']),
            'served_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        },
    )


@archives_bp.route('/archives/<file_id>/download', methods=['GET'])
def download_archive(file_id: str):
    """导出单份档案为可下载文本（对应前端 EXPORT 按钮）。"""
    record = archive_service.find_record(file_id)
    if record is None:
        return jsonify(code=404, message=f'未找到档案 {file_id}'), 404

    filename = f"SENSE-LAB-{record['id']}.txt"
    return Response(
        archive_service.archive_text(record),
        # Flask 会自动补上 charset=utf-8，这里只给基础类型。
        mimetype='text/plain',
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"',
            # 档案正文随报告更新，避免中间层缓存旧内容。
            'Cache-Control': 'no-cache',
        },
    )


@archives_bp.route('/archives/refresh', methods=['POST'])
@jwt_required()
def refresh_archives():
    """丢弃进程内缓存，下次读取时重算。仅管理员。"""
    user = db.session.get(User, int(get_jwt_identity()))
    if user is None or user.role != 'admin':
        return jsonify(code=403, message='需要管理员权限'), 403

    archive_service.invalidate()
    try:
        payload, source = archive_service.get_payload(force=True)
    except RuntimeError as exc:
        return jsonify(code=503, message=str(exc)), 503

    return jsonify(
        code=200,
        message='档案缓存已刷新',
        data={'source': source, 'count': len(payload['records'])},
    )
