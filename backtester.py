# -*- coding: utf-8 -*-
"""回测引擎（杨永兴尾盘战法专用，含诊断系统）"""

import sys
sys.dont_write_bytecode = True

import pandas as pd
from datetime import datetime, timedelta
from config import BACKTEST_CONFIG, RISK_CONFIG, SELECTOR_CONFIG


def _safe_float(val, default=0.0):
    if pd.isna(val):
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _build_date_stock_index(start_date, end_date):
    """预加载CSV数据，只保留日期范围内的行（含成交量、高低价）"""
    from data_fetcher import DATA_DIR

    start_int = int(start_date)
    end_int = int(end_date)
    date_stock_map = {}

    csv_files = list(DATA_DIR.glob('*.csv'))
    total_files = len(csv_files)

    for idx, file_path in enumerate(csv_files):
        if idx % 200 == 0:
            print(f"  加载进度: {idx}/{total_files} ({idx*100//total_files}%)")

        try:
            df = pd.read_csv(file_path)
            if df.empty:
                continue

            if '交易日' not in df.columns and 'date' not in df.columns:
                continue

            date_col = '交易日' if '交易日' in df.columns else 'date'

            df[date_col] = pd.to_numeric(df[date_col], errors='coerce')
            df = df[(df[date_col] >= start_int) & (df[date_col] <= end_int)]

            if df.empty:
                continue

            code_col = '股票代码' if '股票代码' in df.columns else 'code'
            name_col = '股票名称' if '股票名称' in df.columns else 'name'
            open_col = '开盘价' if '开盘价' in df.columns else 'open'
            high_col = '最高价' if '最高价' in df.columns else 'high'
            low_col = '最低价' if '最低价' in df.columns else 'low'
            close_col = '收盘价' if '收盘价' in df.columns else 'close'
            preclose_col = '前收盘价' if '前收盘价' in df.columns else 'preclose'
            gain_col = '涨跌幅（%）' if '涨跌幅（%）' in df.columns else 'pctChg'
            turnover_col = '换手率（%）' if '换手率（%）' in df.columns else 'turn'
            vr_col = '量比'
            cap_col = '流通市值（万元）'
            vol_col = '成交量（手）' if '成交量（手）' in df.columns else 'volume'

            for _, row in df.iterrows():
                try:
                    date_int = int(row[date_col])
                except (ValueError, TypeError):
                    continue

                code = str(row[code_col]).split('.')[0]

                code_data = {
                    'code': code,
                    'name': str(row.get(name_col, code)),
                    'open': _safe_float(row.get(open_col, 0)),
                    'high': _safe_float(row.get(high_col, 0)),
                    'low': _safe_float(row.get(low_col, 0)),
                    'close': _safe_float(row.get(close_col, 0)),
                    'preclose': _safe_float(row.get(preclose_col, 0)),
                    'gain': _safe_float(row.get(gain_col, 0)) / 100,
                    'turnover': _safe_float(row.get(turnover_col, 0)) / 100,
                    'volume_ratio': _safe_float(row.get(vr_col, 1.5), 1.5),
                    'market_cap': _safe_float(row.get(cap_col, 0)) / 10000,
                    'volume': _safe_float(row.get(vol_col, 0)),
                }

                if date_int not in date_stock_map:
                    date_stock_map[date_int] = {}
                date_stock_map[date_int][code] = code_data

        except (pd.errors.EmptyDataError, pd.errors.ParserError, IOError):
            continue

    print(f"  加载完成: {total_files} 个文件，{len(date_stock_map)} 个交易日")
    return date_stock_map


def _get_trading_days_from_data(date_stock_map, start_date, end_date):
    start_int = int(start_date)
    end_int = int(end_date)
    return sorted(d for d in date_stock_map.keys() if start_int <= d <= end_int)


def _get_next_trading_day(date_stock_map, current_date):
    all_dates = sorted(date_stock_map.keys())
    try:
        idx = all_dates.index(current_date)
        if idx + 1 < len(all_dates):
            return all_dates[idx + 1]
    except ValueError:
        pass
    return None


def _check_limit_up_from_index(row_data):
    gain = row_data['gain']
    close = row_data['close']
    preclose = row_data.get('preclose', close)
    if gain >= 0.095:
        return True
    if preclose > 0:
        expected_limit = round(preclose * 1.1, 2)
        if close >= expected_limit - 0.01:
            return True
    return False


