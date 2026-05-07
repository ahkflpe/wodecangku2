# -*- coding: utf-8 -*-
"""选股引擎（杨永兴八步法完整版）"""

import pandas as pd
from data_fetcher import (
    get_realtime_quotes, get_kline_data, get_minute_data,
    get_index_data, check_st_stock, check_suspended,
    check_limit_up, check_volume_amplify_local,
    check_intraday_strong_proxy, check_buy_point_proxy,
)
from config import SELECTOR_CONFIG, RISK_CONFIG


def select_stocks():
    """杨永兴八步法选股"""
    index_gain = get_index_data()
    if index_gain < RISK_CONFIG['index_drop_limit']:
        print(f"大盘跌幅 {index_gain*100:.2f}% 超过限制(-1%)，暂停选股")
        return []

    df = get_realtime_quotes()
    if df.empty:
        print("未获取到行情数据")
        return []

    print(f"原始股票数量: {len(df)}")

    # 第一步：涨幅 3%-5%
    df = _step1_gain_filter(df)
    if df.empty:
        print("第一步涨幅筛选后无结果"); return []

    # 第二步：量比 >= 1
    df = _step2_volume_ratio_filter(df)
    if df.empty:
        print("第二步量比筛选后无结果"); return []

    # 第三步：换手率 5%-10%
    df = _step3_turnover_filter(df)
    if df.empty:
        print("第三步换手率筛选后无结果"); return []

    # 第四步：流通市值 50亿-200亿
    df = _step4_market_cap_filter(df)
    if df.empty:
        print("第四步市值筛选后无结果"); return []

    # 第五步：过滤一字板
    if SELECTOR_CONFIG.get('filter_limit_up', True):
        df = _step5_filter_limit_up(df)

    selected = []
    for _, row in df.iterrows():
        code = row['code']
        name = row['name']

        # 风控：排除 ST
        if check_st_stock(name):
            continue

        # 风控：排除停牌
        if check_suspended(code):
            continue

        # 第五步：成交量持续放大
        if not _step5_volume_amplify(code):
            continue

        # 第六步：K线形态 —— 均线多头 + K线在均线上方
        if not _step6_kline_check(code):
            continue

        # 第七步：分时强势
        if not _step7_intraday_strong(row):
            continue

        # 第八步：买入点确认
        if not _step8_buy_point(row):
            continue

        selected.append({
            'code': code,
            'name': name,
            'price': row['price'],
            'gain': row['gain'],
            'turnover': row['turnover'],
            'volume_ratio': row['volume_ratio'],
            'market_cap': row['market_cap'],
        })

    print(f"最终筛选结果: {len(selected)} 只")
    return selected


def _step1_gain_filter(df):
    result = df[(df['gain'] >= SELECTOR_CONFIG['gain_min']) &
                (df['gain'] <= SELECTOR_CONFIG['gain_max'])]
    print(f"第一步-涨幅 3%-5%: {len(df)} -> {len(result)}")
    return result


def _step2_volume_ratio_filter(df):
    result = df[df['volume_ratio'] >= SELECTOR_CONFIG['volume_ratio_min']]
    print(f"第二步-量比 ≥1: {len(df)} -> {len(result)}")
    return result


def _step3_turnover_filter(df):
    result = df[(df['turnover'] >= SELECTOR_CONFIG['turnover_min']) &
                (df['turnover'] <= SELECTOR_CONFIG['turnover_max'])]
    print(f"第三步-换手率 5%-10%: {len(df)} -> {len(result)}")
    return result


def _step4_market_cap_filter(df):
    result = df[(df['market_cap'] >= SELECTOR_CONFIG['market_cap_min']) &
                (df['market_cap'] <= SELECTOR_CONFIG['market_cap_max'])]
    print(f"第四步-市值 50亿-200亿: {len(df)} -> {len(result)}")
    return result


def _step5_filter_limit_up(df):
    before = len(df)
    mask = df.apply(
        lambda r: not check_limit_up(r['gain'], r['price'], r.get('preclose', r['price'])),
        axis=1
    )
    result = df[mask]
    print(f"第五步-排除涨停: {before} -> {len(result)}")
    return result


def _step5_volume_amplify(code):
    days = SELECTOR_CONFIG.get('volume_amplify_days', 3)
    result = check_volume_amplify_local(code, days)
    return result


def _step6_kline_check(code):
    """第六步：均线多头 + K线在均线上方"""
    try:
        df = get_kline_data(code)
        if df.empty or len(df) < 60:
            return False

        df = df.sort_values('交易日', ascending=True).reset_index(drop=True)

        df['ma5'] = df['收盘'].rolling(5).mean()
        df['ma10'] = df['收盘'].rolling(10).mean()
        df['ma20'] = df['收盘'].rolling(20).mean()
        df['ma60'] = df['收盘'].rolling(60).mean()

        last = df.iloc[-1]

        if not (last['ma5'] > last['ma10'] > last['ma20'] > last['ma60']):
            return False

        if last['收盘'] < last['ma5']:
            return False

        return True
    except (KeyError, ValueError, TypeError):
        return False


def _step7_intraday_strong(row):
    """第七步：分时强势"""
    open_price = row.get('open', 0)
    close_price = row.get('price', 0)
    high_price = row.get('high', 0)
    low_price = row.get('low', 0)
    return check_intraday_strong_proxy(open_price, close_price, high_price, low_price)


def _step8_buy_point(row):
    """第八步：买入点确认"""
    close_price = row.get('price', 0)
    high_price = row.get('high', 0)
    low_price = row.get('low', 0)
    return check_buy_point_proxy(close_price, high_price, low_price)
