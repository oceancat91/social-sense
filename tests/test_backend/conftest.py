"""测试配置和 fixtures"""
import pytest
from app import create_app, db


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
