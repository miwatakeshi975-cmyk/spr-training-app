import streamlit as st
import pandas as pd
import re
import io
from gtts import gTTS

# --- 1. データ読み込み ---
SHEET_ID = "1usIv38xEO6KLAi3x8jxuZPuIgimQ0FUd4NEeeZPjVpA"
GID = "2094303905"
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID}"

@st.cache_data
def load_and_process_data():
    df = pd.read_csv(CSV_URL)
    df.rename(columns={'English(original)': 'Listening','English': 'English'}, inplace=True)
    df = df.iloc[:,0:7]
    df.columns = ['Date','Week','Day','No','Japanese','Listening','English']
    df['Date_dt'] = pd.to_datetime(df['Date'], errors='coerce')

    def get_broadcast_info(row):
        dt = row['Date_dt']
        if pd.isnull(dt): return 0,0
        is_w1 = str(row['Week']).strip().upper() == 'W1'
        if is_w1 and dt.day >= 21:
            b_month = dt.month + 1
            b_year = dt.year
            if b_month > 12:
                b_month = 1
                b_year += 1
        else:
            b_month = dt.month
            b_year = dt.year
        fy = b_year if b_month >= 4 else b_year - 1
        return fy,b_month

    broadcast_info = df.apply(lambda r: pd.Series(get_broadcast_info(r)), axis=1)
    df['FY'] = broadcast_info[0].astype(int)
    df['B_Month'] = broadcast_info[1].astype(int)

    for col in ['Week','Day','Japanese','Listening','English']:
        df[col] = df[col].astype(str).str.strip()
    return df.dropna(subset=['English']).reset_index(drop=True)

df = load_and_process_data()

# --- 2. 状態管理 ---
for key, default in [
    ('mode','Top'), ('active_df',pd.DataFrame()), ('wrong_df',pd.DataFrame()),
    ('q_idx',0), ('attempts',0), ('correct_count',0), ('last_input',''),
    ('used_ids',[]), ('is_error_mode',False),
    ('error_order','ランダム'), ('error_count',10),
    ('confirm_exit',False)
]:
    if key not in st.session_state:
        st.session_state[key] = default

# --- 3. 判定ロジック ---
def clean(text):
    return re.sub(r'[^a-zA-Z0-9]', '', str(text).strip().lower())

def check_answer(idx):
    row = st.session_state.active_df.iloc[idx]
    user_input = st.session_state.get(f"ans_{idx}", "")
    target_en = str(row['English'])
    st.session_state.last_input = user_input
    if clean(user_input) == clean(target_en):
        st.session_state.correct_count += 1
        st.session_state.attempts = 10
    else:
        st.session_state.attempts += 1
        if st.session_state.attempts >= 4:
            st.session_state.wrong_df = pd.concat([st.session_state.wrong_df,row.to_frame().T]).drop_duplicates()

# --- 4. トップメニュー ---
if st.session_state.mode == "Top":
    st.title("SPR Training Center")
    st.write("未来人サイジョー、今日はどの特訓をするざんす？")
    col1,col2 = st.columns(2)
    with col1:
        if st.button("🇯🇵 → 🇺🇸 通常クイズ", use_container_width=True):
            st.session_state.mode = "RangeSelect"; st.rerun()
    with col2:
        if st.button("👂 聞き間違いを修正", use_container_width=True):
            st.session_state.mode = "ErrorFixSetup"; st.rerun()

# --- 5. 通常モード範囲設定 ---
elif st.session_state.mode=="RangeSelect":
    st.title("SPR Training (Normal Mode)")
    with st.expander("📅 出題範囲の設定", expanded=True):
        if st.button("最新回の設定を読み込む"):
            latest = df.iloc[-1]
            st.session_state.update(
                fy_sel=latest['FY'], bm_sel=latest['B_Month'],
                bw_sel=latest['Week'], bd_sel=latest['Day']
            ); st.rerun()
        col1,col2 = st.columns(2)
        with col1:
            s_fy = st.selectbox("年度 (FY)", sorted(df['FY'].unique(), reverse=True), key="fy_sel")
            s_bm = st.selectbox("月", sorted(df[df['FY']==s_fy]['B_Month'].unique()), key="bm_sel")
        with col2:
            s_bw = st.selectbox("週 (Week)", sorted(df[(df['FY']==s_fy)&(df['B_Month']==s_bm)]['Week'].unique()), key="bw_sel")
            day_opts = sorted(df[(df['FY']==s_fy)&(df['B_Month']==s_bm)&(df['Week']==s_bw)]['Day'].unique().tolist())
            s_bd = st.selectbox("Day", ["すべて"]+day_opts, key="bd_sel")
        temp_df = df.query(
            f"FY=={s_fy} and B_Month=={s_bm} and Week=='{s_bw}'"
            + (f" and Day=='{s_bd}'" if s_bd!="すべて" else "")
        ).reset_index(drop=True)
        if st.button("🚀 通常クイズを開始"):
            st.session_state.update(
                mode="Quiz", active_df=temp_df, q_idx=0,
                correct_count=0, attempts=0, last_input="",
                wrong_df=pd.DataFrame(), is_error_mode=False
            ); st.rerun()
    if st.button("🏠 戻る"): st.session_state.mode="Top"; st.rerun()

