"""应用配置"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv('APP_SECRET_KEY', 'dev-secret-key')
    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{os.getenv('DB_USER', 'root')}:"
        f"{os.getenv('DB_PASSWORD', '')}@"
        f"{os.getenv('DB_HOST', 'localhost')}:"
        f"{os.getenv('DB_PORT', '3306')}/"
        f"{os.getenv('DB_NAME', 'social_sense')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = os.getenv('APP_SECRET_KEY', 'jwt-secret-key')
    JWT_ACCESS_TOKEN_EXPIRES = 3600 * 24  # 24小时
