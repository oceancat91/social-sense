"""监控任务模型"""
from datetime import datetime
from app import db


class MonitorTask(db.Model):
    __tablename__ = 'monitor_tasks'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    keywords = db.Column(db.Text, nullable=False)
    platform = db.Column(db.String(50), default='all')   # all 表示全平台采集
    status = db.Column(db.String(20), default='active')  # active / collecting / paused
    data_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    sentiment_data = db.relationship('SentimentData', backref='task', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'keywords': self.keywords,
            'platform': self.platform,
            'status': self.status,
            'data_count': self.data_count or 0,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }
