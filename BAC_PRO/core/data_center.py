# core/data_center.py
from core.snapshot_engine import get_fp_components
from core.db_adapter import generate_fp_hash

class DataCenter:
    def __init__(self, session_state):
        self.ss = session_state

    def update_seq(self, res: str):
        if "auto_clean_seq" not in self.ss:
            self.ss["auto_clean_seq"] = []
        if res in ["B", "P"]:
            self.ss["auto_clean_seq"].append(res)
        return self.ss["auto_clean_seq"]

    def get_components(self, seq, h_min: int):
        # 核心快照提取：分离 Current 与 History
        return get_fp_components(seq, h_min=h_min)

    def build_hash_from_components(self, components):
        # 直接调用锁定的工厂函数，禁止在外界拼接字符串
        return generate_fp_hash(*components)

    def build_hash(self, seq, h_min: int):
        # 备用快捷入口
        components = self.get_components(seq, h_min)
        return self.build_hash_from_components(components)
