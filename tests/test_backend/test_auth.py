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
        payload = {
            'username': 'testuser',
            'email': 'test@example.com',
            'password': 'password123'
        }
        client.post('/api/v1/auth/register', json=payload)
        response = client.post('/api/v1/auth/register', json=payload)
        assert response.status_code == 400
        assert response.json['code'] == 400

    def test_login_success(self, client):
        """测试正常登录"""
        client.post('/api/v1/auth/register', json={
            'username': 'testuser',
            'email': 'test@example.com',
            'password': 'password123'
        })
        response = client.post('/api/v1/auth/login', json={
            'email': 'test@example.com',
            'password': 'password123'
        })
        assert response.status_code == 200
        assert 'token' in response.json['data']

    def test_login_wrong_password(self, client):
        """测试密码错误"""
        client.post('/api/v1/auth/register', json={
            'username': 'testuser',
            'email': 'test@example.com',
            'password': 'password123'
        })
        response = client.post('/api/v1/auth/login', json={
            'email': 'test@example.com',
            'password': 'wrongpassword'
        })
        assert response.status_code == 401
