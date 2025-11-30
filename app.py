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
                "player_id", "name", "team", "skill",
                "initial_buyin", "rebuy_total", "rebuy_times", "final_stack",
                "created_at", "updated_at", "rebuy_history"
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
# 行操作（追加・更新・削除）
# ==============================
def append_player_row(p: dict):
    ws = get_worksheet()
    now = datetime.utcnow().isoformat()
    ws.append_row(
        [
            p["player_id"], p["name"], p["team"], p["skill"], p["initial_buyin"],
            p["rebuy_total"], p["rebuy_times"], "", now, now, ""
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
        if k not in df.columns:
            continue
        col_index = df.columns.get_loc(k) + 1
        ws.update_cell(sheet_row, col_index, "" if v is None else v)

    ws.update_cell(sheet_row, df.columns.get_loc("updated_at") + 1, datetime.utcnow().isoformat())
    load_players_df.clear()


# ==============================
# ★ delete_player_row（改善版）
# ==============================
def delete_player_row(player_id: str):
    ws = get_worksheet()
    df = load_players_df()
    if player_id not in df["player_id"].values:
        return

    row_index = int(df.index[df["player_id"] == player_id][0])
    sheet_row = int(row_index + 2)

    ws.delete_rows(sheet_row)
    load_players_df.clear()

    st.success("プレイヤーを削除しました")
    st.rerun()


def reset_players_sheet():
    ws = get_worksheet()
    ws.clear()
    ws.append_row(
        [
            "player_id", "name", "team", "skill",
            "initial_buyin", "rebuy_total", "rebuy_times", "final_stack",
            "created_at", "updated_at", "rebuy_history"
        ]
    )
    load_players_df.clear()


# ==============================
# Streamlit UI
# ==============================
st.set_page_config(page_title="ポーカー大会 収支集計アプリ", page_icon="🃏", layout="centered")


# 🎨 CSS：ライト/ダーク両対応
st.markdown(
    """
    <style>
    :root {
        --color-bg-dark: #24293a;
        --color-bg-light: #ffffff;
        --color-text-dark: #ffffff;
        --color-text-light: #111827;
        --color-divider-dark: rgba(255,255,255,0.25);
        --color-divider-light: rgba(0,0,0,0.20);
    }

    @media (prefers-color-scheme: dark) {
        .player-card-container { background-color: var(--color-bg-dark); }
        .player-card-name { color: var(--color-text-dark); }
        .player-card-meta { color:#e5e7eb; }
        .player-separator { border-top:1px solid var(--color-divider-dark); }
    }
    @media (prefers-color-scheme: light) {
        .player-card-container { background-color: var(--color-bg-light); }
        .player-card-name { color: var(--color-text-light); }
        .player-card-meta { color:#374151; }
        .player-separator { border-top:1px solid var(--color-divider-light); }
    }

    h1.main-title { font-size: 1.35rem; font-weight: 700; }
    h4.small-subheader { font-size: 0.9rem; font-weight: 700; margin: 0.5rem 0; }

    .player-card-container {
        padding:0.55rem 0.8rem;
        border-radius:1rem;
        margin-bottom:0.35rem;
    }

    .badge {
        display:inline-block;
        padding:0.05rem 0.55rem;
        border-radius:999px;
        font-size:0.7rem;
        margin-left:0.25rem;
    }
    .badge-team-cse {
        border-color:#3b82f6; color:#3b82f6; background-color:rgba(59,130,246,0.12);
    }
    .badge-team-rc {
        border-color:#f97316; color:#f97316; background-color:rgba(249,115,22,0.12);
    }
    .badge-skill-beginner {
        border-color:#22c55e; color:#22c55e; background-color:rgba(34,197,94,0.12);
    }
    .badge-skill-expert {
        border-color:#facc15; color:#facc15; background-color:rgba(250,204,21,0.12);
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def small_subheader(text: str):
    st.markdown(f"<h4 class='small-subheader'>{text}</h4>", unsafe_allow_html=True)



# Title & Rule
st.markdown("<h1 class='main-title'>ポーカー大会 収支集計アプリ</h1>", unsafe_allow_html=True)
st.caption("Buy-in（バイイン）、Re-buy（リバイ）を登録し、収支を自動で集計。")

df = load_players_df()


st.markdown(
    """
**ルール：**

- 個人順位、チーム順位（CSE / RC）を集計  
- handicap：経験者は最終持ち点を半分（マイナスは2倍）／初心者は最終持ち点を2倍（マイナスは半分）  
- 素点収支集計 & handicap収支集計を表示  
"""
)


# ==============================
# 1. プレイヤー登録
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
                "name": name.strip(),
                "team": team,
                "skill": skill,
                "initial_buyin": int(initial_buyin),
                "rebuy_total": 0,
                "rebuy_times": 0,
            }
        )
        st.success(f"{name} を登録しました")
        st.rerun()


df = load_players_df()
st.metric("参加人数", len(df))

st.markdown("---")


# ==============================
# 2. プレイヤー一覧
# ==============================
st.header("2. プレイヤー一覧・途中経過")

if df.empty:
    st.info("プレイヤーがまだ登録されていません。")
else:
    for i, (_, row) in enumerate(df.iterrows()):
        pid = row["player_id"]
        name = row["name"]
        team = row["team"]
        skill = row["skill"]
        rebuy_total = int(row["rebuy_total"]) if not pd.isna(row["rebuy_total"]) else 0
        rebuy_times = int(row["rebuy_times"]) if not pd.isna(row["rebuy_times"]) else 0
        final_stack = (
            None if pd.isna(row["final_stack"]) or row["final_stack"] == "" else int(row["final_stack"])
        )
        history = row["rebuy_history"] or ""

        with st.container():
            st.markdown("<div class='player-card-container'>", unsafe_allow_html=True)

            c_name, c_badge = st.columns([3,2])
            with c_name:
                st.markdown(f"<div class='player-card-name'>{name}</div>", unsafe_allow_html=True)
                st.markdown(
                    f"<div class='player-card-meta'>"
                    f"Re-buy合計: {rebuy_total:,}（{rebuy_times}回）　"
                    f"最終Stack: {('未入力' if final_stack is None else f'{final_stack:,}')}"
                    f"</div>",
                    unsafe_allow_html=True,
                )

            with c_badge:
                team_class = "badge-team-cse" if team == "CSE" else "badge-team-rc"
                skill_class = "badge-skill-beginner" if skill == "初心者" else "badge-skill-expert"
                st.markdown(
                    f"<div style='text-align:right;'>"
                    f"<span class='badge {team_class}'>{team}</span>"
                    f"<span class='badge {skill_class}'>{skill}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

            col1, col2, col3 = st.columns([3,2,2])
            rebuy_val = col1.number_input(
                "",
                step=1000, min_value=0,
                key=f"rb_{pid}",
                label_visibility="collapsed"
            )

            if col2.button("＋ Re-buy", key=f"rba_{pid}"):
                if rebuy_val <= 0:
                    st.warning("Re-buy額は正の数を入力してください")
                else:
                    new_total = rebuy_total + int(rebuy_val)
                    new_times = rebuy_times + 1
                    new_history = f"{history},{int(rebuy_val)}" if history else str(int(rebuy_val))
                    update_player_row(
                        pid,
                        {"rebuy_total": new_total, "rebuy_times": new_times, "rebuy_history": new_history},
                    )
                    st.success(f"{name} に Re-buy {int(rebuy_val):,} を追加しました")
                    st.rerun()

            if col3.button("↺ 直近Re-buy取消", key=f"rbc_{pid}"):
                if not history:
                    st.warning("取り消す Re-buy がありません")
                else:
                    parts = [int(x) for x in history.split(",") if x]
                    if not parts:
                        st.warning("取り消す Re-buy がありません")
                    else:
                        last = parts.pop()
                        new_history = ",".join(str(x) for x in parts)
                        new_total = rebuy_total - last
                        new_times = rebuy_times - 1
                        update_player_row(
                            pid,
                            {
                                "rebuy_total": max(new_total,0),
                                "rebuy_times": max(new_times,0),
                                "rebuy_history": new_history,
                            },
                        )
                        st.success(f"{name} の Re-buy {last:,} を取消しました")
                        st.rerun()

            col_sp, col_del = st.columns([5,1])
            with col_del:
                del_key = f"confirm_delete_{pid}"
                if st.button("🗑 削除", key=f"del_{pid}"):
                    if not st.session_state.get(del_key, False):
                        st.session_state[del_key] = True
                        st.warning(f"{name} を削除しますか？もう一度ボタンを押すと削除されます。")
                    else:
                        delete_player_row(pid)

            st.markdown("</div>", unsafe_allow_html=True)

        if i < len(df) - 1:
            st.markdown("<hr class='player-separator' />", unsafe_allow_html=True)


st.markdown("---")


# ==============================
# 3. 最終Stack登録
# ==============================
st.header("3. 最終Stack登録")

if df.empty:
    st.info("プレイヤーがまだ登録されていません。")
else:
    for _, row in df.iterrows():
        pid = row["player_id"]
        name = row["name"]
        val = int(row["final_stack"]) if not pd.isna(row["final_stack"]) else 0

        c1, c2, c3 = st.columns([3,2,2])
        c1.write(f"**{name}**")
        new_stack = c2.number_input(
            "",
            value=val, step=1000,
            key=f"fs_{pid}",
            label_visibility="collapsed"
        )
        if c3.button("登録", key=f"fsb_{pid}"):
            update_player_row(pid, {"final_stack": int(new_stack)})
            st.success(f"{name} のStackを登録しました")
            st.rerun()

st.markdown("---")


# ==============================
# 4. ランキング + メダル色
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
else:
    df_rank["initial_buyin"] = pd.to_numeric(df_rank["initial_buyin"], errors="coerce").fillna(0)
    df_rank["rebuy_total"] = pd.to_numeric(df_rank["rebuy_total"], errors="coerce").fillna(0)

    df_rank["profit"] = df_rank["final_stack"] - (
        df_rank["initial_buyin"] + df_rank["rebuy_total"]
    )

    def handicap(row):
        p = row["profit"]
        if pd.isna(p):
            return None
        if p >= 0:
            return int(p * 2) if row["skill"] == "初心者" else int(p * 0.5)
        else:
            return int(p * 0.5) if row["skill"] == "初心者" else int(p * 2)

    df_rank["handicap_profit"] = df_rank.apply(handicap, axis=1)


    # === メダル色適用関数 ===
    def apply_medal_colors(df):
        def style_row(row):
            idx = row.name
            if idx == 0:
                return ['background-color: #FFD700; color:black'] * len(row)
            elif idx == 1:
                return ['background-color: #C0C0C0; color:black'] * len(row)
            elif idx == 2:
                return ['background-color: #CD7F32; color:white'] * len(row)
            return [''] * len(row)
        return df.style.apply(style_row, axis=1)


    # 個人ランキング（素点）
    small_subheader("個人ランキング（素点収支）")
    table_profit = (
        df_rank.sort_values("profit", ascending=False)[["name", "skill", "team", "profit"]]
        .rename(columns={
            "name": "プレイヤー",
            "skill": "スキル",
            "team": "チーム",
            "profit": "素点収支",
        })
        .reset_index(drop=True)
    )
    styled_profit = apply_medal_colors(table_profit)
    st.dataframe(styled_profit, use_container_width=True)


    # 個人ランキング（handicap収支）
    small_subheader("個人ランキング（handicap収支）")
    table_handicap = (
        df_rank.sort_values("handicap_profit", ascending=False)[
            ["name", "skill", "team", "handicap_profit"]
        ]
        .rename(columns={
            "name": "プレイヤー",
            "skill": "スキル",
            "team": "チーム",
            "handicap_profit": "Handicap収支",
        })
        .reset_index(drop=True)
    )
    styled_handicap = apply_medal_colors(table_handicap)
    st.dataframe(styled_handicap, use_container_width=True)


    # チームランキング
    group_score = (
        df_rank.groupby("team", as_index=False)
        .agg({"profit": "sum", "handicap_profit": "sum"})
        .rename(columns={"team": "チーム", "profit": "素点収支", "handicap_profit": "Handicap収支"})
    )

    small_subheader("チームランキング（素点収支）")
    table_team_profit = group_score.sort_values("素点収支", ascending=False)[["チーム", "素点収支"]]
    st.dataframe(table_team_profit.reset_index(drop=True), use_container_width=True)


    small_subheader("チームランキング（handicap収支）")
    table_team_handicap = group_score.sort_values("Handicap収支", ascending=False)[["チーム", "Handicap収支"]]
    st.dataframe(table_team_handicap.reset_index(drop=True), use_container_width=True)

st.markdown("---")


# ==============================
# 5. データリセット
# ==============================
st.subheader("データリセット（注意）")
with st.expander("データをリセット（元に戻せません）"):
    if st.button("全データ削除"):
        reset_players_sheet()
        st.success("データをリセットしました")
        st.rerun()
