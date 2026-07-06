"""舆情数据模型"""
from datetime import datetime
from app import db


class SentimentData(db.Model):
    __tablename__ = 'sentiment_data'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    task_id = db.Column(db.Integer, db.ForeignKey('monitor_tasks.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    source = db.Column(db.String(100))
    author = db.Column(db.String(100))
    sentiment = db.Column(db.String(20))   # positive / negative / neutral
    score = db.Column(db.Float, default=0.0)
    published_at = db.Column(db.DateTime)
    collected_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'task_id': self.task_id,
            'content': self.content,
            'source': self.source,
            'author': self.author,
            'sentiment': self.sentiment,
            'score': self.score,
            'published_at': self.published_at.isoformat() if self.published_at else None,
            'collected_at': self.collected_at.isoformat()
        }
