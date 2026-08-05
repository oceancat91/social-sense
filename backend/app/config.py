"""应用配置"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv('APP_SECRET_KEY', os.urandom(32).hex())

    # 数据库：优先 DATABASE_URL（云平台自动注入），其次按 DB_DRIVER 选择
    DATABASE_URL = os.getenv('DATABASE_URL')
    if DATABASE_URL:
        # Render / Railway PostgreSQL: postgres:// -> postgresql://
        SQLALCHEMY_DATABASE_URI = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
    else:
        DB_DRIVER = os.getenv('DB_DRIVER', 'sqlite')
        if DB_DRIVER == 'sqlite':
            # Render 持久化磁盘：SQLite 文件放在 /var/data/ 目录
            _dir = os.getenv('RENDER_PERSISTENT_DIR', '')
            _path = os.getenv('SQLITE_PATH',
                              os.path.join(_dir, 'social_sense.db') if _dir else 'social_sense.db')
            SQLALCHEMY_DATABASE_URI = f'sqlite:///{_path}'
        elif DB_DRIVER == 'postgres':
            SQLALCHEMY_DATABASE_URI = (
                f"postgresql://{os.getenv('DB_USER', 'postgres')}:"
                f"{os.getenv('DB_PASSWORD', '')}@"
                f"{os.getenv('DB_HOST', 'localhost')}:"
                f"{os.getenv('DB_PORT', '5432')}/"
                f"{os.getenv('DB_NAME', 'social_sense')}"
            )
        else:
            SQLALCHEMY_DATABASE_URI = (
                f"mysql+pymysql://{os.getenv('DB_USER', 'root')}:"
                f"{os.getenv('DB_PASSWORD', '')}@"
                f"{os.getenv('DB_HOST', 'localhost')}:"
                f"{os.getenv('DB_PORT', '3306')}/"
                f"{os.getenv('DB_NAME', 'social_sense')}?charset=utf8mb4"
            )

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = os.getenv('APP_SECRET_KEY', os.urandom(32).hex())
    JWT_ACCESS_TOKEN_EXPIRES = 3600 * 24  # 24小时

    # 情感分析模型（HuggingFace），不可用时自动降级为词典分析
    SENTIMENT_MODEL_NAME = os.getenv(
        'SENTIMENT_MODEL_NAME',
        'lxyuan/distilbert-base-multilingual-cased-sentiments-student'
    )
    # 每个任务单次采集的最大数据量
    CRAWL_MAX_RECORDS = int(os.getenv('CRAWL_MAX_RECORDS', '600'))
