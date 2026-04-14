import sys
import os

# 将项目根目录添加到路径，确保可以导入其他模块
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.config import Config
from utils.logger import Logger

class FinanceSystem:
    def __init__(self, mode=None):
        """
        初始化财务系统
        :param mode: 强制指定模式 ('MYSQL' 或 'REDIS')，如果不传则读取 .env 配置
        """
        # 1. 确定运行模式
        self.mode = mode.upper() if mode else Config.RUN_MODE
        self.logger = Logger()
        
        # 2. 根据模式动态加载适配器
        if self.mode == "MYSQL":
            from adapters.mysql_adapter import MySQLAdapter
            self.adapter = MySQLAdapter()
            self.logger.info("Finance System initialized in MYSQL mode.")
        elif self.mode == "REDIS":
            from adapters.redis_adapter import RedisAdapter
            self.adapter = RedisAdapter()
            self.logger.info("Finance System initialized in REDIS mode.")
        else:
            raise ValueError(f"Unsupported RUN_MODE: {self.mode}")

    # --- 统一业务接口 ---

    def get_balance(self, uid):
        """获取用户余额"""
        return self.adapter.get_user_balance(uid)

    def place_bet(self, uid, app_id, amount, bet_data):
        """
        统一下注入口
        :param uid: 用户ID
        :param app_id: 应用标识 ('iMarket' 或 'BacPro')
        :param amount: 下注金额
        :param bet_data: 下注详细数据 (字典格式)
        """
        # 基础校验
        if amount <= 0:
            return {"status": "error", "message": "Amount must be greater than 0"}

        # 1. 权限检查
        if not self.adapter.check_app_access(uid, app_id):
            self.logger.error(f"Access Denied: User {uid} -> {app_id}")
            return {"status": "error", "message": f"User has no access to {app_id}"}

        # 2. 调用适配器执行原子下注
        result = self.adapter.execute_bet(uid, app_id, amount, bet_data)
        
        # 3. 记录审计日志
        if result["status"] == "success":
            self.logger.info(f"BET SUCCESS: User {uid} | App {app_id} | Amt {amount} | BetID {result['bet_id']}")
        else:
            self.logger.error(f"BET FAILED: User {uid} | Msg: {result.get('message')}")
            
        return result

    def settle_bet(self, bet_id, win_amount):
        """
        统一结算入口
        :param bet_id: 注单ID
        :param win_amount: 派彩金额 (0 表示未中奖)
        """
        # 1. 执行结算
        result = self.adapter.execute_settle(bet_id, win_amount)
        
        # 2. 记录审计日志
        if result["status"] == "success":
            self.logger.info(f"SETTLE SUCCESS: BetID {bet_id} | WinAmt {win_amount} | NetProfit {result.get('net_profit')}")
        else:
            self.logger.error(f"SETTLE FAILED: BetID {bet_id} | Msg: {result.get('message')}")
            
        return result

    def check_status(self):
        """系统健康检查"""
        return {
            "mode": self.mode,
            "adapter": self.adapter.__class__.__name__
        }