# --- 6. 聞き間違い修正モード ---
elif st.session_state.mode=="ErrorFixSetup":
    st.title("👂 Fix Your Hearing!")
    error_pool = df[(df['English']!=df['Listening']) & (df['Listening']!="") & (df['Listening']!="nan")].reset_index(drop=True)
    available_pool = error_pool[~error_pool.index.isin(st.session_state.used_ids)]
    if available_pool.empty:
        st.success("全ての問題を修正し尽くしたざんす！")
        if st.button("既出リストをリセットして再挑戦"): st.session_state.used_ids=[]; st.rerun()
        if st.button("🏠 戻る"): st.session_state.mode="Top"; st.rerun()
    else:
        st.write(f"現在、修正可能な聞き間違いが {len(available_pool)} 問あるざんす。")
        order = st.selectbox("出題方法を選択してください", ["ランダム","最新順","古い順"], key="error_order")
        max_q = len(available_pool)
        count = st.number_input(f"何問出題するざんすか？ (最大 {max_q})", 1, max_q, value=min(10,max_q), key="error_count")
        if st.button("🔥 特訓開始"):
            if order=="ランダム": temp_df=available_pool.sample(n=int(count)).reset_index(drop=True)
            elif order=="最新順": temp_df=available_pool.sort_values("Date_dt", ascending=False).head(int(count)).reset_index(drop=True)
            else: temp_df=available_pool.sort_values("Date_dt", ascending=True).head(int(count)).reset_index(drop=True)
            st.session_state.update(
                mode="Quiz", active_df=temp_df, q_idx=0,
                correct_count=0, attempts=0, last_input="",
                wrong_df=pd.DataFrame(), is_error_mode=True
            ); st.rerun()
    if st.button("🏠 戻る"): st.session_state.mode="Top"; st.rerun()

# --- 7. クイズ画面 ---
elif st.session_state.mode=="Quiz":
    f_df = st.session_state.active_df
    is_error_mode = st.session_state.get('is_error_mode', False)
    if st.session_state.q_idx < len(f_df):
        row = f_df.iloc[st.session_state.q_idx]
        target_en = str(row['English'])
        st.caption(f"Problem {st.session_state.q_idx+1}/{len(f_df)} (Date: {row['Date']}, No.{row['No']})")
        st.subheader("👂 聞き間違いを修正するざんす！" if is_error_mode else f"Q: {row['Japanese']}")
        default_val = row['Listening'] if is_error_mode and st.session_state.attempts==0 else st.session_state.last_input
        is_locked = st.session_state.attempts==10 or st.session_state.attempts>=4

        with st.form(key=f"form_{st.session_state.q_idx}", clear_on_submit=False):
            user_input = st.text_input(
                f"解答 ({min(st.session_state.attempts+1,4)}/4回目)",
                value=default_val,
                key=f"ans_{st.session_state.q_idx}",
                disabled=is_locked
            )
            col1,col2 = st.columns(2)
            with col1: submit_btn = st.form_submit_button("判定")
            with col2: next_btn = st.form_submit_button("次の問題へ")

            if submit_btn and not is_locked: check_answer(st.session_state.q_idx); st.rerun()
            if next_btn:
                if st.session_state.attempts<4: st.session_state.wrong_df=pd.concat([st.session_state.wrong_df,row.to_frame().T]).drop_duplicates()
                st.session_state.update(q_idx=st.session_state.q_idx+1, attempts=0, last_input=""); st.rerun()

        if 1<=st.session_state.attempts<=3:
            target_ws = target_en.split()
            user_ws = st.session_state.last_input.split()
            hint = [cw if (clean(cw)==(clean(user_ws[i]) if i<len(user_ws) else "") or (st.session_state.attempts>=2 and (i==0 or cw[0].isupper()))) else "_"*len(cw) for i,cw in enumerate(target_ws)]
            st.info(f"💡 ヒント: {' '.join(hint)}")

        if st.session_state.attempts>=3:
            tts = gTTS(text=target_en, lang='en')
            fp = io.BytesIO(); tts.write_to_fp(fp); fp.seek(0)
            st.audio(fp)

        if is_locked:
            if st.session_state.attempts==10:
                st.success(f"✨ 正解！: {target_en}")
                if is_error_mode and row.name not in st.session_state.used_ids: st.session_state.used_ids.append(row.name)
            else:
                st.error(f"❌ 残念！正解は: {target_en}")

        # 中止確認
        if not st.session_state.confirm_exit:
            if st.button("中止してメニューへ"):
                st.session_state.confirm_exit=True; st.rerun()
        else:
            st.warning("本当に中止しますか？")
            c1,c2 = st.columns(2)
            with c1:
                if st.button("はい"):
                    st.session_state.update(mode="Top", is_error_mode=False, confirm_exit=False); st.rerun()
            with c2:
                if st.button("いいえ"):
                    st.session_state.confirm_exit=False; st.rerun()

    else:
        st.header("🏁 特訓終了")
        st.metric(label="正解数", value=f"{st.session_state.correct_count}/{len(f_df)}")
        col1,col2 = st.columns(2)
        with col1:
            if st.button("🔄 全問リトライ"): st.session_state.update(q_idx=0, correct_count=0, attempts=0, last_input="", wrong_df=pd.DataFrame()); st.rerun()
        with col2:
            if not st.session_state.wrong_df.empty:
                if st.button("🔥 間違えた問題だけをリトライ"):
                    st.session_state.update(
                        active_df=st.session_state.wrong_df.reset_index(drop=True),
                        q_idx=0, correct_count=0, attempts=0, last_input="", wrong_df=pd.DataFrame()
                    ); st.rerun()
        if st.button("🏠 メニューに戻る"): st.session_state.update(mode="Top", is_error_mode=False); st.rerun()