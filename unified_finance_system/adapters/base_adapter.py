from abc import ABC, abstractmethod

class BaseAdapter(ABC):
    
    @abstractmethod
    def connect(self):
        """建立数据库连接"""
        pass

    @abstractmethod
    def get_user_balance(self, uid):
        """获取用户可用余额和冻结金额"""
        pass

    @abstractmethod
    def execute_bet(self, uid, app_id, amount, bet_data):
        """原子操作：扣款 + 记录注单"""
        pass

    @abstractmethod
    def execute_settle(self, bet_id, win_amount):
        """原子操作：结算注单 + 返还/更新余额"""
        pass

    @abstractmethod
    def check_app_access(self, uid, app_id):
        """检查用户是否有权访问特定 App"""
        pass