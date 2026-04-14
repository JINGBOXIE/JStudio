import os
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

class Config:
    # 运行模式: MYSQL 或 REDIS
    RUN_MODE = os.getenv("RUN_MODE", "MYSQL").upper()

    # MySQL 配置
    MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_USER = os.getenv("MYSQL_USER", "root")
    MYSQL_PASS = os.getenv("MYSQL_PASS", "")
    MYSQL_DB = os.getenv("MYSQL_DB", "unified_account_system")

    # Redis (Upstash) 配置
    REDIS_URL = os.getenv("REDIS_URL", "")

    @classmethod
    def get_mysql_config(cls):
        return {
            "host": cls.MYSQL_HOST,
            "user": cls.MYSQL_USER,
            "password": cls.MYSQL_PASS,
            "database": cls.MYSQL_DB
        }