import redis
import os

# 使用单例模式或连接池，避免 Streamlit 频繁刷新导致连接数耗尽
_redis_client = None

def get_redis_rpc(host='localhost', port=6379, db=0, password=None):
    """
    获取 Redis 连接实例。
    默认开启 decode_responses=True，确保返回的是字符串而非 bytes。
    """
    global _redis_client
    
    if _redis_client is None:
        try:
            # 建立连接池
            pool = redis.ConnectionPool(
                host=host,
                port=port,
                db=db,
                password=password,
                decode_responses=True,  # 关键：自动将 bytes 转为 str
                socket_timeout=2,        # 设置超时，防止程序卡死
                socket_connect_timeout=2,
                retry_on_timeout=True
            )
            _redis_client = redis.Redis(connection_pool=pool)
            
            # 立即执行一次 PING 测试物理连接
            _redis_client.ping()
            
        except redis.ConnectionError as e:
            print(f"❌ Redis Connection Error: {e}")
            # 如果连接失败，返回 None 或抛出异常，让调用方处理
            return None
            
    return _redis_client

def get_user_balance(uid="J"):
    """
    高层封装：直接获取用户余额
    """
    try:
        r = get_redis_rpc()
        if r:
            # Redis HGET 命令
            val = r.hget(f"u:info:{uid.upper()}", "balance")
            # 转换为 float，如果不存在则返回 0.0
            return float(val) if val else 0.0
        return None
    except Exception as e:
        print(f"❌ Error fetching balance for {uid}: {e}")
        return None

def update_user_balance(uid, amount):
    """
    高层封装：更新用户余额
    """
    try:
        r = get_redis_rpc()
        if r:
            r.hset(f"u:info:{uid.upper()}", "balance", amount)
            return True
        return False
    except Exception as e:
        print(f"❌ Error updating balance: {e}")
        return False