"""数据库初始化脚本"""
import os
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / 'backend'))

from app import create_app
from app.models.user import User


def init_database():
    """初始化数据库并创建管理员账户"""
    app = create_app()
    with app.app_context():
        print('数据库表创建成功')
        email = os.getenv('ADMIN_EMAIL', 'admin@social-sense.com')
        admin = User.query.filter_by(email=email).first()
        if admin is None:
            raise RuntimeError('应用初始化后仍未找到管理员账户')
        print(f'管理员账户已就绪: {admin.email}')


if __name__ == '__main__':
    init_database()