def _check_volume_amplify_index(date_stock_map, code, current_date, days=3):
    all_dates = sorted(date_stock_map.keys())
    try:
        idx = all_dates.index(current_date)
    except ValueError:
        return False
    if idx < days:
        return False
    volumes = []
    for i in range(days, -1, -1):
        d = all_dates[idx - i]
        stock_map = date_stock_map.get(d, {})
        if code in stock_map:
            volumes.append(stock_map[code].get('volume', 0))
        else:
            return False
    for i in range(1, len(volumes)):
        if volumes[i] <= volumes[i - 1]:
            return False
    return True


def _check_intraday_strong_index(row_data):
    open_price = row_data['open']
    close_price = row_data['close']
    high_price = row_data['high']
    low_price = row_data['low']
    if open_price <= 0 or close_price <= 0:
        return False
    if close_price <= open_price:
        return False
    mid = (high_price + low_price) / 2
    if close_price < mid:
        return False
    return True


def _check_buy_point_index(row_data):
    close_price = row_data['close']
    high_price = row_data['high']
    low_price = row_data['low']
    if high_price <= 0 or low_price <= 0:
        return False
    intraday_range = high_price - low_price
    if intraday_range <= 0:
        return False
    position = (close_price - low_price) / intraday_range
    return position >= 0.7


def _check_st_name(name):
    if name is None:
        return False
    return 'ST' in str(name) or 'st' in str(name)


def _select_stocks_from_index(date_stock_map, date_int):
    """八步法从索引选股，返回 (selected_stocks, diagnostics)"""
    if date_int not in date_stock_map:
        return [], _make_empty_diag()

    stock_dict = date_stock_map[date_int]
    total = len(stock_dict)
    d = {
        'date': str(date_int),
        'total': total,
        'step1_before': total,
        'step1_after': 0,
        'step2_after': 0,
        'step3_after': 0,
        'step4_after': 0,
        'step5_after': 0,
        'step7_after': 0,
        'step8_after': 0,
        'st_filtered': 0,
        'limit_up_filtered': 0,
        'final': 0,
    }

    # 统计各步失败数量
    step_gain_fail = 0
    step_vr_fail = 0
    step_turnover_fail = 0
    step_cap_fail = 0
    step_amp_fail = 0
    step_strong_fail = 0
    step_buy_fail = 0

    selected = []

    for code, row_data in stock_dict.items():
        if _check_st_name(row_data['name']):
            d['st_filtered'] += 1
            continue

        gain = row_data['gain']
        if not (SELECTOR_CONFIG['gain_min'] <= gain <= SELECTOR_CONFIG['gain_max']):
            step_gain_fail += 1
            continue

        if row_data['volume_ratio'] < SELECTOR_CONFIG['volume_ratio_min']:
            step_vr_fail += 1
            continue

        turnover = row_data['turnover']
        if not (SELECTOR_CONFIG['turnover_min'] <= turnover <= SELECTOR_CONFIG['turnover_max']):
            step_turnover_fail += 1
            continue

        market_cap = row_data['market_cap']
        if not (SELECTOR_CONFIG['market_cap_min'] <= market_cap <= SELECTOR_CONFIG['market_cap_max']):
            step_cap_fail += 1
            continue

        if SELECTOR_CONFIG.get('filter_limit_up', True):
            if _check_limit_up_from_index(row_data):
                d['limit_up_filtered'] += 1
                continue

        amplify_days = SELECTOR_CONFIG.get('volume_amplify_days', 3)
        if not _check_volume_amplify_index(date_stock_map, code, date_int, amplify_days):
            step_amp_fail += 1
            continue

        if not _check_intraday_strong_index(row_data):
            step_strong_fail += 1
            continue

        if not _check_buy_point_index(row_data):
            step_buy_fail += 1
            continue

        selected.append({
            'code': code,
            'name': row_data['name'],
            'price': row_data['close'],
            'gain': gain,
            'turnover': turnover,
            'volume_ratio': row_data['volume_ratio'],
            'market_cap': market_cap,
        })

    # 反推各步通过量
    after_st = d['total'] - d['st_filtered']
    after_gain = after_st - step_gain_fail
    after_vr = after_gain - step_vr_fail
    after_turnover = after_vr - step_turnover_fail
    after_cap = after_turnover - step_cap_fail
    after_limit = after_cap - d['limit_up_filtered']
    after_amp = after_limit - step_amp_fail
    after_strong = after_amp - step_strong_fail
    after_buy = after_strong - step_buy_fail

    d['step1_after'] = after_gain
    d['step2_after'] = after_vr
    d['step3_after'] = after_turnover
    d['step4_after'] = after_cap
    d['step5_after'] = after_amp
    d['step7_after'] = after_strong
    d['step8_after'] = after_buy
    d['final'] = len(selected)

    return selected, d


