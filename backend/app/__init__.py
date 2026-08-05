"""应用工厂"""
import os

from flask import Flask
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from sqlalchemy import text as sa_text

db = SQLAlchemy()
jwt = JWTManager()


def create_app():
    """创建并配置 Flask 应用实例"""
    app = Flask(__name__)
    app.config.from_object('app.config.Config')

    db.init_app(app)
    jwt.init_app(app)

    # 生产环境限制 CORS 来源
    _cors_origin = os.getenv('CORS_ORIGIN', '*')
    CORS(app, resources={r"/api/*": {"origins": _cors_origin.split(',') if _cors_origin != '*' else '*'}})

    from app.routes.auth import auth_bp
    from app.routes.task import task_bp
    from app.routes.analysis import analysis_bp

    app.register_blueprint(auth_bp, url_prefix='/api/v1/auth')
    app.register_blueprint(task_bp, url_prefix='/api/v1/tasks')
    app.register_blueprint(analysis_bp, url_prefix='/api/v1/analysis')

    # Render 健康检查端点
    @app.route('/health')
    def health():
        try:
            db.session.execute(sa_text('SELECT 1'))
            db_ok = True
        except Exception:
            db_ok = False
        return {
            'status': 'ok' if db_ok else 'degraded',
            'db': db_ok
        }

    with app.app_context():
        db.create_all()
        _ensure_admin(app)

    return app


def _ensure_admin(app):
    """首次部署自动创建管理员账户"""
    from app.models.user import User
    email = os.getenv('ADMIN_EMAIL', 'admin@social-sense.com')
    password = os.getenv('ADMIN_PASSWORD', 'admin123')
    if not User.query.filter_by(email=email).first():
        admin = User(username='admin', email=email, role='admin')
        admin.set_password(password)
        db.session.add(admin)
        db.session.commit()
