import uuid
from datetime import datetime

import pandas as pd
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials


# ==============================
# Google Sheets 接続
# ==============================
@st.cache_resource
def get_gspread_client():
    credentials_info = st.secrets["gcp_service_account"]
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    credentials = Credentials.from_service_account_info(credentials_info, scopes=scopes)
    client = gspread.authorize(credentials)
    return client


@st.cache_resource
def get_worksheet():
    client = get_gspread_client()
    spreadsheet_id = st.secrets["spreadsheet_id"]
    sh = client.open_by_key(spreadsheet_id)

    try:
        ws = sh.worksheet("players")
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title="players", rows=1000, cols=20)
        ws.append_row(
            [
                "player_id",
                "name",
                "team",
                "skill",
                "initial_buyin",
                "rebuy_total",
                "rebuy_times",
                "final_stack",
                "created_at",
                "updated_at",
                "rebuy_history",
            ]
        )
    # rebuy_history 列が無かったら追加
    header = ws.row_values(1)
    if "rebuy_history" not in header:
        header.append("rebuy_history")
        ws.update("1:1", [header])

    return ws


# ==============================
# DataFrame 取得
# ==============================
@st.cache_data(ttl=5)
def load_players_df() -> pd.DataFrame:
    ws = get_worksheet()
    rows = ws.get_all_values()
    if len(rows) <= 1:
        return pd.DataFrame(
            columns=[
                "player_id",
                "name",
                "team",
                "skill",
                "initial_buyin",
                "rebuy_total",
                "rebuy_times",
                "final_stack",
                "created_at",
                "updated_at",
                "rebuy_history",
            ]
        )
    df = pd.DataFrame(rows[1:], columns=rows[0])

    numeric_cols = ["initial_buyin", "rebuy_total", "rebuy_times", "final_stack"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    if "rebuy_history" not in df.columns:
        df["rebuy_history"] = ""

    return df


# ==============================
# シート更新
# ==============================
def append_player_row(p: dict):
    ws = get_worksheet()
    now = datetime.utcnow().isoformat()
    ws.append_row(
        [
            p["player_id"],
            p["name"],
            p["team"],
            p["skill"],
            p["initial_buyin"],
            p["rebuy_total"],
            p["rebuy_times"],
            "",
            now,
            now,
            "",
        ]
    )
    load_players_df.clear()


def update_player_row(player_id: str, updates: dict):
    ws = get_worksheet()
    df = load_players_df()
    if player_id not in df["player_id"].values:
        return
    row_index = df.index[df["player_id"] == player_id][0]
    sheet_row = row_index + 2

    for k, v in updates.items():
        col_index = df.columns.get_loc(k) + 1
        ws.update_cell(sheet_row, col_index, "" if v is None else v)

    ws.update_cell(sheet_row, df.columns.get_loc("updated_at") + 1, datetime.utcnow().isoformat())
    load_players_df.clear()


def reset_players_sheet():
    ws = get_worksheet()
    ws.clear()
    ws.append_row(
        [
            "player_id",
            "name",
            "team",
            "skill",
            "initial_buyin",
            "rebuy_total",
            "rebuy_times",
            "final_stack",
            "created_at",
            "updated_at",
            "rebuy_history",
        ]
    )
    load_players_df.clear()


# ==============================
# Streamlit UI
# ==============================
st.set_page_config(page_title="ポーカー大会 収支集計アプリ", page_icon="🃏", layout="centered")

st.markdown(
    """
    <style>
    h1.main-title { font-size: 1.4rem; font-weight: 700; }
    h4.small-subheader { font-size: 0.95rem; font-weight: 700; margin: 0.5rem 0; }
    .player-card-container { background-color:#24293a; padding:0.6rem 0.9rem; border-radius:1rem; margin-bottom:0.4rem;}
    .player-card-name { color:white; font-size:1.05rem; font-weight:700; }
    .player-card-meta { color:#e5e7eb; font-size:0.85rem; }
    .player-separator { border-top:1px solid rgba(255,255,255,0.25); }
    </style>
    """,
    unsafe_allow_html=True,
)


def small_subheader(text: str):
    st.markdown(f"<h4 class='small-subheader'>{text}</h4>", unsafe_allow_html=True)


st.markdown("<h1 class='main-title'>ポーカー大会 収支集計アプリ</h1>", unsafe_allow_html=True)
st.caption("Buy-in（バイイン）、Re-buy（リバイ）を登録し、収支を自動で集計。")


df = load_players_df()


# ==============================
# プレイヤー登録 UI
# ==============================
st.header("1. プレイヤー登録")

with st.form("reg"):
    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input("プレイヤー名")
    with col2:
        team = st.selectbox("チーム", ["CSE", "RC"])

    col3, col4 = st.columns(2)
    with col3:
        skill = st.selectbox("スキル", ["初心者", "経験者"])
    with col4:
        initial_buyin = st.number_input("初期Buy-in", step=1000, min_value=0)

    submitted = st.form_submit_button("＋ 登録")

if submitted:
    if not name.strip():
        st.error("名前を入力してください")
    else:
        append_player_row(
            {
                "player_id": str(uuid.uuid4()),
                "name": name,
                "team": team,
                "skill": skill,
                "initial_buyin": initial_buyin,
                "rebuy_total": 0,
                "rebuy_times": 0,
            }
        )
        st.success(f"{name} を登録しました")
        st.rerun()


df = load_players_df()
st.metric("参加人数", len(df))


# ==============================
# プレイヤー一覧 & Rebuy管理
# ==============================
st.header("2. プレイヤー一覧・途中経過")
if df.empty:
    st.info("プレイヤーがまだ登録されていません。")
else:
    for i, (_, row) in enumerate(df.iterrows()):
        pid = row["player_id"]
        name = row["name"]
        rebuy_total = int(row["rebuy_total"])
        rebuy_times = int(row["rebuy_times"])
        history = row["rebuy_history"] or ""

        with st.container():
            st.markdown("<div class='player-card-container'>", unsafe_allow_html=True)
            st.markdown(f"<div class='player-card-name'>{name}</div>", unsafe_allow_html=True)
            st.markdown(
                f"<div class='player-card-meta'>Rebuy合計: {rebuy_total:,}（{rebuy_times}回）</div>",
                unsafe_allow_html=True,
            )

            col1, col2, col3 = st.columns([3, 2, 2])
            val = col1.number_input("", step=1000, min_value=0, key=f"rb_{pid}", label_visibility="collapsed")

            if col2.button("＋ Re-buy", key=f"rba_{pid}"):
                new_total = rebuy_total + val
                new_times = rebuy_times + 1
                new_history = f"{history},{val}" if history else str(val)
                update_player_row(pid, {"rebuy_total": new_total, "rebuy_times": new_times, "rebuy_history": new_history})
                st.rerun()

            if col3.button("↺ 取消", key=f"rbc_{pid}"):
                if not history:
                    st.warning("取り消す Re-buy がありません")
                else:
                    parts = [int(x) for x in history.split(",") if x]
                    last = parts.pop()
                    update_player_row(
                        pid,
                        {
                            "rebuy_total": rebuy_total - last,
                            "rebuy_times": rebuy_times - 1,
                            "rebuy_history": ",".join([str(x) for x in parts]),
                        },
                    )
                    st.success(f"{name} の Re-buy {last:,} を取消しました")
                st.rerun()

            st.markdown("</div>", unsafe_allow_html=True)

        if i < len(df) - 1:
            st.markdown("<hr class='player-separator' />", unsafe_allow_html=True)

st.markdown("---")


# ==============================
# 最終Stack登録
# ==============================
st.header("3. 最終Stack登録")

for _, row in df.iterrows():
    pid = row["player_id"]
    name = row["name"]
    val = int(row["final_stack"]) if not pd.isna(row["final_stack"]) else 0

    c1, c2, c3 = st.columns([3, 2, 2])
    c1.write(f"**{name}**")
    new_stack = c2.number_input("", value=val, step=1000, key=f"fs_{pid}", label_visibility="collapsed")
    if c3.button("登録", key=f"fsb_{pid}"):
        update_player_row(pid, {"final_stack": new_stack})
        st.success(f"{name} のStackを登録しました")
        st.rerun()

st.markdown("---")


# ==============================
# 集計 & ランキング
# ==============================
st.header("4. ランキング")

df_rank = df.copy()
df_rank["final_stack"] = pd.to_numeric(df_rank["final_stack"], errors="coerce")

missing = df_rank[df_rank["final_stack"].isna()]["name"].tolist()
if missing:
    st.error("最終Stack未入力: " + ", ".join(missing))

df_rank = df_rank.dropna(subset=["final_stack"])
if len(df_rank) == 0:
    st.info("まだランキングを計算できません。")
    st.stop()

df_rank["profit"] = df_rank["final_stack"] - (df_rank["initial_buyin"] + df_rank["rebuy_total"])

def handicap(row):
    p = row["profit"]
    if p >= 0:
        return int(p * 2) if row["skill"] == "初心者" else int(p * 0.5)
    else:
        return int(p * 0.5) if row["skill"] == "初心者" else int(p * 2)

df_rank["handicap_profit"] = df_rank.apply(handicap, axis=1)

# ---- 個人
small_subheader("個人ランキング（素点収支）")
st.dataframe(
    df_rank.sort_values("profit", ascending=False)[["name", "skill", "team", "profit"]]
    .rename(columns={"name": "プレイヤー", "skill": "スキル", "team": "チーム", "profit": "素点収支"}),
    use_container_width=True,
)

small_subheader("個人ランキング（handicap収支）")
st.dataframe(
    df_rank.sort_values("handicap_profit", ascending=False)[
        ["name", "skill", "team", "handicap_profit"]
    ].rename(
        columns={
            "name": "プレイヤー",
            "skill": "スキル",
            "team": "チーム",
            "handicap_profit": "handicap収支",
        }
    ),
    use_container_width=True,
)


# ---- チーム集計
group_score = df_rank.groupby("team", as_index=False).agg(
    {"profit": "sum", "handicap_profit": "sum"}
)

small_subheader("チームランキング（素点収支）")
st.dataframe(
    group_score.sort_values("profit", ascending=False)
    .rename(columns={"team": "チーム", "profit": "素点収支"}),
    use_container_width=True,
)

small_subheader("チームランキング（handicap収支）")
st.dataframe(
    group_score.sort_values("handicap_profit", ascending=False)
    .rename(columns={"team": "チーム", "handicap_profit": "handicap収支"}),
    use_container_width=True,
)

st.markdown("---")


# ==============================
# リセット
# ==============================
st.subheader("データリセット（注意）")
with st.expander("データをリセット（元に戻せません）"):
    if st.button("全データ削除"):
        reset_players_sheet()
        st.success("データをリセットしました")
        st.rerun()