def _make_empty_diag():
    return {
        'date': 'N/A', 'total': 0,
        'step1_after': 0, 'step2_after': 0, 'step3_after': 0,
        'step4_after': 0, 'step5_after': 0, 'step7_after': 0,
        'step8_after': 0, 'st_filtered': 0, 'limit_up_filtered': 0,
        'final': 0,
    }


def backtest(start_date, end_date, demo_mode=False):
    """杨永兴战法回测引擎"""
    print(f"开始回测: {start_date} -> {end_date}")
    if demo_mode:
        print("【Demo 模式】使用模拟数据")

    capital = BACKTEST_CONFIG['initial_capital']
    positions = []
    trades = []
    equity_curve = []
    all_diagnostics = []
    _dates_with_selection = 0
    _dates_total = 0

    if demo_mode:
        trading_days = _get_demo_trading_days(start_date, end_date)
        date_stock_map = {}
    else:
        print("正在预加载数据...")
        date_stock_map = _build_date_stock_index(start_date, end_date)
        total_dates = len(date_stock_map)
        print(f"已加载 {total_dates} 个交易日的数据")
        trading_days = _get_trading_days_from_data(date_stock_map, start_date, end_date)
        print(f"回测范围: {len(trading_days)} 个交易日")

    for i, day in enumerate(trading_days):
        if i % 20 == 0:
            print(f"处理进度: {i}/{len(trading_days)} ({i*100//len(trading_days)}%)")

        day_str = str(day)

        if positions:
            if demo_mode:
                capital, trades = _sell_positions_demo(positions, day_str, capital, trades)
            else:
                capital, trades = _sell_positions_strategy(
                    positions, day, capital, trades, date_stock_map
                )
            positions = []

        if demo_mode:
            selected = _select_stocks_demo(day_str)
            diag = _make_empty_diag()
        else:
            selected, diag = _select_stocks_from_index(date_stock_map, day)

        _dates_total += 1
        if selected:
            _dates_with_selection += 1
            positions, capital = _buy_stocks(selected, capital)

        all_diagnostics.append(diag)

        total_value = capital + sum(p['value'] for p in positions)
        equity_curve.append({
            'date': day_str,
            'capital': capital,
            'position_value': sum(p['value'] for p in positions),
            'total': total_value
        })

    d_summary = _build_diag_summary(all_diagnostics, _dates_total, _dates_with_selection)
    report = _generate_report(trades, equity_curve, BACKTEST_CONFIG['initial_capital'])
    report['diagnostics'] = d_summary
    report['daily_diagnostics'] = all_diagnostics
    return report


