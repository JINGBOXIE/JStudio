import redis
import json
from .base_adapter import BaseAdapter
from utils.config import Config

class RedisAdapter(BaseAdapter):
    def __init__(self):
        self.r = None
        self.connect()

    def connect(self):
        """连接到 Upstash Redis (跳过 SSL 证书验证)"""
        try:
            # 关键改动：加入 ssl_cert_reqs=None
            self.r = redis.from_url(
                Config.REDIS_URL, 
                decode_responses=True,
                ssl_cert_reqs=None 
            )
            self.r.ping()
            print("Successfully connected to Upstash Redis (SSL Ignored)")
        except Exception as e:
            print(f"Redis Connection Error: {e}")
            raise e

    def get_user_balance(self, uid):
        """获取余额"""
        data = self.r.hgetall(f"u:{uid}:acc")
        if not data:
            return None
        return {
            "balance": float(data.get("balance", 0)),
            "frozen": float(data.get("frozen", 0)),
            "total_pnl": float(data.get("total_pnl", 0))
        }

    def check_app_access(self, uid, app_id):
        """权限检查 (简单实现：检查权限 Set)"""
        return self.r.sismember(f"u:{uid}:perms", app_id)

    def execute_bet(self, uid, app_id, amount, bet_data):
        """
        使用 LUA 脚本保证原子性：
        1. 检查余额
        2. 扣钱
        3. 生成自增 BetID
        4. 写入注单 Hash
        """
        lua_script = """
        local uid = ARGV[1]
        local amount = tonumber(ARGV[2])
        local app_id = ARGV[3]
        local bet_info = ARGV[4]
        
        local acc_key = "u:" .. uid .. ":acc"
        local balance = tonumber(redis.call("HGET", acc_key, "balance") or "0")
        
        if balance < amount then
            return {err = "INSUFFICIENT_BALANCE"}
        end
        
        -- 扣钱
        redis.call("HINCRBYFLOAT", acc_key, "balance", -amount)
        
        -- 生成 ID 并存单
        local bet_id = redis.call("INCR", "global:bet_id")
        local bet_key = "b:" .. bet_id
        redis.call("HSET", bet_key, 
            "uid", uid, 
            "app_id", app_id, 
            "amount", amount, 
            "status", 0, 
            "data", bet_info
        )
        return bet_id
        """
        try:
            result = self.r.eval(lua_script, 0, uid, amount, app_id, json.dumps(bet_data))
            if isinstance(result, dict) and "err" in result:
                return {"status": "error", "message": result["err"]}
            return {"status": "success", "bet_id": result}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def execute_settle(self, bet_id, win_amount):
        """
        使用 LUA 脚本结算：
        1. 读取注单并校验状态
        2. 计算盈亏
        3. 增加余额和总盈亏
        4. 更新注单状态
        """
        lua_script = """
        local bet_id = ARGV[1]
        local win_amount = tonumber(ARGV[2])
        local bet_key = "b:" .. bet_id
        
        local bet = redis.call("HGETALL", bet_key)
        if #bet == 0 then return {err = "BET_NOT_FOUND"} end
        
        -- 解析 HGETALL (Redis 返回的是平铺列表)
        local b_data = {}
        for i=1, #bet, 2 do b_data[bet[i]] = bet[i+1] end
        
        if b_data.status ~= "0" then return {err = "ALREADY_SETTLED"} end
        
        local uid = b_data.uid
        local original_amount = tonumber(b_data.amount)
        local net_profit = win_amount - original_amount
        
        -- 更新账户
        local acc_key = "u:" .. uid .. ":acc"
        redis.call("HINCRBYFLOAT", acc_key, "balance", win_amount)
        redis.call("HINCRBYFLOAT", acc_key, "total_pnl", net_profit)
        
        -- 更新注单
        local new_status = win_amount > 0 and 1 or 2
        redis.call("HSET", bet_key, "status", new_status)
        
        return tostring(net_profit)
        """
        try:
            result = self.r.eval(lua_script, 0, bet_id, win_amount)
            if isinstance(result, dict) and "err" in result:
                return {"status": "error", "message": result["err"]}
            return {"status": "success", "net_profit": float(result)}
        except Exception as e:
            return {"status": "error", "message": str(e)}