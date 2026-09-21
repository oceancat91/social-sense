"""测试配置和 fixtures"""
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

from app import create_app, db
from app.services.crawler_service import CrawlerService


@pytest.fixture(autouse=True)
def force_mock_crawl(monkeypatch):
    """后端测试一律走 mock 数据源，禁止真实联网采集。

    生产采集策略是「优先真实适配器，缺 cookie 才回退 mock」；本机若存在
    cookie，测试就会真的去搜索、爬评论，导致耗时数分钟、结果随线上数据变化
    而不可复现（例如幂等用例的计数漂移）。这里直接禁用真实采集分支。
    """
    monkeypatch.setattr(
        CrawlerService,
        '_try_real_crawl',
        staticmethod(lambda *args, **kwargs: []),
    )


@pytest.fixture
def app():
    """创建测试用应用实例"""
    app = create_app()
    app.config.update({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
    })

    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture
def client(app):
    """创建测试客户端"""
    return app.test_client()