def _build_diag_summary(all_diagnostics, dates_total, dates_with_selection):
    """汇总所有天的诊断数据，找出瓶颈步骤"""
    if not all_diagnostics:
        return {}

    # 汇总每步平均通过量
    keys = ['total', 'step1_after', 'step2_after', 'step3_after',
            'step4_after', 'step5_after', 'step7_after', 'step8_after',
            'st_filtered', 'limit_up_filtered', 'final']
    sums = {k: 0 for k in keys}
    for d in all_diagnostics:
        for k in keys:
            sums[k] += d.get(k, 0)

    n = max(dates_total, 1)
    avg = {k: sums[k] / n for k in keys}

    # 计算每步的淘汰率
    steps = [
        ('排除ST', 'total', 'step1_after'),
        ('涨幅3%-5%', 'step1_after', 'step2_after'),
        ('量比≥1', 'step2_after', 'step3_after'),
        ('换手率5%-10%', 'step3_after', 'step4_after'),
        ('市值50-200亿', 'step4_after', 'step5_after'),
        ('成交量持续放大', 'step5_after', 'step7_after'),
        ('分时强势', 'step7_after', 'step8_after'),
        ('买入点确认', 'step8_after', 'final'),
    ]

    bottlenecks = []
    for name, key_before, key_after in steps:
        before_val = avg.get(key_before, 0)
        after_val = avg.get(key_after, 0)
        eliminated = before_val - after_val
        rate = (eliminated / before_val * 100) if before_val > 0 else 0
        bottlenecks.append({
            'step': name,
            'before': round(before_val, 1),
            'after': round(after_val, 1),
            'eliminated': round(eliminated, 1),
            'eliminate_rate': round(rate, 1),
        })

    return {
        'avg_stocks_per_day': round(avg.get('total', 0), 1),
        'avg_pass_step1': round(avg.get('step1_after', 0), 1),
        'avg_pass_step4': round(avg.get('step4_after', 0), 1),
        'avg_pass_step5': round(avg.get('step5_after', 0), 1),
        'avg_pass_step7': round(avg.get('step7_after', 0), 1),
        'avg_pass_step8': round(avg.get('step8_after', 0), 1),
        'avg_final': round(avg.get('final', 0), 1),
        'dates_total': dates_total,
        'dates_with_selection': dates_with_selection,
        'bottlenecks': bottlenecks,
    }


def _get_demo_trading_days(start_date, end_date):
    start = datetime.strptime(start_date, '%Y%m%d')
    end = datetime.strptime(end_date, '%Y%m%d')
    days = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            days.append(int(current.strftime('%Y%m%d')))
        current += timedelta(days=1)
    return days


def _select_stocks_demo(date):
    import random
    random.seed(int(date))
    if random.random() < 0.3:
        num_stocks = random.randint(1, 3)
        stocks = []
        for i in range(num_stocks):
            stocks.append({
                'code': f'60{random.randint(1000, 9999)}',
                'name': f'模拟股票{i+1}',
                'price': random.uniform(10, 50),
                'gain': random.uniform(0.03, 0.05),
                'turnover': random.uniform(0.05, 0.10),
                'volume_ratio': random.uniform(1, 3),
                'market_cap': random.uniform(50, 200),
            })
        return stocks
    return []


def _buy_stocks(selected, capital):
    positions = []
    max_stocks = int(RISK_CONFIG['max_total_position'] / RISK_CONFIG['max_position_per_stock'])
    stocks_to_buy = selected[:max_stocks]

    for stock in stocks_to_buy:
        position_size = capital * RISK_CONFIG['max_position_per_stock']
        shares = int(position_size / stock['price'] / 100) * 100

        if shares > 0:
            cost = shares * stock['price']
            capital -= cost
            positions.append({
                'code': stock['code'],
                'name': stock['name'],
                'buy_price': stock['price'],
                'shares': shares,
                'value': cost
            })

    return positions, capital


def _sell_positions_demo(positions, date, capital, trades):
    import random
    random.seed(int(date))
    for pos in positions:
        if random.random() < 0.7:
            gain_pct = random.uniform(0.005, 0.03)
        else:
            gain_pct = random.uniform(-0.025, -0.005)
        sell_price = pos['buy_price'] * (1 + gain_pct)
        revenue = pos['shares'] * sell_price
        capital += revenue
        gain = (sell_price - pos['buy_price']) / pos['buy_price']
        trades.append({
            'code': pos['code'],
            'name': pos['name'],
            'buy_price': pos['buy_price'],
            'sell_price': sell_price,
            'shares': pos['shares'],
            'gain': gain,
            'profit': revenue - pos['value'],
            'date': date
        })
    return capital, trades


def _sell_positions_strategy(positions, date, capital, trades, date_stock_map):
    next_date = _get_next_trading_day(date_stock_map, date)
    for pos in positions:
        sell_price = pos['buy_price']
        if next_date and pos['code'] in date_stock_map.get(next_date, {}):
            next_open = date_stock_map[next_date][pos['code']]['open']
            if next_open > 0:
                sell_price = next_open
        revenue = pos['shares'] * sell_price
        capital += revenue
        gain = (sell_price - pos['buy_price']) / pos['buy_price']
        trades.append({
            'code': pos['code'],
            'name': pos['name'],
            'buy_price': pos['buy_price'],
            'sell_price': sell_price,
            'shares': pos['shares'],
            'gain': gain,
            'profit': revenue - pos['value'],
            'date': str(date)
        })
    return capital, trades


