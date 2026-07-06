"""应用工厂"""
from flask import Flask
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager

db = SQLAlchemy()
jwt = JWTManager()


def create_app():
    """创建并配置 Flask 应用实例"""
    app = Flask(__name__)
    app.config.from_object('app.config.Config')

    db.init_app(app)
    jwt.init_app(app)
    CORS(app)

    from app.routes.auth import auth_bp
    from app.routes.task import task_bp
    from app.routes.analysis import analysis_bp

    app.register_blueprint(auth_bp, url_prefix='/api/v1/auth')
    app.register_blueprint(task_bp, url_prefix='/api/v1/tasks')
    app.register_blueprint(analysis_bp, url_prefix='/api/v1/analysis')

    with app.app_context():
        db.create_all()

    return app
