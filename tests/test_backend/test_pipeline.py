"""数据清洗、模拟生成与处理管道测试"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

from app.models.sentiment import SentimentData
from app.models.task import MonitorTask
from app.models.user import User
from app.services.cleaning_service import CleaningService
from app.services.mock_data_service import MockDataGenerator, PLATFORM_PROFILES
from app.services.pipeline_service import PipelineService
from app import db


class TestCleaningService:
    """数据清洗测试"""

    def test_clean_html_and_url(self):
        text = '<p>查看详情 https://example.com 校园食品安全</p>'
        cleaned = CleaningService.clean_text(text)
        assert '<p>' not in cleaned
        assert 'https://' not in cleaned
        assert '校园食品安全' in cleaned

    def test_clean_mention_and_topic(self):
        text = '回复 @张三: #校园食品安全# 必须关注 @李四'
        cleaned = CleaningService.clean_text(text)
        assert '@张三' not in cleaned
        assert '#' not in cleaned
        assert '校园食品安全' in cleaned

    def test_invalid_short_text(self):
        assert not CleaningService.is_valid('好的')
        assert not CleaningService.is_valid('')

    def test_batch_dedup(self):
        records = [
            {'content': '校园食品安全必须严查'},
            {'content': '校园食品安全必须严查'},
            {'content': '完全不同的另一条内容'},
        ]
        cleaned, stats = CleaningService.clean_batch(records)
        assert stats['duplicated'] == 1
        assert stats['valid'] == 2
        assert all('content_hash' in r for r in cleaned)


class TestMockDataGenerator:
    """模拟数据生成器测试"""

    def test_generate_all_platforms(self):
        records = MockDataGenerator('测试事件', days=14).generate(total=300)
        assert len(records) > 0
        platforms = {r['platform'] for r in records}
        assert platforms == set(PLATFORM_PROFILES.keys())

    def test_generate_single_platform(self):
        records = MockDataGenerator('测试事件', days=7).generate(
            total=100, platforms=['weibo'])
        assert all(r['platform'] == 'weibo' for r in records)

    def test_deterministic(self):
        """相同关键词应生成相同数据（可复现）"""
        r1 = MockDataGenerator('测试').generate(total=50)
        r2 = MockDataGenerator('测试').generate(total=50)
        assert [r['content'] for r in r1] == [r['content'] for r in r2]

    def test_propagation_order(self):
        """传播时序：抖音应早于知乎开始"""
        records = MockDataGenerator('测试', days=14).generate(total=600)
        first = {}
        for r in records:
            p = r['platform']
            if p not in first or r['published_at'] < first[p]:
                first[p] = r['published_at']
        assert first['douyin'] < first['zhihu']

    def test_required_fields(self):
        records = MockDataGenerator('测试', days=7).generate(total=20)
        for r in records:
            assert r['content'] and r['author'] and r['published_at']
            assert r['like_count'] >= 0
            assert r['expected_sentiment'] in ('positive', 'neutral', 'negative')


class TestPipeline:
    """处理管道端到端测试"""

    def test_run_task_pipeline(self, app):
        with app.app_context():
            user = User(username='pipeuser', email='pipe@example.com')
            user.set_password('pass123')
            db.session.add(user)
            db.session.commit()

            task = MonitorTask(user_id=user.id, keywords='测试事件',
                               platform='all', status='collecting')
            db.session.add(task)
            db.session.commit()

            PipelineService.run_task_pipeline(app, task.id, days=7, limit=120)

            # 管道在嵌套上下文的独立会话中提交，需过期缓存再读取
            db.session.expire_all()
            task = db.session.get(MonitorTask, task.id)
            assert task.status == 'active'
            assert task.data_count > 0

            items = SentimentData.query.filter_by(task_id=task.id).all()
            assert all(i.sentiment in ('positive', 'neutral', 'negative') for i in items)
            assert all(i.platform in PLATFORM_PROFILES for i in items)
            assert all(i.keywords for i in items)

    def test_pipeline_idempotent(self, app):
        """重复运行管道不应产生重复数据"""
        with app.app_context():
            user = User(username='idemuser', email='idem@example.com')
            user.set_password('pass123')
            db.session.add(user)
            db.session.commit()

            task = MonitorTask(user_id=user.id, keywords='幂等测试', platform='all')
            db.session.add(task)
            db.session.commit()

            PipelineService.run_task_pipeline(app, task.id, days=7, limit=100)
            first_count = SentimentData.query.filter_by(task_id=task.id).count()

            PipelineService.run_task_pipeline(app, task.id, days=7, limit=100)
            second_count = SentimentData.query.filter_by(task_id=task.id).count()

            assert first_count > 0
            assert second_count == first_count