def _generate_report(trades, equity_curve, initial_capital):
    if not trades:
        return {
            'total_trades': 0,
            'win_rate': 0,
            'avg_return': 0,
            'total_return': 0,
            'max_drawdown': 0,
            'final_capital': initial_capital
        }

    df_trades = pd.DataFrame(trades)
    df_equity = pd.DataFrame(equity_curve)

    total_trades = len(trades)
    win_trades = len(df_trades[df_trades['gain'] > 0])
    win_rate = win_trades / total_trades if total_trades > 0 else 0
    avg_return = df_trades['gain'].mean()

    final_capital = df_equity['total'].iloc[-1]
    total_return = (final_capital - initial_capital) / initial_capital

    df_equity['peak'] = df_equity['total'].cummax()
    df_equity['drawdown'] = (df_equity['total'] - df_equity['peak']) / df_equity['peak']
    max_drawdown = df_equity['drawdown'].min()

    return {
        'total_trades': total_trades,
        'win_rate': win_rate,
        'avg_return': avg_return,
        'total_return': total_return,
        'max_drawdown': max_drawdown,
        'final_capital': final_capital,
        'trades': trades,
        'equity_curve': equity_curve
    }


def print_report(report):
    print("\n" + "=" * 60)
    print("回测报告")
    print("=" * 60)
    print(f"总交易次数: {report['total_trades']}")
    print(f"胜率: {report['win_rate']*100:.2f}%")
    print(f"平均收益率: {report['avg_return']*100:.2f}%")
    print(f"总收益率: {report['total_return']*100:.2f}%")
    print(f"最大回撤: {report['max_drawdown']*100:.2f}%")
    print(f"最终资金: {report['final_capital']:.2f}")
    print("=" * 60)

    _print_diagnostics(report.get('diagnostics', {}))


def _print_diagnostics(diag):
    if not diag:
        return
    print("\n" + "=" * 60)
    print("选股诊断分析")
    print("=" * 60)
    print(f"回测交易日数: {diag.get('dates_total', 0)}")
    print(f"有选股结果的交易日: {diag.get('dates_with_selection', 0)}")
    print(f"每日平均股票总数: {diag.get('avg_stocks_per_day', 0)} 只")
    print()
    print("八步法逐级筛选（日均通过量）：")
    print(f"  {'┌初始全量':>20}  {diag.get('avg_stocks_per_day', 0):>8.0f} 只")
    print(f"  {'├① 涨幅3%-5%':>20}  {diag.get('avg_pass_step1', 0):>8.1f} 只")
    print(f"  {'├② 量比≥1':>20}  {diag.get('avg_pass_step1', 0):>8} → {diag.get('avg_pass_step1', 0):>8}")
    print(f"  {'├③ 换手率5%-10%':>20}  ---")
    print(f"  {'├④ 市值50-200亿':>20}  {diag.get('avg_pass_step4', 0):>8.1f} 只")
    print(f"  {'├⑤ 成交量持续放大':>20}  {diag.get('avg_pass_step5', 0):>8.1f} 只")
    print(f"  {'├⑦ 分时强势':>20}  {diag.get('avg_pass_step7', 0):>8.1f} 只")
    print(f"  {'└⑧ 买入点确认':>20}  {diag.get('avg_pass_step8', 0):>8.1f} 只")
    print()

    bottlenecks = diag.get('bottlenecks', [])
    if bottlenecks:
        print("各步淘汰率:")
        max_rate = max(b['eliminate_rate'] for b in bottlenecks) if bottlenecks else 0
        for b in bottlenecks:
            bar = '█' * int(b['eliminate_rate'] / 5) + '░' * (20 - int(b['eliminate_rate'] / 5))
            flag = ' ← 最大瓶颈' if b['eliminate_rate'] == max_rate and b['eliminate_rate'] > 30 else ''
            print(f"  {b['step']:<16} {bar} {b['eliminate_rate']:>5.1f}% "
                  f"({b['before']:.0f} → {b['after']:.0f}){flag}")
    print("=" * 60)
