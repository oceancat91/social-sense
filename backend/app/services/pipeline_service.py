"""舆情数据处理管道：采集 → 清洗 → 情感分析 → 关键词提取 → 入库"""
import json
import logging
import threading

from app import db
from app.models.sentiment import SentimentData
from app.models.task import MonitorTask
from app.services.cleaning_service import CleaningService
from app.services.crawler_service import CrawlerService
from app.services.sentiment_service import SentimentService

logger = logging.getLogger(__name__)

BATCH_SIZE = 64


class PipelineService:
    """任务级数据处理管道"""

    @classmethod
    def run_task_pipeline(cls, app, task_id: int, days: int = 14, limit: int = None):
        """
        执行完整处理管道（设计为可在后台线程中运行）。
        :param app: Flask 应用实例（线程内需要应用上下文）
        :param task_id: 监控任务 ID
        :param days: 模拟事件回溯天数
        :param limit: 采集数据量上限
        """
        with app.app_context():
            task = db.session.get(MonitorTask, task_id)
            if not task:
                logger.error('任务不存在: %s', task_id)
                return

            max_records = limit or app.config.get('CRAWL_MAX_RECORDS', 600)
            task.status = 'collecting'
            db.session.commit()

            try:
                keyword = task.keywords.split(',')[0].strip()
                stats = cls._execute(task, keyword, days, max_records)
                task.status = 'active'
                task.data_count = SentimentData.query.filter_by(task_id=task.id).count()
                db.session.commit()
                logger.info('任务 %s 管道完成: %s', task_id, stats)
            except Exception as exc:
                db.session.rollback()
                task = db.session.get(MonitorTask, task_id)
                if task:
                    task.status = 'active'
                    db.session.commit()
                logger.exception('任务 %s 管道执行失败: %s', task_id, exc)

    @classmethod
    def _execute(cls, task: MonitorTask, keyword: str, days: int, limit: int,
                 progress_cb=None, phase_cb=None) -> dict:
        """采集 → 清洗 → 分析 → 入库

        :param progress_cb: 平台级采集进度回调 progress_cb(platform, state)
        :param phase_cb: 阶段切换回调 phase_cb(phase)，phase 为 'clean'/'sentiment'
        """
        # 1. 采集
        raw_records = CrawlerService.crawl(
            keyword=keyword, platform=task.platform, days=days, limit=limit,
            progress_cb=progress_cb,
        )

        # 2. 清洗去重（管道内）
        if phase_cb:
            phase_cb('clean')
        cleaned, clean_stats = CleaningService.clean_batch(raw_records)

        # 3. 与库内已有数据去重（支持重复运行）
        existing_hashes = {
            row.content_hash
            for row in SentimentData.query.with_entities(SentimentData.content_hash)
            .filter_by(task_id=task.id).all()
        }
        cleaned = [r for r in cleaned if r['content_hash'] not in existing_hashes]

        # 4. 情感分析 + 关键词提取 + 入库（分批）
        if phase_cb:
            phase_cb('sentiment')
        inserted = 0
        for i in range(0, len(cleaned), BATCH_SIZE):
            batch = cleaned[i:i + BATCH_SIZE]
            sentiments = SentimentService.analyze_batch([r['content'] for r in batch])

            for record, sentiment in zip(batch, sentiments):
                keywords = SentimentService.extract_keywords(record['content'], top_k=5)
                db.session.add(SentimentData(
                    task_id=task.id,
                    platform=record['platform'],
                    content_type=record.get('content_type', 'post'),
                    content=record['content'],
                    content_hash=record['content_hash'],
                    source=record.get('source'),
                    author=record.get('author'),
                    url=record.get('url'),
                    sentiment=sentiment['sentiment'],
                    score=sentiment['score'],
                    keywords=json.dumps([w for w, _ in keywords], ensure_ascii=False),
                    like_count=record.get('like_count', 0),
                    comment_count=record.get('comment_count', 0),
                    share_count=record.get('share_count', 0),
                    published_at=record.get('published_at'),
                ))
            db.session.commit()
            inserted += len(batch)

        return {
            'clean': clean_stats,
            'inserted': inserted,
            'analyzer': SentimentService.backend_name(),
        }

    @classmethod
    def run_in_background(cls, app, task_id: int, days: int = 14, limit: int = None):
        """后台线程方式运行管道，避免阻塞请求"""
        thread = threading.Thread(
            target=cls.run_task_pipeline,
            args=(app, task_id, days, limit),
            daemon=True,
        )
        thread.start()
        return thread
