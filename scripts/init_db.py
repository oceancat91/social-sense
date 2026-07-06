"""数据库初始化脚本"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from app import create_app, db
from app.models.user import User


def init_database():
    """初始化数据库并创建管理员账户"""
    app = create_app()
    with app.app_context():
        db.create_all()
        print('数据库表创建成功')

        admin = User.query.filter_by(email='admin@social-sense.com').first()
        if not admin:
            admin = User(
                username='admin',
                email='admin@social-sense.com',
                role='admin'
            )
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print('管理员账户创建成功')
            print('  邮箱: admin@social-sense.com')
            print('  密码: admin123')
        else:
            print('管理员账户已存在')


if __name__ == '__main__':
    init_database()
