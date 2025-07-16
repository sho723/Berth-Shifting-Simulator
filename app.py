import streamlit as st
import pandas as pd
import numpy as np
import json
from datetime import datetime, timedelta
import itertools
from io import StringIO
import requests

# ページ設定
st.set_page_config(page_title="トウモロコシ運搬船バース最適化", layout="wide")

# TTMレート取得（仮想的な関数 - 実際のAPIに置き換えてください）
@st.cache_data
def get_usd_jpy_rate():
    """USD/JPY為替レートを取得（デモ用固定値）"""
    # 実際の実装では為替APIを使用してください
    return 150.0  # 仮の為替レート

# データクラス
class SiloData:
    def __init__(self, name, capacity, current_stock, daily_usage):
        self.name = name
        self.capacity = capacity
        self.current_stock = current_stock
        self.daily_usage = daily_usage
        
    def get_available_capacity(self, days_from_start):
        """指定日数後の利用可能容量を計算"""
        projected_stock = max(0, self.current_stock - (self.daily_usage * days_from_start))
        return self.capacity - projected_stock
    
    def is_available(self, days_from_start, required_capacity):
        """指定日数後に必要容量が利用可能かチェック"""
        return self.get_available_capacity(days_from_start) >= required_capacity

class RouteOptimizer:
    def __init__(self, silos, berth_change_cost_usd, delivery_capacity_per_berth):
        self.silos = silos
        self.berth_change_cost_usd = berth_change_cost_usd
        self.delivery_capacity_per_berth = delivery_capacity_per_berth
        
    def generate_route_plans(self, max_berth_changes):
        """可能なルートプランを生成"""
        plans = []
        silo_names = list(self.silos.keys())
        
        # 1回から最大変更回数+1回までのバース使用パターンを生成
        for num_berths in range(1, min(max_berth_changes + 2, len(silo_names) + 1)):
            for berth_combination in itertools.combinations(silo_names, num_berths):
                for berth_order in itertools.permutations(berth_combination):
                    plans.append(list(berth_order))
        
        return plans
    
    def evaluate_route(self, route, start_date):
        """ルートを評価"""
        total_cost = 0
        current_day = 0
        results = []
        
        for i, berth_name in enumerate(route):
            # バース変更コスト
            if i > 0:
                total_cost += self.berth_change_cost_usd
            
            silo = self.silos[berth_name]
            
            # サイロの利用可能性をチェック
            if silo.is_available(current_day, self.delivery_capacity_per_berth):
                delivery_date = start_date + timedelta(days=current_day)
                available_capacity = silo.get_available_capacity(current_day)
                delivery_amount = min(self.delivery_capacity_per_berth, available_capacity)
                
                results.append({
                    'バース': berth_name,
                    '納入日': delivery_date.strftime('%Y-%m-%d'),
                    '納入量': delivery_amount,
                    '利用可能容量': available_capacity,
                    '実行可能': True
                })
                
                current_day += 1
            else:
                results.append({
                    'バース': berth_name,
                    '納入日': 'N/A',
                    '納入量': 0,
                    '利用可能容量': silo.get_available_capacity(current_day),
                    '実行可能': False
                })
                
                return {
                    'route': route,
                    'total_cost_usd': float('inf'),
                    'total_cost_jpy': float('inf'),
                    'feasible': False,
                    'details': results
                }
        
        return {
            'route': route,
            'total_cost_usd': total_cost,
            'total_cost_jpy': total_cost * get_usd_jpy_rate(),
            'feasible': True,
            'details': results
        }

