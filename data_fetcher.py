# -*- coding: utf-8 -*-
"""数据获取模块（优先使用本地数据，兼容多格式CSV）"""

import pandas as pd
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta


def _get_base_dir():
    if getattr(sys, 'frozen', False):
        return Path(os.path.dirname(sys.executable))
    return Path(__file__).parent


DATA_DIR = _get_base_dir() / 'data'

COL_MAP = {
    'date': '交易日',
    'code': '股票代码',
    'open': '开盘价',
    'high': '最高价',
    'low': '最低价',
    'close': '收盘价',
    'volume': '成交量（手）',
    'amount': '成交额（千元）',
    'turn': '换手率（%）',
    'pctChg': '涨跌幅（%）',
}

_COL_ALIASES = {
    '股票代码': ['股票代码', 'code'],
    '股票名称': ['股票名称', 'name'],
    '交易日': ['交易日', 'date'],
    '开盘价': ['开盘价', 'open'],
    '最高价': ['最高价', 'high'],
    '最低价': ['最低价', 'low'],
    '收盘价': ['收盘价', 'close'],
    '前收盘价': ['前收盘价', 'preclose'],
    '涨跌额': ['涨跌额', 'change'],
    '涨跌幅（%）': ['涨跌幅（%）', 'pctChg'],
    '成交量（手）': ['成交量（手）', 'volume'],
    '成交额（千元）': ['成交额（千元）', 'amount'],
    '换手率（%）': ['换手率（%）', 'turn'],
    '量比': ['量比'],
    '流通市值（万元）': ['流通市值（万元）'],
}


def _resolve_col(df, target):
    for alias in _COL_ALIASES.get(target, [target]):
        if alias in df.columns:
            return alias
    return None


def _safe_float(val, default=0.0):
    if pd.isna(val):
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def get_local_stock_data(code, start_date=None, end_date=None):
    possible_files = [
        DATA_DIR / f"{code}.SH.csv",
        DATA_DIR / f"{code}.SZ.csv",
        DATA_DIR / f"{code}.csv",
    ]

    df = pd.DataFrame()
    for file_path in possible_files:
        if file_path.exists():
            try:
                df = pd.read_csv(file_path)
                break
            except (pd.errors.EmptyDataError, pd.errors.ParserError, IOError):
                continue

    if df.empty:
        return pd.DataFrame()

    date_col = _resolve_col(df, '交易日')
    if date_col is None:
        return df

    if start_date:
        try:
            start_val = int(start_date.replace('-', '')) if isinstance(start_date, str) else start_date
            df = df[df[date_col].astype(int) >= start_val]
        except (ValueError, TypeError):
            pass
    if end_date:
        try:
            end_val = int(end_date.replace('-', '')) if isinstance(end_date, str) else end_date
            df = df[df[date_col].astype(int) <= end_val]
        except (ValueError, TypeError):
            pass

    return df


def get_realtime_quotes():
    if not DATA_DIR.exists():
        print("本地数据目录不存在，请先运行 download_data.py 下载数据")
        return pd.DataFrame()

    data = []
    csv_files = list(DATA_DIR.glob('*.csv'))

    print(f"从本地读取 {len(csv_files)} 只股票数据...")

    for i, file_path in enumerate(csv_files):
        try:
            df = pd.read_csv(file_path)
            if df.empty:
                continue

            row = df.iloc[0]

            code_col = _resolve_col(df, '股票代码')
            code = str(row[code_col]).split('.')[0] if code_col else file_path.stem

            name_col = _resolve_col(df, '股票名称')
            name = row[name_col] if name_col else code

            open_col = _resolve_col(df, '开盘价')
            open_price = _safe_float(row[open_col]) if open_col else 0

            high_col = _resolve_col(df, '最高价')
            high_price = _safe_float(row[high_col]) if high_col else 0

            low_col = _resolve_col(df, '最低价')
            low_price = _safe_float(row[low_col]) if low_col else 0

            close_col = _resolve_col(df, '收盘价')
            close_price = _safe_float(row[close_col]) if close_col else 0

            preclose_col = _resolve_col(df, '前收盘价')
            preclose = _safe_float(row[preclose_col]) if preclose_col else close_price

            gain_col = _resolve_col(df, '涨跌幅（%）')
            gain_raw = _safe_float(row[gain_col], 0) if gain_col else 0
            gain = gain_raw / 100

            turnover_col = _resolve_col(df, '换手率（%）')
            turnover_raw = _safe_float(row[turnover_col], 0) if turnover_col else 0
            turnover = turnover_raw / 100

            cap_col = _resolve_col(df, '流通市值（万元）')
            market_cap = _safe_float(row[cap_col], 0) / 10000 if cap_col else 0

            vol_ratio = 1.5
            vr_col = _resolve_col(df, '量比')
            if vr_col:
                vol_ratio = _safe_float(row[vr_col], 1.5)

            vol_col = _resolve_col(df, '成交量（手）')
            volume = _safe_float(row[vol_col], 0) if vol_col else 0

            data.append({
                'code': code,
                'name': name,
                'price': close_price,
                'open': open_price,
                'high': high_price,
                'low': low_price,
                'preclose': preclose,
                'gain': gain,
                'turnover': turnover,
                'volume_ratio': vol_ratio,
                'market_cap': market_cap,
                'volume': volume,
            })

        except (pd.errors.EmptyDataError, pd.errors.ParserError, IOError, KeyError):
            continue

        if (i + 1) % 500 == 0:
            print(f"已处理 {i+1}/{len(csv_files)}")

    print(f"成功读取 {len(data)} 只股票")
    return pd.DataFrame(data)


