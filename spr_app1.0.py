import streamlit as st
import pandas as pd
import re
import io
from gtts import gTTS

# --- 1. データ読み込み ---
SHEET_ID = "1usIv38xEO6KLAi3x8jxuZPuIgimQ0FUd4NEeeZPjVpA"
GID = "2094303905"
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID}"

@st.cache_data(ttl=3600)
def load_and_process_data():
    df = pd.read_csv(CSV_URL).iloc[:, 0:8]
    df.columns = ['Date','Week','Day','No','Japanese','Listening','English', 'Explanation']
    df['Date_dt'] = pd.to_datetime(df['Date'], errors='coerce')

    def get_broadcast_info(row):
        dt = row['Date_dt']
        if pd.isnull(dt): return 0, 0
        is_w1 = str(row['Week']).strip().upper() == 'W1'
        b_month, b_year = (dt.month + 1, dt.year) if (is_w1 and dt.day >= 21) else (dt.month, dt.year)
        if b_month > 12: b_month, b_year = 1, b_year + 1
        fy = b_year if b_month >= 4 else b_year - 1
        return fy, b_month

    info = df.apply(get_broadcast_info, axis=1, result_type='expand')
    df['FY'], df['B_Month'] = info[0].astype(int), info[1].astype(int)
    
    for col in ['Week','Day','Japanese','Listening','English', 'Explanation']:
        df[col] = df[col].astype(str).str.strip()
    return df.dropna(subset=['English']).reset_index(drop=True)

df = load_and_process_data()

# --- 2. 状態管理 ---
defaults = [
    ('mode','Top'), ('active_df',pd.DataFrame()), ('wrong_df',pd.DataFrame()),
    ('q_idx',0), ('attempts',0), ('correct_count',0), ('last_input',''),
    ('used_ids',[]), ('is_error_mode',False), ('is_keyword_mode', False), ('confirm_exit',False), ('clear_key', 0),
    ('search_keyword_en', ''), ('search_keyword_jp', ''),
    ('error_order','ランダム（件数指定）'), ('error_count',10), ('error_days', 5)
]
for key, val in defaults:
    if key not in st.session_state: st.session_state[key] = val

def start_quiz(target_df, is_error=False, is_keyword=False):
    st.session_state.update(
        mode="Quiz", active_df=target_df, q_idx=0, correct_count=0, 
        attempts=0, last_input="", wrong_df=pd.DataFrame(), 
        is_error_mode=is_error, is_keyword_mode=is_keyword, clear_key=0, confirm_exit=False
    )
    st.rerun()

# --- 3. 判定ロジック ---
def clean(text):
    return re.sub(r'[^a-zA-Z0-9]', '', str(text).strip().lower())

def check_answer(idx):
    row = st.session_state.active_df.iloc[idx]
    user_input = st.session_state.get(f"ans_{idx}_{st.session_state.clear_key}", "")
    st.session_state.last_input = user_input
    if clean(user_input) == clean(row['English']):
        st.session_state.correct_count += 1
        st.session_state.attempts = 10
    else:
        st.session_state.attempts += 1
        if st.session_state.attempts >= 4:
            st.session_state.wrong_df = pd.concat([st.session_state.wrong_df, row.to_frame().T]).drop_duplicates()

# --- 4. 画面遷移 ---
if st.session_state.mode == "Top":
    st.title("SPR Training Center")
    st.write("未来人サイジョー、今日はどの特訓をするざんす？")
    c1, c2 = st.columns(2)
    if c1.button("🇯🇵 → 🇺🇸 通常クイズ", use_container_width=True): st.session_state.mode = "RangeSelect"; st.rerun()
    if c2.button("👂 聞き間違いを修正", use_container_width=True): st.session_state.mode = "ErrorFixSetup"; st.rerun()
    st.divider()
    if st.button("🔍 表現指定特訓 (キーワード検索)", use_container_width=True): st.session_state.mode = "KeywordSearch"; st.rerun()

