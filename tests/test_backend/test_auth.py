"""用户认证接口测试"""
import pytest


class TestAuth:
    """认证模块测试"""

    def test_register_success(self, client):
        """测试正常注册"""
        response = client.post('/api/v1/auth/register', json={
            'username': 'testuser',
            'email': 'test@example.com',
            'password': 'password123'
        })
        assert response.status_code == 200
        assert response.json['code'] == 200

    def test_register_duplicate_email(self, client):
        """测试重复邮箱注册"""
        # TODO: 实现测试
        pass

    def test_login_success(self, client):
        """测试正常登录"""
        # TODO: 实现测试
        pass

    def test_login_wrong_password(self, client):
        """测试密码错误"""
        # TODO: 实现测试
        pass
