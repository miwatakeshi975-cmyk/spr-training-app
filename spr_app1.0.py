import streamlit as st
import pandas as pd
import re
import io
import difflib
import wave
import struct
import math
import base64
import os
import datetime
from gtts import gTTS

# --- Page Configuration ---
st.set_page_config(
    page_title="SPR Training Center",
    page_icon="🔥",
    layout="centered"
)

# --- Custom CSS (Premium UI) ---
def inject_custom_css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    
    /* Sleek buttons */
    div.stButton > button {
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.2s ease-in-out;
        border: 1px solid rgba(250, 250, 250, 0.2);
    }
    
    div.stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }
    
    /* Clean headers */
    h1, h2, h3 {
        color: #2e86de;
    }
    
    /* Metrics box shadow */
    div[data-testid="metric-container"] {
        background-color: #f7f9fc;
        border-radius: 12px;
        padding: 15px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    
    @media (prefers-color-scheme: dark) {
        div[data-testid="metric-container"] {
            background-color: #1e2530;
        }
        h1, h2, h3 {
            color: #54a0ff;
        }
    }
    </style>
    """, unsafe_allow_html=True)

# --- History Saving ---
HISTORY_FILE = "learning_history.csv"

def save_history(mode_name, df_attempted, scores):
    """学習履歴をローカルのCSVファイルにDayごとに分割して保存する (utf-8-sig形式で行う)"""
    df_result = df_attempted.copy()
    
    # 辞書に保存された結果(idx)をもとに、True/Falseを判定
    # scores は {1: True, 2: False...} のようになっている
    df_result['is_correct'] = [scores.get(i, False) for i in range(len(df_result))]
    
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    rows = []
    
    # 年度、月、週、Dayのグループごとに正答率を集計して行を分ける
    grouped = df_result.groupby(['FY', 'B_Month', 'Week', 'Day'])
    
    for (fy, bm, bw, bd), group in grouped:
        total = len(group)
        correct = group['is_correct'].sum()
        accuracy = round((correct / total * 100), 1) if total > 0 else 0
        
        # FY, Month, Week, Dayをそれぞれ独立した列として保存する（ソート・フィルタリング用）
        rows.append({
            "Date": now,
            "Mode": mode_name,
            "FY": fy,
            "Month": bm,
            "Week": bw,
            "Day": bd,
            "Total Questions": total,
            "Correct": correct,
            "Accuracy (%)": accuracy
        })
        
    new_data = pd.DataFrame(rows)
    
    existing_df = load_history_df()
    if not existing_df.empty:
        history_df = pd.concat([existing_df, new_data], ignore_index=True)
    else:
        history_df = new_data
        
    # 文字化け防止のため utf-8-sig で保存
    history_df.to_csv(HISTORY_FILE, index=False, encoding="utf-8-sig")

# --- Utils & Helpers ---
def load_history_df():
    """履歴CSVを安全に読み込み、DataFrameを返す（文字化け対策済み）"""
    if not os.path.exists(HISTORY_FILE):
        return pd.DataFrame()
        
    try:
        return pd.read_csv(HISTORY_FILE, encoding="utf-8-sig")
    except UnicodeDecodeError:
        try:
            return pd.read_csv(HISTORY_FILE, encoding="shift_jis")
        except UnicodeDecodeError:
            return pd.read_csv(HISTORY_FILE, encoding="cp932")

def navigate_to(target_mode, **kwargs):
    """指定した画面へ安全に遷移し、関連するUIフラグをリセットする"""
    st.session_state.update(
        mode=target_mode,
        is_error_mode=False,
        is_keyword_mode=False,
        confirm_exit=False,
        is_typo=False,
        **kwargs
    )
    st.rerun()

# --- Audio Generators ---
@st.cache_data
def get_success_audio_base64():
    """正解時の楽しいチャイム音を生成してBase64で返す"""
    
    # 🌟 ここから下の数値を変更すると音が変わります 🌟
    
    # 音の長さ（秒）
    duration = 0.6
    
    # 周波数（音の高さ）のリスト。左から右へ順番に鳴ります。
    # 同じ数字を連続させると、その音だけ長く鳴ります。
    # 【例1】ピンポン♪ : [1318.51, 1318.51, 1046.50, 1046.50]
    # 【例2】レベルアップ音 : [523.25, 587.33, 659.25, 783.99, 1046.50, 1046.50, 1046.50]
    # 【例3】コイン音 : [987.77, 1318.51] (durationは0.2など短くする)
    frequencies = [523.25, 587.33, 659.25, 783.99, 1046.50, 1046.50, 1046.50]
    
    # 🌟 ここまで 🌟
    
    sample_rate = 44100
    num_samples = int(duration * sample_rate)
    audio = []
    
    for i in range(num_samples):
        progress = i / num_samples
        note_idx = int(progress * len(frequencies))
        if note_idx >= len(frequencies): note_idx = len(frequencies) - 1
        freq = frequencies[note_idx]
        
        local_progress = (progress * len(frequencies)) % 1.0
        
        # より自然な音にするためのエンベロープ（減衰）
        if local_progress < 0.05:
            envelope = local_progress / 0.05 # アタック
        else:
            envelope = max(0, 1.0 - ((local_progress - 0.05) / 0.95)) # ディケイ
            
        val = 20000 * envelope * math.sin(2 * math.pi * freq * i / sample_rate)
        audio.append(int(val))

    buffer = io.BytesIO()
    with wave.open(buffer, 'w') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        for sample in audio:
            wav.writeframes(struct.pack('<h', sample))

    encoded = base64.b64encode(buffer.getvalue()).decode('utf-8')
    return f"data:audio/wav;base64,{encoded}"

def play_success_sound():
    b64 = get_success_audio_base64()
    st.markdown(f'<audio autoplay="true" src="{b64}"></audio>', unsafe_allow_html=True)

# --- 1. データ読み込み ---
SHEET_ID = "1usIv38xEO6KLAi3x8jxuZPuIgimQ0FUd4NEeeZPjVpA"
GID = "2094303905"
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID}"

@st.cache_data(ttl=3600)
def load_and_process_data():
    try:
        df = pd.read_csv(CSV_URL).iloc[:, 0:8]
    except Exception as e:
        st.error(f"スプレッドシートの読み込みに失敗しました。オフラインになっているか、Google側のアクセス制限の可能性があります。詳細: {e}")
        st.stop()
        
    df.columns = ['Date','Week','Day','No','Japanese','Listening','English', 'Explanation']
    df['Date_dt'] = pd.to_datetime(df['Date'], errors='coerce')

    is_w1 = df['Week'].str.strip().str.upper() == 'W1'
    df['B_Month'] = df['Date_dt'].dt.month
    df['B_Year'] = df['Date_dt'].dt.year
    
    cond_w1_late = is_w1 & (df['Date_dt'].dt.day >= 21)
    df.loc[cond_w1_late, 'B_Month'] = df.loc[cond_w1_late, 'Date_dt'].dt.month + 1
    
    cond_month_13 = df['B_Month'] > 12
    df.loc[cond_month_13, 'B_Month'] = 1
    df.loc[cond_month_13, 'B_Year'] = df.loc[cond_month_13, 'B_Year'] + 1
    
    df['FY'] = df['B_Year']
    df.loc[df['B_Month'] < 4, 'FY'] = df.loc[df['B_Month'] < 4, 'B_Year'] - 1

    for col in ['Week','Day','Japanese','Listening','English', 'Explanation']:
        df[col] = df[col].astype(str).str.strip()
        
    return df.dropna(subset=['English']).reset_index(drop=True)


# --- 2. 状態管理 ---
defaults = [
    ('mode', 'Top'), ('active_df', pd.DataFrame()), ('wrong_df', pd.DataFrame()),
    ('q_idx', 0), ('attempts', 0), ('correct_count', 0), ('last_input', ''),
    ('used_ids', []), ('is_error_mode', False), ('is_keyword_mode', False), ('confirm_exit', False), ('clear_key', 0),
    ('search_keyword_en', ''), ('search_keyword_jp', ''),
    ('error_order', 'ランダム（件数指定）'), ('error_count', 10), ('error_days', 5), ('is_typo', False),
    ('history_saved', True), ('scores', {}),
    ('active_fy', 0), ('active_bm', 0), ('active_bw', 'すべて'), ('active_bd', 'すべて')
]
for key, val in defaults:
    if key not in st.session_state: 
        st.session_state[key] = val

def start_quiz(target_df, is_error=False, is_keyword=False, rerun=True):
    st.session_state.update(
        mode="Quiz", active_df=target_df, original_df=target_df.copy(), q_idx=0, correct_count=0, 
        attempts=0, last_input="", wrong_df=pd.DataFrame(), 
        is_error_mode=is_error, is_keyword_mode=is_keyword, clear_key=0, confirm_exit=False, is_typo=False,
        history_saved=False, scores={} # 新しいクイズが始まったので保存フラグと成績辞書をリセット
    )
    # Reset mini search keywords safely
    for key in ["mini_search_en", "mini_search_jp"]:
        if key in st.session_state:
            try:
                st.session_state[key] = ""
            except:
                # If widget is already instantiated, we can't modify it directly in this run.
                # However, calling via on_click or using try-except prevents the crash.
                pass
    if rerun:
        st.rerun()

# --- 3. 判定ロジック ---
def clean(text):
    return re.sub(r'[^a-zA-Z0-9]', '', str(text).strip().lower())

def check_answer(idx):
    row = st.session_state.active_df.iloc[idx]
    user_input = st.session_state.get(f"ans_{idx}_{st.session_state.clear_key}", "")
    st.session_state.last_input = user_input
    
    clean_user = clean(user_input)
    clean_result = clean(row['English'])
    
    if clean_user == clean_result:
        st.session_state.correct_count += 1
        st.session_state.attempts = 10
        st.session_state.scores[idx] = True
        st.session_state.is_typo = False
    else:
        matcher = difflib.SequenceMatcher(None, clean_user, clean_result)
        if matcher.ratio() >= 0.85 and len(clean_user) >= 3:
            st.session_state.is_typo = True
        else:
            st.session_state.is_typo = False
        
        st.session_state.attempts += 1
        if st.session_state.attempts >= 4:
            st.session_state.scores[idx] = False
            st.session_state[f"force_retry_{idx}"] = True

def cleanup_old_session_keys(q_idx, clear_key):
    """不要になった解答キーを削除してメモリリークを防ぐ"""
    for k in range(clear_key + 1):
        key_to_delete = f"ans_{q_idx}_{k}"
        if key_to_delete in st.session_state:
            del st.session_state[key_to_delete]
            
    # 正解音の再生フラグもお掃除
    key_played = f"played_sound_{q_idx}"
    if key_played in st.session_state:
        del st.session_state[key_played]

# --- 4. 画面コンポーネント関数 ---
def render_top():
    st.title("🌟 SPR Training V3.3")
    st.markdown("モダンで楽しい学習体験へようこそ。")
    st.divider()
    
    st.info("### 1. 📅 通常クイズ\n\n最新の過去問や、指定した対象月の特訓を行います。日々のルーティンに。")
    if st.button("始める", key="top_btn_1", use_container_width=True):
        navigate_to("RangeSelect")

    st.warning("### 2. 👂 弱点克服\n\n自分が聞き間違えやすいディクテーションのミスを徹底的に復習。")
    if st.button("始める", key="top_btn_2", use_container_width=True):
        navigate_to("ErrorFixSetup")
            
    st.success("### 3. 🔍 キーワード検索\n\n特定の英単語や日本語のフレーズを含む問題だけを集中的に練習。")
    if st.button("始める", key="top_btn_3", use_container_width=True):
        navigate_to("KeywordSearch")
        
    st.divider()
    st.subheader("📊 継続は力なり！")
    if st.button("📈 学習記録（履歴）を見る", use_container_width=True):
        navigate_to("History")

def render_history():
    st.title("📈 学習履歴ダッシュボード")
    
    df_hist = load_history_df()
    
    if not df_hist.empty:
            
            # 安全のため、カラムの存在チェックをしてエラーを防ぐ
            total_col = 'Total Questions' if 'Total Questions' in df_hist.columns else 'Total Questions'
            if total_col not in df_hist.columns and 'Total' in df_hist.columns:
                total_col = 'Total'
                
            total_sessions = len(df_hist)
            total_questions = df_hist[total_col].sum() if total_col in df_hist.columns else 0
            avg_acc = df_hist['Accuracy (%)'].mean() if 'Accuracy (%)' in df_hist.columns else 0
            
            c1, c2, c3 = st.columns(3)
            c1.metric("総記録数 (Day単位)", f"{total_sessions} 件")
            c2.metric("総挑戦問題数", f"{total_questions} 問")
            c3.metric("平均正答率", f"{avg_acc:.1f} %")
            
            st.divider()
            
            st.subheader("🚀 正答率の推移")
            # 推移グラフを描画
            if 'Accuracy (%)' in df_hist.columns:
                chart_data = df_hist[['Accuracy (%)']]
                st.line_chart(chart_data)
            
            st.subheader("📚 過去の特訓ログ (最新30件)")
            # 最新のものを上にして表示する
            st.dataframe(df_hist.tail(30).iloc[::-1].reset_index(drop=True), use_container_width=True)
    else:
        st.info("まだ学習履歴がありません。まずはクイズ特訓を始めてみましょう！")
        
    st.divider()
    if st.button("🏠 メニュー（Top）に戻る", use_container_width=True): 
        navigate_to("Top")

def render_range_select():
    df = st.session_state.df_master
    st.header("📅 出題範囲の設定")
    
    with st.container():
        if st.button("✨ ワンクリックで最新の回を読み込む"):
            latest = df.iloc[-1]
            st.session_state.update(fy_sel=latest['FY'], bm_sel=latest['B_Month'], bw_sel=latest['Week'], bd_sel=latest['Day'])
            st.rerun()
            
        st.markdown("<br/>", unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        s_fy = c1.selectbox("年度 (FY)", sorted(df['FY'].unique(), reverse=True), key="fy_sel")
        s_bm = c1.selectbox("月", sorted(df[df['FY']==s_fy]['B_Month'].unique()), key="bm_sel")
        
        # 週(Week)に「すべて」を追加
        week_opts = sorted(df[(df['FY']==s_fy)&(df['B_Month']==s_bm)]['Week'].unique().tolist())
        s_bw = c2.selectbox("週 (Week)", ["すべて"] + week_opts, key="bw_sel")
        
        if s_bw != "すべて":
            day_opts = sorted(df[(df['FY']==s_fy)&(df['B_Month']==s_bm)&(df['Week']==s_bw)]['Day'].unique().tolist())
        else:
            day_opts = sorted(df[(df['FY']==s_fy)&(df['B_Month']==s_bm)]['Day'].unique().tolist())
            
        s_bd = c2.selectbox("Day", ["すべて"] + day_opts, key="bd_sel")
        
        # 動的なクエリの組み立て
        q = f"FY=={s_fy} and B_Month=={s_bm}"
        if s_bw != "すべて":
            q += f" and Week=='{s_bw}'"
        if s_bd != "すべて":
            q += f" and Day=='{s_bd}'"
            
        target_df = df.query(q).reset_index(drop=True)
        
        st.info(f"📚 現在の条件で抽出された問題数: **{len(target_df)}問**")
        
        if st.button("🚀 この範囲で特訓を開始", type="primary", use_container_width=True): 
            st.session_state.active_fy = s_fy
            st.session_state.active_bm = s_bm
            st.session_state.active_bw = s_bw
            st.session_state.active_bd = s_bd
            start_quiz(target_df)
            
    st.divider()
    if st.button("🏠 メニュー（Top）に戻る", use_container_width=True): 
        navigate_to("Top")

def render_keyword_search():
    df = st.session_state.df_master
    st.header("🔍 表現指定特訓")
    
    
    def on_keyword_change(target):
        if target == "en": 
            st.session_state.search_keyword_jp = ""
        else: 
            st.session_state.search_keyword_en = ""

    c1, c2 = st.columns(2)
    k_en = c1.text_input("🇺🇸 英語で検索", key="search_keyword_en", on_change=on_keyword_change, args=("en",))
    k_jp = c2.text_input("🇯🇵 日本語で検索", key="search_keyword_jp", on_change=on_keyword_change, args=("jp",))
    
    target_df, k_input = pd.DataFrame(), ""
    if k_en:
        target_df, k_input = df[df['English'].str.contains(k_en, case=False, na=False)].reset_index(drop=True), k_en
    elif k_jp:
        target_df, k_input = df[df['Japanese'].str.contains(k_jp, na=False)].reset_index(drop=True), k_jp

    if k_input:
        st.info(f"「{k_input}」を含む問題が **{len(target_df)} 問** 見つかったざんす。")
        if not target_df.empty and st.button("🚀 特訓を開始する", type="primary", use_container_width=True): 
            start_quiz(target_df, is_keyword=True)
            
    st.divider()
    if st.button("🏠 メニュー（Top）に戻る", use_container_width=True): 
        navigate_to("Top")

def render_error_fix_setup():
    df = st.session_state.df_master
    st.header("👂 Fix Your Hearing!")
    pool = df[(df['English']!=df['Listening']) & (df['Listening'].str.len() > 0) & (df['Listening']!="nan")].reset_index(drop=True)
    available = pool[~pool.index.isin(st.session_state.used_ids)]
    
    if available.empty:
        st.success("🎉 現在、登録されている聞き間違いは全て復習完了しました！素晴らしい！")
        if st.button("🔄 復習履歴をリセットして最初から", use_container_width=True): 
            st.session_state.used_ids=[]
            st.rerun()
    else:
        col1, col2 = st.columns(2)
        col1.metric("残り復習タスク", f"{len(available)} 問")
        order = col2.selectbox("出題方法", ["ランダム", "最新順", "古い順"], index=1, key="error_order")
        val = st.number_input("今回復習する回数（日数）", 1, 365, value=1)
        
        if st.button("🔥 弱点克服をスタート", type="primary", use_container_width=True):
            if "ランダム" in order: 
                res = available.sample(n=min(val, len(available)))
            else:
                dates = sorted(available['Date_dt'].unique(), reverse="最新" in order)[:val]
                res = available[available['Date_dt'].isin(dates)].sort_values("Date_dt", ascending="最新" not in order)
            start_quiz(res.reset_index(drop=True), is_error=True)
            
    st.divider()
    if st.button("🏠 メニュー（Top）に戻る", use_container_width=True): 
        navigate_to("Top")

def render_quiz():
    f_df = st.session_state.active_df
    
    # Progress Bar
    progress_val = min((st.session_state.q_idx) / max(1, len(f_df)), 1.0)
    st.progress(progress_val)
    
    if st.session_state.q_idx < len(f_df):
        row = f_df.iloc[st.session_state.q_idx]
        is_err = st.session_state.is_error_mode
        
        c1, c2 = st.columns([3, 1])
        c1.subheader("👂 聞き間違い修正！" if is_err else f"Q: {row['Japanese']}")
        
        # 出題中の問題が「いつの」ものかを表示
        scope_str = f"{row.get('FY', '')}年度 {row.get('B_Month', '')}月 {row.get('Week', '')} Day{row.get('Day', '')}"
        
        c2.markdown(f"<div style='text-align:right; color:#888;'><span style='font-size:0.8em;'>{scope_str}</span><br/>Question <b>{st.session_state.q_idx+1} / {len(f_df)}</b></div>", unsafe_allow_html=True)
        
        st.divider()
        locked = st.session_state.attempts in [4, 10]
        
        with st.form(key=f"q_{st.session_state.q_idx}_{st.session_state.clear_key}"):
            ans = st.text_input(
                f"📝 解答 ({min(st.session_state.attempts+1, 4)} 回目の挑戦)", 
                value=row['Listening'] if (is_err and st.session_state.attempts==0) else st.session_state.last_input, 
                key=f"ans_{st.session_state.q_idx}_{st.session_state.clear_key}", 
                disabled=locked
            )
            
            c_btn1, c_btn2, c_btn3 = st.columns(3)
            with c_btn1:
                if st.form_submit_button("✅ 判定する", use_container_width=True, disabled=locked):
                    if not locked:
                        check_answer(st.session_state.q_idx)
                        st.rerun()
            with c_btn2:
                if st.form_submit_button("🔁 やり直す", use_container_width=True, disabled=locked):
                    if not locked:
                        st.session_state.update(last_input="", clear_key=st.session_state.clear_key+1, is_typo=False)
                        st.rerun()
            with c_btn3:
                if st.form_submit_button("⏭️ 次へ進む", use_container_width=True):
                    if st.session_state.get(f"force_retry_{st.session_state.q_idx}", False): 
                        st.session_state.wrong_df = pd.concat([st.session_state.wrong_df, row.to_frame().T]).drop_duplicates()
                    cleanup_old_session_keys(st.session_state.q_idx, st.session_state.clear_key)
                    st.session_state.update(q_idx=st.session_state.q_idx+1, attempts=0, last_input="", clear_key=0, is_typo=False)
                    st.rerun()

        # Feedback
        if st.session_state.get('is_typo', False) and not locked:
            st.warning("👀 **Typo!** 惜しい！スペルミスがあるかもしれません。")

        # Hint logic
        if 1 <= st.session_state.attempts <= 3:
            target_ws, user_ws = row['English'].split(), st.session_state.last_input.split()
            hint = [w if (clean(w)==(clean(user_ws[i]) if i<len(user_ws) else "") or (st.session_state.attempts>=2 and (i==0 or w[0].isupper()))) else "_"*len(w) for i, w in enumerate(target_ws)]
            st.info(f"💡 ヒント: **{' '.join(hint)}**")
        
        # Audio rendering with exception handling
        if st.session_state.attempts >= 3:
            try:
                fp = io.BytesIO()
                gTTS(text=row['English'], lang='en').write_to_fp(fp)
                fp.seek(0)
                st.audio(fp)
            except Exception as e:
                st.error(f"音声の取得に失敗しました ({e})")

        # Answer reveal & feedback
        if locked:
            if st.session_state.attempts==10:
                st.success(f"✨ **Excellent! 正解!**: {row['English']}")
                
                sound_key = f"played_sound_{st.session_state.q_idx}"
                if not st.session_state.get(sound_key, False):
                    play_success_sound()
                    st.session_state[sound_key] = True
                    
                if is_err and row.name not in st.session_state.used_ids: 
                    st.session_state.used_ids.append(row.name)
            else: 
                st.error(f"❌ **正解は**: {row['English']}")
            
            if is_err and str(row['Explanation']).strip() not in ["", "nan"]: 
                st.info(f"📖 {row['Explanation']}")

        st.divider()
        
        chk_key = f"force_retry_{st.session_state.q_idx}"
        ui_key = f"ui_check_{st.session_state.q_idx}"
        
        if chk_key not in st.session_state:
            st.session_state[chk_key] = False
            
        if ui_key not in st.session_state:
            st.session_state[ui_key] = st.session_state[chk_key]
            
        # 確実に内部ステータスとUIを同期（プログラムからの変更を優先）
        if st.session_state[chk_key] != st.session_state[ui_key]:
            st.session_state[ui_key] = st.session_state[chk_key]

        def sync_check(c_key=chk_key, u_key=ui_key):
            st.session_state[c_key] = st.session_state[u_key]

        st.checkbox("🔄 この問題をリトライ対象にチェックする", key=ui_key, on_change=sync_check)

        st.divider()
        st.subheader("⚙️ オプション")
        col_skip, col_finish, col_exit = st.columns(3)
        with col_skip:
            if st.button("⏭️ この問題をスキップ", use_container_width=True):
                cleanup_old_session_keys(st.session_state.q_idx, st.session_state.clear_key)
                st.session_state.active_df = st.session_state.active_df.drop(st.session_state.q_idx).reset_index(drop=True)
                st.session_state.update(attempts=0, last_input="", clear_key=0, is_typo=False)
                st.rerun()
        with col_finish:
            if st.button("🏁 この範囲の回答を終了", use_container_width=True):
                cleanup_old_session_keys(st.session_state.q_idx, st.session_state.clear_key)
                st.session_state.active_df = st.session_state.active_df.iloc[:st.session_state.q_idx].reset_index(drop=True)
                st.session_state.update(attempts=0, last_input="", clear_key=0, is_typo=False)
                st.rerun()
        with col_exit:
            if st.button("🏠 中止してメニューへ", use_container_width=True): 
                st.session_state.confirm_exit=True
                st.rerun()
                
        if st.session_state.confirm_exit:
            st.warning("本当に特訓を中止しますか？（ここまでの履歴は保存されません）")
            c_exit1, c_exit2 = st.columns(2)
            if c_exit1.button("はい、終了する", use_container_width=True): 
                st.session_state.update(mode="Top", is_error_mode=False, is_keyword_mode=False, confirm_exit=False, is_typo=False)
                st.rerun()
            if c_exit2.button("いいえ、続ける", use_container_width=True): 
                st.session_state.confirm_exit=False
                st.rerun()
    else:
        render_quiz_results(f_df)

def render_quiz_results(f_df):
    accuracy = (st.session_state.correct_count / len(f_df)) * 100 if len(f_df) > 0 else 0
    
    # --- 履歴をCSVにDay単位で保存し、初回のみエフェクトを再生する ---
    if not st.session_state.get('history_saved', True):
        mode_label = "通常クイズ"
        if st.session_state.is_error_mode: 
            mode_label = "弱点克服"
        elif st.session_state.is_keyword_mode: 
            mode_label = "キーワード検索"
            
        # 関数に渡すと、内部でDayごと・指定カラムごとに分割保存される
        save_history(mode_label, f_df, st.session_state.scores)
        st.session_state.history_saved = True
        
        if accuracy >= 80:
            st.balloons()
        
    st.title("🏁 特訓完了！")
    
    c1, c2, c3 = st.columns(3)
    c1.metric("挑戦した問題数", f"{len(f_df)} 問")
    c2.metric("正解数", f"{st.session_state.correct_count} 問")
    c3.metric("正答率", f"{accuracy:.1f} %")
    
    if accuracy == 100:
        st.success("完璧です！この調子で頑張りましょう！🌟")
    elif accuracy >= 80:
        st.info("大変よくできました！あと少しでパーフェクトです！👍")
    else:
        st.warning("復習あるのみ！間違えた問題をやり直してみましょう。💪")
    
    st.divider()
    st.subheader("🔁 次のアクション")
    
    c_retry1, c_retry2 = st.columns(2)
    with c_retry1:
        if st.button("🔄 このセットをもう一度全問解く", use_container_width=True): 
            restore_df = st.session_state.get('original_df', st.session_state.active_df).copy()
            st.session_state.update(active_df=restore_df, q_idx=0, correct_count=0, attempts=0, last_input="", wrong_df=pd.DataFrame(), clear_key=0, is_typo=False, history_saved=False)
            st.rerun()
        
    with c_retry2:
        if st.button("🔥 チェックした問題をリトライ", type="primary", use_container_width=True, disabled=st.session_state.wrong_df.empty):
            if not st.session_state.wrong_df.empty:
                start_quiz(st.session_state.wrong_df.reset_index(drop=True), is_error=st.session_state.is_error_mode, is_keyword=st.session_state.is_keyword_mode)
                
    # --- Suggestion for Keyword Search based on checked questions ---
    if not st.session_state.is_error_mode:
        st.divider()
        st.subheader("💡 出題された問題からキーワード特訓")
        st.markdown("気になった文法や表現（例: used to）を検索して、そのまま特訓を開始できます。")
        
        # 出題された問題の振り返り (英文と日本語を別々のアコーディオンに分割)
        with st.expander("👀 今回出題された問題の英文を確認", expanded=False):
            for i, row in f_df.iterrows():
                st.markdown(f"- **{row['English']}**")
                
        with st.expander("👀 今回出題された問題の日本語訳を確認", expanded=False):
            for i, row in f_df.iterrows():
                st.markdown(f"- {row['Japanese']}")
                
        # その場で検索・件数確認ができるミニ検索UI
        def on_mini_keyword_change(target):
            if target == "en": 
                st.session_state.mini_search_jp = ""
            else: 
                st.session_state.mini_search_en = ""

        mini_k_en = st.text_input("特訓したい英語キーワードを入力:", key="mini_search_en", placeholder="例: used to, look forward", on_change=on_mini_keyword_change, args=("en",))
        mini_k_jp = st.text_input("特訓したい日本語キーワードを入力:", key="mini_search_jp", placeholder="例: する予定, かもしれない", on_change=on_mini_keyword_change, args=("jp",))
        
        hit_df = pd.DataFrame()
        k_input = ""
        df = st.session_state.df_master
        
        if mini_k_en:
            hit_df = df[df['English'].str.contains(mini_k_en, case=False, na=False)].reset_index(drop=True)
            k_input = mini_k_en
        elif mini_k_jp:
            hit_df = df[df['Japanese'].str.contains(mini_k_jp, na=False)].reset_index(drop=True)
            k_input = mini_k_jp
            
        if k_input:
            if hit_df.empty:
                st.warning(f"❌ 「{k_input}」を含む問題は見つかりませんでした。別のキーワードを試してください。")
            else:
                st.success(f"✅ 「{k_input}」を含む問題が **{len(hit_df)} 問** 見つかりました。多すぎたり少なすぎる場合は、上の検索窓でキーワードを変えてみましょう。")
                def start_keyword_quiz_callback():
                    # 本格的な表現指定特訓モードのキーワード入力欄にも同期させる
                    st.session_state.search_keyword_en = mini_k_en
                    st.session_state.search_keyword_jp = mini_k_jp
                    start_quiz(hit_df, is_keyword=True, rerun=False)

                st.button(f"🚀 この {len(hit_df)} 問で特訓を開始する", type="primary", use_container_width=True, on_click=start_keyword_quiz_callback)
                
    # --- 次のDayがあれば進行ボタンを表示 ---
    if not st.session_state.is_error_mode and not st.session_state.is_keyword_mode:
        current_day = st.session_state.get('active_bd', 'すべて')
        if current_day != "すべて":
            df = st.session_state.df_master
            unique_days = df[['FY', 'B_Month', 'Week', 'Day']].drop_duplicates().values.tolist()
            fy, bm, bw = st.session_state.get('active_fy'), st.session_state.get('active_bm'), st.session_state.get('active_bw')
            
            current_idx = -1
            for i, (y, m, w, d) in enumerate(unique_days):
                if y == fy and m == bm and (bw == "すべて" or w == bw) and d == current_day:
                    current_idx = i
                    break
            
            if current_idx != -1 and current_idx + 1 < len(unique_days):
                next_y, next_m, next_w, next_d = unique_days[current_idx + 1]
                
                st.divider()
                st.subheader("⏭️ 続けて次のステップへ")
                
                label_extra = ""
                if next_y != fy or next_m != bm:
                    label_extra = f" ({next_y}年度 {next_m}月)"
                elif next_w != bw and bw != "すべて":
                    label_extra = f" ({next_w})"
                
                def start_next_day_callback():
                    st.session_state.active_fy = next_y
                    st.session_state.active_bm = next_m
                    st.session_state.active_bw = next_w
                    st.session_state.active_bd = next_d
                    q_str = f"FY=={next_y} and B_Month=={next_m} and Week=='{next_w}' and Day=='{next_d}'"
                    target_next_df = df.query(q_str).reset_index(drop=True)
                    start_quiz(target_next_df, rerun=False)

                st.button(f"🚀 Day{next_d}{label_extra} の特訓に進む", type="primary", use_container_width=True, on_click=start_next_day_callback)
            elif current_idx != -1 and current_idx + 1 >= len(unique_days):
                st.divider()
                st.success("現在の最新回まで到達しました")
    

    st.divider()
    c_back1, c_back2 = st.columns(2)
    
    with c_back1:
        if st.session_state.is_error_mode:
            if st.button("⏪ 弱点克服の設定に戻る", use_container_width=True):
                st.session_state.update(mode="ErrorFixSetup", is_error_mode=False, is_keyword_mode=False)
                st.rerun()
        elif st.session_state.is_keyword_mode:
            if st.button("⏪ 検索設定に戻る", use_container_width=True):
                st.session_state.update(mode="KeywordSearch", is_error_mode=False, is_keyword_mode=False)
                st.rerun()
        else:
            if st.button("📅 出題範囲の設定に戻る", use_container_width=True):
                st.session_state.update(mode="RangeSelect", is_error_mode=False, is_keyword_mode=False)
                st.rerun()

    with c_back2:
        if st.button("🏠 メニュー（Top）に戻る", use_container_width=True):
            st.session_state.update(mode="Top", is_error_mode=False, is_keyword_mode=False)
            st.rerun()

# --- 5. メインルーティング ---
def main():
    inject_custom_css()
    
    if 'df_master' not in st.session_state:
        st.session_state.df_master = load_and_process_data()
        
    if st.session_state.mode == "Top":
        render_top()
    elif st.session_state.mode == "History":
        render_history()
    elif st.session_state.mode == "RangeSelect":
        render_range_select()
    elif st.session_state.mode == "KeywordSearch":
        render_keyword_search()
    elif st.session_state.mode == "ErrorFixSetup":
        render_error_fix_setup()
    elif st.session_state.mode == "Quiz":
        render_quiz()

if __name__ == "__main__":
    main()
