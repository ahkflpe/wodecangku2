# -*- coding: utf-8 -*-
"""主程序入口"""

import argparse
from datetime import datetime
from selector import select_stocks
from backtester import backtest, print_report
from notifier import send_buy_signal, send_sell_signal
from config import BACKTEST_CONFIG


def run_select():
    """手动选股"""
    print(f"\n开始选股 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    stocks = select_stocks()

    if stocks:
        print(f"\n筛选结果: {len(stocks)} 只")
        for stock in stocks:
            print(f"{stock['code']} {stock['name']} "
                  f"价格:{stock['price']:.2f} "
                  f"涨幅:{stock['gain']*100:.2f}% "
                  f"换手:{stock['turnover']*100:.2f}%")

        # 发送邮件
        send_buy_signal(stocks)
    else:
        print("未筛选出符合条件的股票")
        send_buy_signal([])


def run_backtest(start_date, end_date, demo_mode=False):
    """运行回测"""
    report = backtest(start_date, end_date, demo_mode)
    print_report(report)

    # 保存详细报告
    import json
    with open('backtest_report.json', 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    print("\n详细报告已保存到 backtest_report.json")


def main():
    parser = argparse.ArgumentParser(description='杨永兴选股系统')
    parser.add_argument('--select', action='store_true', help='手动选股')
    parser.add_argument('--backtest', action='store_true', help='运行回测')
    parser.add_argument('--demo', action='store_true', help='Demo 模式（使用模拟数据）')
    parser.add_argument('--start', type=str, help='回测起始日期 (YYYYMMDD)')
    parser.add_argument('--end', type=str, help='回测结束日期 (YYYYMMDD)')

    args = parser.parse_args()

    if args.backtest:
        start = args.start or BACKTEST_CONFIG['start_date']
        end = args.end or BACKTEST_CONFIG['end_date']
        run_backtest(start, end, demo_mode=args.demo)
    elif args.select:
        run_select()
    else:
        print("请指定操作: --select (选股) 或 --backtest (回测)")
        print("示例: python main.py --select")
        print("示例: python main.py --backtest --demo  # Demo 模式回测")
        print("示例: python main.py --backtest --start 20250420 --end 20260420")


if __name__ == '__main__':
    main()
