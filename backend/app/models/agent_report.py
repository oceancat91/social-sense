"""多 Agent 分析报告模型：持久化跨平台分析结果"""
import json
from datetime import datetime

from app import db


class AgentReport(db.Model):
    __tablename__ = 'agent_reports'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    task_id = db.Column(db.Integer, db.ForeignKey('monitor_tasks.id'), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    keyword = db.Column(db.String(255), nullable=False)
    platforms = db.Column(db.String(255), default='')   # 逗号分隔的平台列表
    status = db.Column(db.String(20), default='pending')  # pending/running/success/failed/partial
    progress = db.Column(db.Text)                        # 结构化进度（JSON 字符串）
    # result 含完整平台报告 + 对齐时序，单条可达数 MB，须用 LONGTEXT（TEXT 仅 64KB）
    result = db.Column(db.LONGTEXT)                      # run_full_analysis 输出（JSON 字符串）
    error = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self, include_result: bool = False):
        data = {
            'id': self.id,
            'task_id': self.task_id,
            'user_id': self.user_id,
            'keyword': self.keyword,
            'platforms': self.platform_list(),
            'status': self.status,
            'progress': self.progress_dict(),
            'error': self.error,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
        }
        if include_result and self.result:
            try:
                data['result'] = json.loads(self.result)
            except (ValueError, TypeError):
                data['result'] = None
        return data

    def progress_dict(self):
        """解析 progress JSON，失败返回 None。"""
        if not self.progress:
            return None
        try:
            return json.loads(self.progress)
        except (ValueError, TypeError):
            return None

    def platform_list(self):
        if not self.platforms:
            return []
        return [p for p in self.platforms.split(',') if p]
