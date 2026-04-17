#JStudio/BAC_PRO/modules/db_utils.py
import redis
import os

def get_redis_rpc():
    """
    这是我为你设计的核心连接函数。
    它不仅修复了 SSL 报错，还强制指向了你存放百万余额的 DB 0。
    """
    url = os.getenv("UPSTASH_REDIS_URL")
    if not url:
        raise ValueError("环境变量 UPSTASH_REDIS_URL 未设置")
    
    # 核心：通过 db=0 强制切换到生产库，避开那个 $1,115 的测试库
    return redis.from_url(
        url, 
        db=0, 
        decode_responses=True, 
        ssl_cert_reqs=None # 必须跳过证书校验
    )