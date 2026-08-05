"""应用配置"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv('APP_SECRET_KEY', 'dev-secret-key')

    # DB_DRIVER=sqlite 可免装 MySQL 快速本地开发，生产环境使用 mysql
    DB_DRIVER = os.getenv('DB_DRIVER', 'mysql')
    if DB_DRIVER == 'sqlite':
        _sqlite_path = os.getenv('SQLITE_PATH', 'social_sense.db')
        SQLALCHEMY_DATABASE_URI = f'sqlite:///{_sqlite_path}'
    else:
        SQLALCHEMY_DATABASE_URI = (
            f"mysql+pymysql://{os.getenv('DB_USER', 'root')}:"
            f"{os.getenv('DB_PASSWORD', '')}@"
            f"{os.getenv('DB_HOST', 'localhost')}:"
            f"{os.getenv('DB_PORT', '3306')}/"
            f"{os.getenv('DB_NAME', 'social_sense')}?charset=utf8mb4"
        )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = os.getenv('APP_SECRET_KEY', 'jwt-secret-key')
    JWT_ACCESS_TOKEN_EXPIRES = 3600 * 24  # 24小时

    # 情感分析模型（HuggingFace），不可用时自动降级为词典分析
    SENTIMENT_MODEL_NAME = os.getenv(
        'SENTIMENT_MODEL_NAME',
        'lxyuan/distilbert-base-multilingual-cased-sentiments-student'
    )
    # 每个任务单次采集的最大数据量
    CRAWL_MAX_RECORDS = int(os.getenv('CRAWL_MAX_RECORDS', '600'))
