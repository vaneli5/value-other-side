#!/usr/bin/env python3
"""
价值另一面 - A股低估筛选器

Usage:
    python screen.py                    # 运行筛选
    python screen.py --limit 20         # 筛选20只
    python screen.py --save             # 保存到GitHub
    python screen.py --help             # 查看帮助

Examples:
    python screen.py -l 10 -s           # 筛选10只并保存
"""

import argparse
import datetime
import os
import sys
from pathlib import Path

try:
    import pandas as pd
    import tushare as ts
except ImportError:
    print("Error: Missing dependencies. Run: pip install tushare pandas")
    sys.exit(1)

# 配置
DEFAULT_TOKEN = ''  # 默认空，需要通过参数传入
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')

# GitHub配置
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')
REPO_OWNER = 'vaneli5'
REPO_NAME = 'agent-memo'
BRANCH = 'main'


def get_token(token=None):
    """获取tushare token: 参数 > 环境变量 > ~/.aj-skills/.env"""
    if token:
        return token
    
    # 优先读取环境变量
    token = os.environ.get('TUSHARE_TOKEN')
    if token:
        return token
    
    # 读取 ~/.aj-skills/.env
    env_file = Path.home() / ".aj-skills" / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith('TUSHARE_TOKEN='):
                return line.split('=', 1)[1].strip()
    
    return ''


def fetch_data(token):
    """获取今日行情数据"""
    ts.set_token(token)
    pro = ts.pro_api(token)
    
    # 获取最近交易日
    today = datetime.datetime.now()
    start_date = (today - datetime.timedelta(days=10)).strftime('%Y%m%d')
    cal_df = pro.trade_cal(exchange='SSE', start_date=start_date, end_date=today.strftime('%Y%m%d'))
    cal_df = cal_df[cal_df['is_open'] == 1].sort_values('cal_date')
    if len(cal_df) > 0:
        trade_date = cal_df.iloc[-1]['cal_date']
    else:
        # 如果没有开市日，回退到获取所有历史交易日
        cal_df = pro.trade_cal(exchange='SSE', start_date='20250101', end_date=today.strftime('%Y%m%d'))
        cal_df = cal_df[cal_df['is_open'] == 1].sort_values('cal_date')
        trade_date = cal_df.iloc[-1]['cal_date']
    print(f"  使用交易日: {trade_date}")
    
    # 直接获取所有股票的daily_basic
    df = pro.daily_basic(
        trade_date=trade_date,
        fields='ts_code,close,pe_ttm,pb,dv_ratio,turnover_rate'
    )
    
    # 获取股票名称、行业、上市日期
    stocks = pro.stock_basic(
        exchange='', 
        list_status='L', 
        fields='ts_code,name,industry,list_date'
    )
    
    # 合并名称和行业
    df = df.merge(stocks[['ts_code', 'name', 'industry', 'list_date']], on='ts_code', how='left')
    
    # 过滤ST和北交所、科创板
    df = df[~df['name'].str.contains('ST|退', na=False)]
    df = df[~df['ts_code'].str.endswith(('.BJ', '.KCB'))]
    
    return df


def filter_stocks(df, pe_max=15, pb_max=2, turnover_min=0.5, 
                   no_bank=False, no_broker=False, no_insurance=False, 
                   no_real_estate=False, no_new=False):
    """筛选低估股票"""
    if df is None or len(df) == 0:
        return pd.DataFrame()
    
    # 排除银行
    if no_bank:
        df = df[~df['industry'].str.contains('银行', na=False)]
    
    # 排除券商
    if no_broker:
        df = df[~df['industry'].str.contains('证券|券商', na=False)]
    
    # 排除保险
    if no_insurance:
        df = df[~df['industry'].str.contains('保险', na=False)]
    
    # 排除地产
    if no_real_estate:
        df = df[~df['industry'].str.contains('房地产|地产', na=False)]
    
    # 排除次新股
    if no_new:
        one_year_ago = (datetime.datetime.now() - datetime.timedelta(days=365)).strftime('%Y%m%d')
        df = df[df['list_date'] < one_year_ago]
    
    # 筛选条件
    result = df[
        (df['pe_ttm'] > 0) & (df['pe_ttm'] < pe_max) &
        (df['pb'] > 0) & (df['pb'] < pb_max) &
        (df['turnover_rate'] > turnover_min)
    ].copy()
    
    # 按PE排序
    result = result.sort_values('pe_ttm')
    
    return result


