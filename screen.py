#!/usr/bin/env python3
"""
价值另一面 - A股低估筛选器
每天自动运行，筛选低估股票，结果保存到 GitHub
"""

import os
import datetime
import pandas as pd
import tushare as ts

# 配置
TOKEN = os.environ.get('TUSHARE_TOKEN', 'your_token_here')
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', 'ghp_your_token_here')
REPO_OWNER = 'vaneli5'
REPO_NAME = 'agent-memo'
BRANCH = 'main'

# 筛选条件
FILTER_CONDITIONS = {
    'pe_ttm': (0, 15),          # 市盈率 0-15
    'pb': (0, 2),                # 市净率 0-2
    'dv_ratio': (2, None),       # 股息率 > 2%
    'roe': (10, None),           # ROE > 10%
}

def get_token():
    """获取tushare token"""
    if TOKEN != 'your_token_here':
        return TOKEN
    
    # 尝试从文件读取
    token_file = os.path.expanduser('~/.tushare_token')
    if os.path.exists(token_file):
        with open(token_file) as f:
            return f.read().strip()
    return None

def fetch_stock_data():
    """获取股票数据"""
    pro = ts.pro_api(get_token())
    
    # 获取全部A股
    df = pro.stock_basic(
        exchange='', 
        list_status='L', 
        fields='ts_code,symbol,name,industry,list_date'
    )
    
    # 过滤科创板、北交所
    df = df[~df['ts_code'].str.endswith(('.BJ', '.KCB'))]
    
    return df

def get_daily_data(ts_codes):
    """获取每日行情数据（PE、PB等）"""
    # 分批获取
    all_data = []
    batch_size = 500
    
    for i in range(0, len(ts_codes), batch_size):
        batch = ts_codes[i:i+batch_size]
        try:
            df = ts.pro_bar(
                ts_code=','.join(batch),
                asset='E',
                adj='qfq',
                start_date=(datetime.datetime.now() - datetime.timedelta(days=30)).strftime('%Y%m%d'),
                end_date=datetime.datetime.now().strftime('%Y%m%d')
            )
            if df is not None and len(df) > 0:
                all_data.append(df)
        except Exception as e:
            print(f"Error fetching batch {i}: {e}")
    
    if all_data:
        return pd.concat(all_data, ignore_index=True)
    return pd.DataFrame()

def filter_stocks(df, conditions):
    """筛选股票"""
    result = df.copy()
    
    for col, (min_val, max_val) in conditions.items():
        if col in result.columns:
            if min_val is not None:
                result = result[result[col] > min_val]
            if max_val is not None:
                result = result[result[col] < max_val]
    
    return result

def save_to_github(df, filename='low_valuation_stocks.csv'):
    """保存结果到GitHub"""
    import requests
    from io import StringIO
    
    date_str = datetime.datetime.now().strftime('%Y-%m-%d')
    content = df.to_csv(index=False, encoding='utf-8-sig')
    
    # API endpoint
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/data/{filename}"
    
    # 检查文件是否存在
    response = requests.get(url, headers={'Authorization': f'token {GITHUB_TOKEN}'})
    
    sha = response.json().get('sha') if response.status_code == 200 else None
    
    # 上传文件
    data = {
        'message': f'update: {date_str} 低估股票筛选结果',
        'content': __import__('base64').b64encode(content.encode('utf-8')).decode('utf-8'),
        'branch': BRANCH
    }
    if sha:
        data['sha'] = sha
    
    response = requests.put(url, json=data, headers={'Authorization': f'token {GITHUB_TOKEN}'})
    
    if response.status_code in [200, 201]:
        print(f"✓ 已保存到 GitHub: data/{filename}")
        return True
    else:
        print(f"✗ 保存失败: {response.text}")
        return False

def main():
    print("=" * 50)
    print("价值另一面 - A股低估筛选器")
    print("=" * 50)
    
    # 获取股票列表
    print("\n[1/3] 获取股票列表...")
    stocks = fetch_stock_data()
    print(f"  共 {len(stocks)} 只A股")
    
    # 获取行情数据（简化版：用最新交易日的概览数据）
    print("\n[2/3] 获取行情数据...")
    # 这里简化处理，实际需要用tushare的更多接口
    # 先获取基本面的关键指标
    
    # 获取实时行情（包含PE、PB）
    try:
        df = ts.get_today_all()
        if df is not None:
            print(f"  获取到 {len(df)} 条行情数据")
    except Exception as e:
        print(f"  获取行情失败: {e}")
        df = pd.DataFrame()
    
    if len(df) > 0:
        # 筛选
        print("\n[3/3] 筛选低估股票...")
        
        # 过滤条件
        result = df[
            (df['pe'] > 0) & (df['pe'] < 15) &  # PE 0-15
            (df['pb'] > 0) & (df['pb'] < 2) &    # PB 0-2
            (df['turnoverratiof'] > 0.5)          # 成交活跃
        ].copy()
        
        result = result.sort_values('pe')
        result = result.head(50)  # 取前50只
        
        print(f"  筛选出 {len(result)} 只低估股票")
        
        # 展示结果
        print("\n" + "=" * 50)
        print("低估股票TOP10:")
        print("=" * 50)
        display_cols = ['code', 'name', 'close', 'pe', 'pb', 'turnoverratiof']
        display_cols = [c for c in display_cols if c in result.columns]
        print(result[display_cols].head(10).to_string(index=False))
        
        # 保存到GitHub
        save_to_github(result)
        
    else:
        print("  无行情数据")
    
    print("\n完成!")

if __name__ == '__main__':
    main()
