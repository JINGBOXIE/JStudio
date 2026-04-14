import mysql.connector
from mysql.connector import Error
from .base_adapter import BaseAdapter
from utils.config import Config
import json

class MySQLAdapter(BaseAdapter):
    def __init__(self):
        self.config = Config.get_mysql_config()
        self.conn = None
        self.connect()

    def connect(self):
        """建立数据库连接"""
        try:
            self.conn = mysql.connector.connect(**self.config)
            if self.conn.is_connected():
                print("Successfully connected to MySQL database")
        except Error as e:
            print(f"Error connecting to MySQL: {e}")
            raise e

    def _get_cursor(self):
        """获取游标，如果连接断开则重连"""
        if not self.conn.is_connected():
            self.connect()
        return self.conn.cursor(dictionary=True)

    def get_user_balance(self, uid):
        """查询余额 (增加 cursor.close 确保不占用连接)"""
        cursor = self._get_cursor()
        try:
            query = "SELECT balance, frozen, total_pnl FROM accounts WHERE uid = %s"
            cursor.execute(query, (uid,))
            return cursor.fetchone()
        finally:
            cursor.close()  # <-- 必须关闭，否则连接会一直处于“忙碌”状态

    def execute_bet(self, uid, app_id, amount, bet_data):
        """原子操作：扣款 + 记录注单"""
        cursor = self._get_cursor()
        try:
            # 1. 强制清理任何残留事务状态
            if self.conn.in_transaction:
                self.conn.rollback()

            self.conn.start_transaction()

            # 2. 锁定并校验
            cursor.execute("SELECT balance FROM accounts WHERE uid = %s FOR UPDATE", (uid,))
            account = cursor.fetchone()
            
            if not account or float(account['balance']) < float(amount):
                raise Exception("Insufficient balance or user not found")

            # 3. 扣款与记账
            cursor.execute("UPDATE accounts SET balance = balance - %s WHERE uid = %s", (amount, uid))
            cursor.execute(
                "INSERT INTO bets (uid, app_id, amount, bet_data, status) VALUES (%s, %s, %s, %s, 0)",
                (uid, app_id, amount, json.dumps(bet_data))
            )
            
            bet_id = cursor.lastrowid
            self.conn.commit()
            return {"status": "success", "bet_id": bet_id}

        except Exception as e:
            if self.conn: self.conn.rollback()
            return {"status": "error", "message": str(e)}
        finally:
            cursor.close() # <-- 必须关闭

    def check_app_access(self, uid, app_id):
        """权限检查"""
        cursor = self._get_cursor()
        query = "SELECT 1 FROM user_app_permissions WHERE uid = %s AND app_id = %s"
        cursor.execute(query, (uid, app_id))
        return cursor.fetchone() is not None

    

    def execute_settle(self, bet_id, win_amount):
        """
        原子操作：结算注单 -> 更新余额和盈亏
        """
        cursor = self._get_cursor()
        try:
            self.conn.start_transaction()

            # 1. 锁定注单并获取原始金额
            cursor.execute("SELECT uid, amount, status FROM bets WHERE bet_id = %s FOR UPDATE", (bet_id,))
            bet = cursor.fetchone()

            if not bet:
                raise Exception("Bet record not found")
            if bet['status'] != 0:
                raise Exception("Bet already settled")

            uid = bet['uid']
            original_amount = float(bet['amount'])
            net_profit = float(win_amount) - original_amount

            # 2. 更新账户余额和总盈亏
            # 余额增加派彩金额，盈亏增加 (派彩 - 本金)
            update_acc_query = """
                UPDATE accounts 
                SET balance = balance + %s, 
                    total_pnl = total_pnl + %s 
                WHERE uid = %s
            """
            cursor.execute(update_acc_query, (win_amount, net_profit, uid))

            # 3. 更新注单状态
            # status: 1为赢(win_amount > 0), 2为输(win_amount == 0)
            new_status = 1 if float(win_amount) > 0 else 2
            update_bet_query = "UPDATE bets SET status = %s, settled_at = NOW() WHERE bet_id = %s"
            cursor.execute(update_bet_query, (new_status, bet_id))

            self.conn.commit()
            return {"status": "success", "net_profit": net_profit}

        except Exception as e:
            self.conn.rollback()
            return {"status": "error", "message": str(e)}
        finally:
            cursor.close()