def save_to_github(df, subdir='value-other-side'):
    """保存结果到GitHub"""
    import requests
    from base64 import b64encode
    
    if not GITHUB_TOKEN:
        print("Warning: GITHUB_TOKEN not set, skipping save")
        return False
    
    date_str = datetime.datetime.now().strftime('%Y-%m-%d')
    content = df.to_csv(index=False, encoding='utf-8-sig')
    
    filename = f'low_valuation_{date_str}.csv'
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{subdir}/data/{filename}"
    
    # 检查文件是否存在
    response = requests.get(url, headers={'Authorization': f'token {GITHUB_TOKEN}'})
    sha = response.json().get('sha') if response.status_code == 200 else None
    
    # 上传文件
    data = {
        'message': f'update: {date_str} 低估股票筛选结果',
        'content': b64encode(content.encode('utf-8')).decode('utf-8'),
        'branch': BRANCH
    }
    if sha:
        data['sha'] = sha
    
    response = requests.put(url, json=data, headers={'Authorization': f'token {GITHUB_TOKEN}'})
    
    if response.status_code in [200, 201]:
        print(f"✓ 已保存到 GitHub: {subdir}/data/{filename}")
        return True
    else:
        print(f"✗ 保存失败: {response.text}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description='价值另一面 - A股低估筛选器',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('-l', '--limit', type=int, default=30, 
                        help='筛选数量 (default: 30)')
    parser.add_argument('--pe', type=float, default=15,
                        help='PE最大值 (default: 15)')
    parser.add_argument('--pb', type=float, default=2,
                        help='PB最大值 (default: 2)')
    parser.add_argument('--turnover', type=float, default=0.5,
                        help='最小换手率%% (default: 0.5)')
    parser.add_argument('-t', '--token', type=str, 
                        help='Tushare token (或设置环境变量 TUSHARE_TOKEN)')
    parser.add_argument('-s', '--save', action='store_true',
                        help='保存结果到GitHub')
    parser.add_argument('--no-bank', action='store_true', default=True,
                        help='排除银行股 (默认开启)')
    parser.add_argument('--no-broker', action='store_true', default=True,
                        help='排除券商股 (默认开启)')
    parser.add_argument('--no-insurance', action='store_true', default=True,
                        help='排除保险股 (默认开启)')
    parser.add_argument('--no-real-estate', action='store_true', default=True,
                        help='排除地产股 (默认开启)')
    parser.add_argument('--no-new', action='store_true', default=True,
                        help='排除次新股 (默认开启)')
    parser.add_argument('--include-all', action='store_true',
                        help='不过滤，包含所有股票')
    
    args = parser.parse_args()
    
    # 优先用参数，其次从环境变量/配置文件读取
    token = args.token if args.token else get_token()
    
    if not token:
        print("Error: 请传入 Tushare token")
        print("  - 通过参数: python screen.py -t YOUR_TOKEN")
        print("  - 或设置环境变量: export TUSHARE_TOKEN=YOUR_TOKEN")
        print("  - 或配置在 ~/.aj-skills/.env")
        sys.exit(1)
    
    print("=" * 50)
    print("价值另一面 - A股低估筛选器")
    print(f"筛选条件: PE<{args.pe}, PB<{args.pb}, 换手>{args.turnover}%")
    print("=" * 50)
    
    # 获取数据
    print("\n[1/2] 获取行情数据...")
    df = fetch_data(token)
    if df is None or len(df) == 0:
        print("✗ 获取数据失败")
        sys.exit(1)
    print(f"  获取到 {len(df)} 只股票")
    
    # 筛选
    print("\n[2/2] 筛选低估股票...")
    
    # 默认排除银行/券商/保险/地产/次新股
    if not args.include_all:
        result = filter_stocks(
            df, 
            pe_max=args.pe, 
            pb_max=args.pb,
            turnover_min=args.turnover,
            no_bank=True,
            no_broker=True,
            no_insurance=True,
            no_real_estate=True,
            no_new=True
        )
    else:
        result = filter_stocks(
            df, 
            pe_max=args.pe, 
            pb_max=args.pb,
            turnover_min=args.turnover
        )
    
    result = result.head(args.limit)
    print(f"  筛选出 {len(result)} 只")
    
    # 展示结果
    print("\n" + "=" * 50)
    print(f"低估股票TOP{len(result)}:")
    print("=" * 50)
    
    display_cols = ['code', 'name', 'close', 'pe', 'pb', 'turnoverratiof']
    display_cols = [c for c in display_cols if c in result.columns]
    
    for i, row in result.iterrows():
        print(f"{row.get('ts_code', ''):6} {row.get('name', ''):8} "
              f"现价:{row.get('close', 0):6.2f} "
              f"PE:{row.get('pe_ttm', 0):6.1f} "
              f"PB:{row.get('pb', 0):4.2f} "
              f"换手:{row.get('turnover_rate', 0):5.1f}%")
    
    # 保存
    if args.save:
        save_to_github(result)
    
    print(f"\n完成! 共 {len(result)} 只")


if __name__ == '__main__':
    main()
