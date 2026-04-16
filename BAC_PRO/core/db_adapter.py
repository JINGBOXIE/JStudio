import redis
import json
import hashlib
from core.snapshot_engine import build_state_key  # 核心：必须调用这个函数
# core/db_adapter.py

class RedisAdapter:
    def __init__(self, redis_url):
        try:
            # 加入 ssl_cert_reqs=None 以跳过证书校验
            self.client = redis.from_url(
                redis_url, 
                decode_responses=True,
                ssl_cert_reqs=None  # ✨ 关键：修复 [SSL: CERTIFICATE_VERIFY_FAILED]
            )
        except Exception as e:
            print(f"Redis Connection Error: {e}")
            
    # --- ✨ 新增：专门查询 Entropy JSON 数据的函数 ---
    def get_entropy_decision(self, rk_id):
        """
        专门用于查询线上 E: 开头的 JSON 字符串指纹
        """
        try:
            # 自动补全前缀，确保与线上 E:000000000000000000 格式一致
            target_key = f"E:{rk_id}" if not rk_id.startswith("E:") else rk_id
            
            raw_data = self.client.get(target_key)
            #st.toast(f"Searching: {target_key}")
            
            if raw_data:
                # 解析终端测试看到的 JSON 格式: {"a": "N", "eb": -0.0106, ...}
                data = json.loads(raw_data)
                
                # 转换线上简写字段名为程序使用的标准字段名
                # a -> action, t -> tier, eb -> ev_cut, ep -> ev_cont
                return {
                    "action": data.get("a", "N"),
                    "edge": max(float(data.get("ep", 0)), float(data.get("eb", 0))),
                    "ev_cut": float(data.get("eb", 0)),
                    "ev_cont": float(data.get("ep", 0)),
                    "tier": data.get("t", "N")
                }
            return None
        except Exception as e:
            print(f"Entropy Query Error: {e}")
            return None
    
    def get_state_decision(self, state_hash):
        """
        物理对齐版本：优先处理 Hash 类型
        """
        try:
            target_key = state_hash.strip()
            
            # 1. 尝试 HGETALL (针对终端显示的 hash 结构)
            data = self.client.hgetall(target_key)
            
            if data and isinstance(data, dict) and "action" in data:
                return {
                    "action": data.get("action"),
                    "edge": float(data.get("edge", 0)),
                    "ev_cut": float(data.get("ev_cut", 0)),
                    "ev_cont": float(data.get("ev_cont", 0))
                }

            # 2. 备选：尝试 String 协议
            raw_data = self.client.get(target_key)
            if raw_data:
                parts = raw_data.split('|')
                return {
                    "action": parts[0],
                    "edge": float(parts[1]),
                    "ev_cut": float(parts[2]),
                    "ev_cont": float(parts[3])
                }
            return None
        except Exception as e:
            return None

# === 今日新增：下注流水写入逻辑（对齐老版本变量名 self.client） ===

    def record_app_transaction(self, user_id, username, amount, tx_type, strategy, hist_len, bet_len, action):
        """
        核心写入函数：处理余额更新与流水存档。
        使用了 self.client 确保与你的初始化变量名一致。
        """
        import uuid, datetime
        # 1. 生成流水 ID 和时间
        tx_id = f"TX_{uuid.uuid4().hex[:10].upper()}"
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        norm_action = "CONTINUE" if str(action).upper() in ["S", "CONTINUE", "STAY"] else "CUT"
        
        try:
            # 🟢 控制台调试：如果你在终端运行，这里会显示数据飞往哪个库
            conn_info = self.client.connection_pool.connection_kwargs
            print(f"📡 [DEBUG] Redis Writing to: {conn_info.get('host')} | TX: {tx_id}")

            # 2. 开启管道 (Pipeline) 保证原子性
            pipe = self.client.pipeline()
            
            # 3. 强制转换数字类型，防止 Redis 报错
            val = float(amount)
            
            # 4. 执行写入
            # 更新余额
            new_balance = self.client.hincrbyfloat(f"u:info:{user_id}", "balance", val)
            # 记录用户名
            self.client.hset(f"u:info:{user_id}", "user", username)
            
            # 5. 构造详细流水包
            tx_data = {
                "userID": user_id,
                "user": username,
                "type": tx_type,
                "strategy": strategy,
                "action": norm_action,
                "hist_len": hist_len,
                "bet_len": bet_len,
                "amount": val,
                "balance": new_balance,
                "datetime": now,
                "txID": tx_id
            }
            
            # 6. 写入 Hash 详情并推入用户流水列表
            pipe.hset(f"tx:{tx_id}", mapping=tx_data)
            pipe.lpush(f"u:tx_list:{user_id}", tx_id)
            
            # ⚡ 这一步是关键：必须执行管道，数据才会真的发给 Redis 服务器
            pipe.execute()
            
            return new_balance
            
        except Exception as e:
            print(f"❌ Redis Write Error: {e}")
            return None

    def sync_transaction(self, uid, username, amount, tx_type, strategy, h_len, b_len, action):
        """
        备用入口：直接指向主写入函数
        """
        return self.record_app_transaction(
            user_id=uid, 
            username=username, 
            amount=amount, 
            tx_type=tx_type, 
            strategy=strategy, 
            hist_len=h_len, 
            bet_len=b_len, 
            action=action
        )
def generate_fp_hash(cur_side, cur_len, hist_B, hist_P, hist_min=3):
    """
    V8 物理对齐正式版
    """
    # 1. 严格执行 hist_min 过滤（确保与 1.4M 数据采样逻辑一致）
    f_B = {k: v for k, v in hist_B.items() if int(k) >= hist_min}
    f_P = {k: v for k, v in hist_P.items() if int(k) >= hist_min}
    
    # 2. 调用引擎函数生成那串“B|4|HB=...|HP=...”的原始字符串
    raw_key = build_state_key(
        cur_side=cur_side,
        cur_len=cur_len,
        hist_B=f_B,
        hist_P=f_P
    )
    
    # 3. 对该原始字符串进行 SHA256 哈希
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
