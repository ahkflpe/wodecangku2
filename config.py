# -*- coding: utf-8 -*-
"""配置文件（支持 JSON 持久化，兼容 PyInstaller 打包）"""

import json
import os
import sys
import shutil
from pathlib import Path


def _get_base_dir():
    if getattr(sys, 'frozen', False):
        return Path(os.path.dirname(sys.executable))
    return Path(__file__).parent


# 启动时自动清除所有 __pycache__ 目录
def _auto_clear_cache():
    base = _get_base_dir()
    for cache_dir in base.rglob('__pycache__'):
        try:
            shutil.rmtree(cache_dir, ignore_errors=True)
        except Exception:
            pass

_auto_clear_cache()


CONFIG_FILE = _get_base_dir() / 'config.json'

EMAIL_CONFIG = {
    'smtp_server': 'smtp.qq.com',
    'smtp_port': 465,
    'sender': 'your_email@qq.com',
    'password': 'your_auth_code',
    'receiver': 'your_email@qq.com'
}

# 选股参数 —— 杨永兴八步法标准值
SELECTOR_CONFIG = {
    'gain_min': 0.03,
    'gain_max': 0.05,
    'volume_ratio_min': 1,
    'turnover_min': 0.05,
    'turnover_max': 0.10,
    'market_cap_min': 50,
    'market_cap_max': 200,
    'volume_amplify_days': 3,
    'filter_limit_up': True,
}

RISK_CONFIG = {
    'index_drop_limit': -0.01,
    'stop_loss': -0.02,
    'stop_profit': 0.02,
    'max_position_per_stock': 0.10,
    'max_total_position': 0.50,
}

BACKTEST_CONFIG = {
    'start_date': '20250421',
    'end_date': '20251231',
    'initial_capital': 100000,
}


def load_config():
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                saved = json.load(f)
            for key in SELECTOR_CONFIG:
                if key in saved:
                    SELECTOR_CONFIG[key] = saved[key]
            if 'start_date' in saved:
                BACKTEST_CONFIG['start_date'] = saved['start_date']
            if 'end_date' in saved:
                BACKTEST_CONFIG['end_date'] = saved['end_date']
        except (json.JSONDecodeError, IOError):
            pass


def save_config():
    data = dict(SELECTOR_CONFIG)
    data['start_date'] = BACKTEST_CONFIG['start_date']
    data['end_date'] = BACKTEST_CONFIG['end_date']
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


load_config()
