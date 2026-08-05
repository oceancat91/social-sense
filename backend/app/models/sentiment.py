"""舆情数据模型"""
import json
from datetime import datetime
from app import db


class SentimentData(db.Model):
    __tablename__ = 'sentiment_data'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    task_id = db.Column(db.Integer, db.ForeignKey('monitor_tasks.id'), nullable=False)
    platform = db.Column(db.String(20), index=True)      # weibo/douyin/xiaohongshu/bilibili/zhihu/kuaishou
    content_type = db.Column(db.String(20), default='post')  # post / comment / video
    content = db.Column(db.Text, nullable=False)
    content_hash = db.Column(db.String(64), index=True)  # 用于去重
    source = db.Column(db.String(100))
    author = db.Column(db.String(100))
    url = db.Column(db.String(255))
    sentiment = db.Column(db.String(20), index=True)     # positive / negative / neutral
    score = db.Column(db.Float, default=0.0)             # [-1, 1]，负值为负面情绪
    keywords = db.Column(db.String(500))                 # 提取的关键词（JSON 数组）
    like_count = db.Column(db.Integer, default=0)
    comment_count = db.Column(db.Integer, default=0)
    share_count = db.Column(db.Integer, default=0)
    published_at = db.Column(db.DateTime, index=True)
    collected_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('task_id', 'content_hash', name='uq_task_content'),
    )

    @property
    def engagement(self):
        """互动热度：点赞 + 评论*2 + 转发*3"""
        return (self.like_count or 0) + (self.comment_count or 0) * 2 + (self.share_count or 0) * 3

    def keyword_list(self):
        if not self.keywords:
            return []
        try:
            return json.loads(self.keywords)
        except (ValueError, TypeError):
            return []

    def to_dict(self):
        return {
            'id': self.id,
            'task_id': self.task_id,
            'platform': self.platform,
            'content_type': self.content_type,
            'content': self.content,
            'source': self.source,
            'author': self.author,
            'url': self.url,
            'sentiment': self.sentiment,
            'score': self.score,
            'keywords': self.keyword_list(),
            'like_count': self.like_count or 0,
            'comment_count': self.comment_count or 0,
            'share_count': self.share_count or 0,
            'engagement': self.engagement,
            'published_at': self.published_at.isoformat() if self.published_at else None,
            'collected_at': self.collected_at.isoformat()
        }