# メイン関数
def main():
    st.title("🚢 トウモロコシ運搬船バース最適化システム")
    
    # サイドバーでの設定
    st.sidebar.header("📋 システム設定")
    
    # 為替レート表示
    usd_jpy_rate = get_usd_jpy_rate()
    st.sidebar.write(f"💱 USD/JPY レート: {usd_jpy_rate:.2f}円")
    
    # 基本設定
    max_berth_changes = st.sidebar.slider("最大バース変更回数", 1, 5, 3)
    berth_change_cost = st.sidebar.number_input("バース変更コスト (USD)", value=10000, step=1000)
    delivery_capacity = st.sidebar.number_input("バースあたり納入容量", value=1000, step=100)
    
    # 起算日設定
    start_date = st.sidebar.date_input("起算日", datetime.now())
    
    # データ入力方式選択
    input_mode = st.sidebar.radio("データ入力方式", ["手動入力", "ファイル読み込み"])
    
    if input_mode == "手動入力":
        # サイロ数設定
        num_silos = st.sidebar.slider("サイロ数", 2, 10, 5)
        
        # メインエリア
        st.header("🏭 サイロ情報設定")
        
        # サイロ情報入力
        silos = {}
        cols = st.columns(2)
        
        for i in range(num_silos):
            with cols[i % 2]:
                st.subheader(f"サイロ {i+1}")
                name = st.text_input(f"サイロ名", f"サイロ_{i+1}", key=f"silo_name_{i}")
                capacity = st.number_input(f"容量", value=5000, step=100, key=f"capacity_{i}")
                current_stock = st.number_input(f"現在の在庫", value=2000, step=100, key=f"stock_{i}")
                daily_usage = st.slider(f"1日あたり使用量", 0, 5000, 200, key=f"usage_{i}")
                
                silos[name] = SiloData(name, capacity, current_stock, daily_usage)
                
                # 容量使用率表示
                usage_rate = (current_stock / capacity) * 100
                st.progress(usage_rate / 100)
                st.write(f"使用率: {usage_rate:.1f}%")
    
    else:
        # ファイル読み込み
        uploaded_file = st.file_uploader("データファイルを選択", type=['json'])
        
        if uploaded_file is not None:
            try:
                data = json.load(uploaded_file)
                silos = {}
                
                for silo_data in data['silos']:
                    silos[silo_data['name']] = SiloData(
                        silo_data['name'],
                        silo_data['capacity'],
                        silo_data['current_stock'],
                        silo_data['daily_usage']
                    )
                
                st.success(f"✅ {len(silos)}個のサイロデータを読み込みました")
                
                # 読み込んだデータを表示
                st.subheader("📊 読み込みデータ")
                silo_df = pd.DataFrame([
                    {
                        'サイロ名': silo.name,
                        '容量': silo.capacity,
                        '現在在庫': silo.current_stock,
                        '1日使用量': silo.daily_usage,
                        '使用率': f"{(silo.current_stock/silo.capacity)*100:.1f}%"
                    }
                    for silo in silos.values()
                ])
                st.dataframe(silo_df)
                
            except Exception as e:
                st.error(f"❌ ファイル読み込みエラー: {str(e)}")
                return
        else:
            st.info("📁 データファイルをアップロードしてください")
            return
    
    # 最適化実行
    if st.button("🚀 最適化実行", type="primary"):
        if len(silos) < 2:
            st.error("❌ 最低2つのサイロが必要です")
            return
        
        with st.spinner("計算中..."):
            optimizer = RouteOptimizer(silos, berth_change_cost, delivery_capacity)
            route_plans = optimizer.generate_route_plans(max_berth_changes)
            
            # 全ルートを評価
            results = []
            for route in route_plans:
                result = optimizer.evaluate_route(route, start_date)
                if result['feasible']:
                    results.append(result)
            
            # 結果をコストで並び替え
            results.sort(key=lambda x: x['total_cost_usd'])
        
        # 結果表示
        st.header("📈 最適化結果")
        
        if not results:
            st.error("❌ 実行可能なルートが見つかりませんでした")
            return
        
        # 結果サマリー
        summary_df = pd.DataFrame([
            {
                'ランク': i+1,
                'ルート': ' → '.join(result['route']),
                'バース変更回数': len(result['route']) - 1,
                'コスト (USD)': f"${result['total_cost_usd']:,.0f}",
                'コスト (JPY)': f"¥{result['total_cost_jpy']:,.0f}"
            }
            for i, result in enumerate(results[:10])  # 上位10件
        ])
        
        st.subheader("🏆 最適ルート一覧")
        st.dataframe(summary_df)
        
        # 詳細結果
        st.subheader("📋 詳細結果")
        selected_rank = st.selectbox("詳細を表示するランク", range(1, min(len(results)+1, 11)))
        
        if selected_rank:
            selected_result = results[selected_rank-1]
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.metric("総コスト (USD)", f"${selected_result['total_cost_usd']:,.0f}")
                st.metric("バース変更回数", len(selected_result['route']) - 1)
            
            with col2:
                st.metric("総コスト (JPY)", f"¥{selected_result['total_cost_jpy']:,.0f}")
                st.metric("実行可能", "✅" if selected_result['feasible'] else "❌")
            
            # 詳細スケジュール
            detail_df = pd.DataFrame(selected_result['details'])
            st.dataframe(detail_df)
        
        # データ保存
        st.subheader("💾 データ保存")
        
        # 保存用データ作成
        save_data = {
            'timestamp': datetime.now().isoformat(),
            'settings': {
                'max_berth_changes': max_berth_changes,
                'berth_change_cost': berth_change_cost,
                'delivery_capacity': delivery_capacity,
                'start_date': start_date.isoformat()
            },
            'silos': [
                {
                    'name': silo.name,
                    'capacity': silo.capacity,
                    'current_stock': silo.current_stock,
                    'daily_usage': silo.daily_usage
                }
                for silo in silos.values()
            ],
            'results': results[:5]  # 上位5件を保存
        }
        
        if st.button("📥 結果をダウンロード"):
            # JSONファイルとしてダウンロード
            json_str = json.dumps(save_data, indent=2, ensure_ascii=False)
            st.download_button(
                label="💾 結果データダウンロード",
                data=json_str,
                file_name=f"corn_ship_optimization_{start_date.strftime('%Y%m%d')}.json",
                mime="application/json"
            )

if __name__ == "__main__":
    main()