def get_kline_data(symbol, period='daily', adjust='qfq'):
    df = get_local_stock_data(symbol)

    if not df.empty:
        close_col = _resolve_col(df, '收盘价')
        if close_col:
            df['收盘'] = pd.to_numeric(df[close_col], errors='coerce')

    return df


def get_minute_data(symbol, period='1'):
    return pd.DataFrame()


def get_index_data():
    for suffix in ['.SH', '.SZ', '']:
        file_path = DATA_DIR / f"000001{suffix}.csv"
        if file_path.exists():
            try:
                df = pd.read_csv(file_path)
                if not df.empty:
                    gain_col = _resolve_col(df, '涨跌幅（%）')
                    if gain_col:
                        return _safe_float(df.iloc[0][gain_col], 0) / 100
            except (pd.errors.EmptyDataError, pd.errors.ParserError, IOError, KeyError):
                continue
    return 0


def check_st_stock(name):
    if name is None:
        return False
    return 'ST' in str(name) or 'st' in str(name)


def check_suspended(symbol):
    return False


def check_limit_up(gain, close, preclose):
    """检查是否涨停（含一字板）"""
    if gain >= 0.095:
        return True
    if preclose > 0:
        expected_limit = round(preclose * 1.1, 2)
        if close >= expected_limit - 0.01:
            return True
    return False


def get_stock_volume_trend(code, lookback_days=5):
    """获取最近 N 天的成交量序列（从最新到最旧），升序返回（旧→新）"""
    df = get_local_stock_data(code)
    if df.empty:
        return []

    date_col = '交易日' if '交易日' in df.columns else 'date'
    vol_col = '成交量（手）' if '成交量（手）' in df.columns else 'volume'

    if date_col not in df.columns or vol_col not in df.columns:
        return []

    df = df.sort_values(date_col, ascending=True)
    df = df.tail(lookback_days + 1)

    volumes = pd.to_numeric(df[vol_col], errors='coerce').tolist()
    return [v for v in volumes if not pd.isna(v)]


def check_volume_amplify_local(code, days=3):
    """检查本地数据中最近 N 天成交量是否持续放大"""
    volumes = get_stock_volume_trend(code, days + 1)
    if len(volumes) < days + 1:
        return False
    recent = volumes[-(days + 1):]
    for i in range(1, len(recent)):
        if recent[i] <= recent[i-1]:
            return False
    return True


def check_intraday_strong_proxy(open_price, close_price, high_price, low_price):
    """分时强势代理判断：收盘 > 开盘 且 收盘在当日上半区间"""
    if open_price <= 0 or close_price <= 0:
        return False
    if close_price <= open_price:
        return False
    mid = (high_price + low_price) / 2
    if close_price < mid:
        return False
    return True


def check_buy_point_proxy(close_price, high_price, low_price):
    """买入点代理判断：收盘价接近日内最高价"""
    if high_price <= 0 or low_price <= 0:
        return False
    intraday_range = high_price - low_price
    if intraday_range <= 0:
        return False
    position = (close_price - low_price) / intraday_range
    return position >= 0.7
