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

# core/db_adapter.py



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