from core.finance_system import FinanceSystem
import json

def run_test():
    # 1. 初始化财务系统 (默认读取 .env 中的模式)
    fs = FinanceSystem()
    print(f"--- 系统启动: 模式 [{fs.mode}] ---")

    test_uid = 1
    
    # 2. 查看初始余额
    acc = fs.get_balance(test_uid)
    if acc:
        print(f"初始状态: 余额 {acc['balance']}, 总盈亏 {acc['total_pnl']}")
    else:
        print("错误: 找不到测试用户，请先执行 SQL 初始化数据。")
        return

    # 3. 模拟 iMarket 下注 (100 元)
    print("\n[测试 1] 模拟 iMarket 下注...")
    bet_res = fs.place_bet(
        uid=test_uid, 
        app_id="iMarket", 
        amount=100.0, 
        bet_data={"event": "BTC/USDT", "type": "long"}
    )
    
    if bet_res["status"] == "success":
        bet_id = bet_res["bet_id"]
        print(f"下注成功! 注单ID: {bet_id}")
        
        # 4. 模拟结算 (赢了 150 元，即纯利润 50)
        print(f"\n[测试 2] 模拟注单 {bet_id} 结算...")
        settle_res = fs.settle_bet(bet_id, win_amount=150.0)
        
        if settle_res["status"] == "success":
            print(f"结算成功! 净利润: {settle_res['net_profit']}")
        else:
            print(f"结算失败: {settle_res['message']}")
    else:
        print(f"下注失败: {bet_res['message']}")

    # 5. 查看最终状态
    final_acc = fs.get_balance(test_uid)
    print(f"\n最终状态: 余额 {final_acc['balance']}, 总盈亏 {final_acc['total_pnl']}")

if __name__ == "__main__":
    try:
        run_test()
    except Exception as e:
        print(f"运行过程中发生崩溃: {e}")