elif st.session_state.mode == "RangeSelect":
    st.title("📅 出題範囲の設定")
    with st.expander("設定", expanded=True):
        if st.button("最新回の設定を読み込む"):
            latest = df.iloc[-1]
            st.session_state.update(fy_sel=latest['FY'], bm_sel=latest['B_Month'], bw_sel=latest['Week'], bd_sel=latest['Day']); st.rerun()
        c1, c2 = st.columns(2)
        s_fy = c1.selectbox("年度 (FY)", sorted(df['FY'].unique(), reverse=True), key="fy_sel")
        s_bm = c1.selectbox("月", sorted(df[df['FY']==s_fy]['B_Month'].unique()), key="bm_sel")
        s_bw = c2.selectbox("週 (Week)", sorted(df[(df['FY']==s_fy)&(df['B_Month']==s_bm)]['Week'].unique()), key="bw_sel")
        day_opts = sorted(df[(df['FY']==s_fy)&(df['B_Month']==s_bm)&(df['Week']==s_bw)]['Day'].unique().tolist())
        s_bd = c2.selectbox("Day", ["すべて"] + day_opts, key="bd_sel")
        
        q = f"FY=={s_fy} and B_Month=={s_bm} and Week=='{s_bw}'" + (f" and Day=='{s_bd}'" if s_bd!="すべて" else "")
        if st.button("🚀 通常クイズを開始"): start_quiz(df.query(q).reset_index(drop=True))
    if st.button("🏠 戻る"): st.session_state.mode="Top"; st.rerun()

elif st.session_state.mode == "KeywordSearch":
    st.title("🔍 表現指定特訓")
    
    def on_keyword_change(target):
        if target == "en": st.session_state.search_keyword_jp = ""
        else: st.session_state.search_keyword_en = ""

    c1, c2 = st.columns(2)
    k_en = c1.text_input("🇺🇸 英語で検索", key="search_keyword_en", on_change=on_keyword_change, args=("en",))
    k_jp = c2.text_input("🇯🇵 日本語で検索", key="search_keyword_jp", on_change=on_keyword_change, args=("jp",))
    
    target_df, k_input = pd.DataFrame(), ""
    if k_en:
        target_df, k_input = df[df['English'].str.contains(k_en, case=False, na=False)].reset_index(drop=True), k_en
    elif k_jp:
        target_df, k_input = df[df['Japanese'].str.contains(k_jp, na=False)].reset_index(drop=True), k_jp

    if k_input:
        st.info(f"「{k_input}」を含む問題が {len(target_df)} 問見つかったざんす。")
        if not target_df.empty and st.button("🚀 特訓を開始する", use_container_width=True): start_quiz(target_df, is_keyword=True)
    if st.button("🏠 戻る"): st.session_state.mode="Top"; st.rerun()

elif st.session_state.mode == "ErrorFixSetup":
    st.title("👂 Fix Your Hearing!")
    pool = df[(df['English']!=df['Listening']) & (df['Listening'].str.len() > 0) & (df['Listening']!="nan")].reset_index(drop=True)
    available = pool[~pool.index.isin(st.session_state.used_ids)]
    if available.empty:
        st.success("全て修正完了！")
        if st.button("リセット"): st.session_state.used_ids=[]; st.rerun()
    else:
        st.write(f"残り {len(available)} 問ざんす。")
        order = st.selectbox("出題方法", ["ランダム（件数指定）", "最新順から（日数指定）", "古い順から（日数指定）"], key="error_order")
        val = st.number_input("数/日数", 1, 365, value=10)
        if st.button("🔥 特訓開始"):
            if "ランダム" in order: res = available.sample(n=min(val, len(available)))
            else:
                dates = sorted(available['Date_dt'].unique(), reverse="最新" in order)[:val]
                res = available[available['Date_dt'].isin(dates)].sort_values("Date_dt", ascending="最新" not in order)
            start_quiz(res.reset_index(drop=True), is_error=True)
    if st.button("🏠 戻る"): st.session_state.mode="Top"; st.rerun()

elif st.session_state.mode == "Quiz":
    f_df = st.session_state.active_df
    if st.session_state.q_idx < len(f_df):
        row = f_df.iloc[st.session_state.q_idx]
        is_err = st.session_state.is_error_mode
        st.caption(f"Problem {st.session_state.q_idx+1}/{len(f_df)} ({row['Date']} No.{row['No']})")
        st.subheader("👂 聞き間違い修正！" if is_err else f"Q: {row['Japanese']}")
        
        locked = st.session_state.attempts in [4, 10]
        
        with st.form(key=f"q_{st.session_state.q_idx}_{st.session_state.clear_key}"):
            ans = st.text_input(
                f"解答 ({min(st.session_state.attempts+1, 4)}/4)", 
                value=row['Listening'] if (is_err and st.session_state.attempts==0) else st.session_state.last_input, 
                key=f"ans_{st.session_state.q_idx}_{st.session_state.clear_key}", 
                disabled=locked
            )
            
            if st.form_submit_button("判定", use_container_width=True, disabled=locked):
                if not locked:
                    check_answer(st.session_state.q_idx)
                    st.rerun()
                
            if st.form_submit_button("クリア", use_container_width=True, disabled=locked):
                if not locked:
                    st.session_state.update(last_input="", clear_key=st.session_state.clear_key+1)
                    st.rerun()
                
            if st.form_submit_button("次の問題へ", use_container_width=True):
                if st.session_state.attempts < 4: 
                    st.session_state.wrong_df = pd.concat([st.session_state.wrong_df, row.to_frame().T]).drop_duplicates()
                st.session_state.update(q_idx=st.session_state.q_idx+1, attempts=0, last_input="", clear_key=0)
                st.rerun()

        if 1 <= st.session_state.attempts <= 3:
            target_ws, user_ws = row['English'].split(), st.session_state.last_input.split()
            hint = [w if (clean(w)==(clean(user_ws[i]) if i<len(user_ws) else "") or (st.session_state.attempts>=2 and (i==0 or w[0].isupper()))) else "_"*len(w) for i, w in enumerate(target_ws)]
            st.info(f"💡 ヒント: {' '.join(hint)}")
        
        if st.session_state.attempts >= 3:
            fp = io.BytesIO(); gTTS(text=row['English'], lang='en').write_to_fp(fp); fp.seek(0)
            st.audio(fp)

        if locked:
            if st.session_state.attempts==10:
                st.success(f"✨ 正解!: {row['English']}")
                if is_err and row.name not in st.session_state.used_ids: st.session_state.used_ids.append(row.name)
            else: 
                st.error(f"❌ 正解は: {row['English']}")
            if is_err and str(row['Explanation']).strip() not in ["", "nan"]: 
                st.info(f"📖 {row['Explanation']}")

        st.divider()
        if not st.session_state.confirm_exit:
            if st.button("中止してメニューへ"): 
                st.session_state.confirm_exit=True
                st.rerun()
        else:
            st.warning("本当に中止しますか？")
            c1, c2 = st.columns(2)
            if c1.button("はい"): 
                st.session_state.update(mode="Top", is_error_mode=False, is_keyword_mode=False, confirm_exit=False)
                st.rerun()
            if c2.button("いいえ"): 
                st.session_state.confirm_exit=False
                st.rerun()
    else:
        st.header("🏁 特訓終了")
        st.metric("正解数", f"{st.session_state.correct_count}/{len(f_df)}")
        
        c1, c2 = st.columns(2)
        if c1.button("🔄 全問リトライ", use_container_width=True): 
            st.session_state.update(q_idx=0, correct_count=0, attempts=0, last_input="", wrong_df=pd.DataFrame(), clear_key=0); st.rerun()
        if c2.button("🔥 ミスのみリトライ", use_container_width=True) and not st.session_state.wrong_df.empty:
            start_quiz(st.session_state.wrong_df.reset_index(drop=True), is_error=st.session_state.is_error_mode, is_keyword=st.session_state.is_keyword_mode)
            
        st.divider()
        
        # モードに合わせて戻り先を判定
        if st.session_state.is_error_mode:
            btn_label, back_mode = "👂 出題設定（Fix Your Hearing）に戻る", "ErrorFixSetup"
        elif st.session_state.is_keyword_mode:
            btn_label, back_mode = "🔍 検索画面（表現指定特訓）に戻る", "KeywordSearch"
        else:
            btn_label, back_mode = "📅 出題範囲の設定に戻る", "RangeSelect"

        if st.button(btn_label, use_container_width=True):
            st.session_state.update(mode=back_mode, is_error_mode=False, is_keyword_mode=False)
            st.rerun()
            
        if st.button("🏠 メニュー（Top）に戻る", use_container_width=True):
            st.session_state.update(mode="Top", is_error_mode=False, is_keyword_mode=False)
            st.rerun()
