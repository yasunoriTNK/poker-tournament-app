import uuid
from datetime import datetime

import pandas as pd
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials


# --------------------------
# Google Sheets 接続まわり
# --------------------------


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
            ]
        )
    return ws


def _empty_players_df() -> pd.DataFrame:
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
        ]
    )


@st.cache_data(ttl=10, show_spinner=False)
def load_players_df() -> pd.DataFrame:
    ws = get_worksheet()
    values = ws.get_all_values()
    if not values or len(values) == 1:
        return _empty_players_df()

    header = values[0]
    records = values[1:]
    df = pd.DataFrame(records, columns=header)

    # 型変換
    numeric_cols = ["initial_buyin", "rebuy_total", "rebuy_times", "final_stack"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def append_player_row(row: dict):
    ws = get_worksheet()
    now = datetime.utcnow().isoformat()
    ws.append_row(
        [
            row["player_id"],
            row["name"],
            row["team"],
            row["skill"],
            int(row["initial_buyin"]),
            int(row["rebuy_total"]),
            int(row["rebuy_times"]),
            "" if row["final_stack"] is None else int(row["final_stack"]),
            now,
            now,
        ]
    )
    load_players_df.clear()


def update_player_row(player_id: str, updates: dict):
    ws = get_worksheet()
    df = load_players_df()

    if df.empty:
        return

    if player_id not in df["player_id"].values:
        return

    row_idx = df.index[df["player_id"] == player_id][0]
    sheet_row = row_idx + 2  # 1-based & header

    for col_name, new_value in updates.items():
        if col_name not in df.columns:
            continue
        col_idx = df.columns.get_loc(col_name) + 1
        if col_name in ["initial_buyin", "rebuy_total", "rebuy_times", "final_stack"]:
            if new_value is None or new_value == "":
                ws.update_cell(sheet_row, col_idx, "")
            else:
                ws.update_cell(sheet_row, col_idx, int(new_value))
        else:
            ws.update_cell(sheet_row, col_idx, str(new_value))

    ts_col = df.columns.get_loc("updated_at") + 1
    ws.update_cell(sheet_row, ts_col, datetime.utcnow().isoformat())

    load_players_df.clear()


# --------------------------
# Streamlit UI / ロジック
# --------------------------


st.set_page_config(
    page_title="ポーカー大会 収支集計アプリ",
    page_icon="🃏",
    layout="centered",
)

# プレイヤー名の可読性向上 CSS
st.markdown(
    """
    <style>
    .player-card-name {
        color: #ffffff;
        font-weight: 700;
        font-size: 1.05rem;
    }
    .player-card-container {
        background-color: #24293a;
        padding: 0.75rem 1.0rem;
        border-radius: 1.25rem;
    }
    .badge {
        display: inline-block;
        padding: 0.1rem 0.6rem;
        border-radius: 999px;
        font-size: 0.75rem;
        border: 1px solid rgba(255, 255, 255, 0.4);
        margin-left: 0.25rem;
    }
    .badge-team-cse {
        border-color: #3b82f6;
        color: #3b82f6;
        background-color: rgba(59, 130, 246, 0.08);
    }
    .badge-team-rc {
        border-color: #f97316;
        color: #f97316;
        background-color: rgba(249, 115, 22, 0.08);
    }
    .badge-skill-beginner {
        border-color: #22c55e;
        color: #22c55e;
        background-color: rgba(34, 197, 94, 0.08);
    }
    .badge-skill-expert {
        border-color: #facc15;
        color: #facc15;
        background-color: rgba(250, 204, 21, 0.08);
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("ポーカー大会 収支集計アプリ")
st.caption("Buy-in（バイイン）、Re-buy（リバイ）を登録し、収支を自動で集計。")

df = load_players_df()

# --------------------------
# ルール表示
# --------------------------

st.markdown(
    """
**ルール：**

- 個人順位、チーム順位（CSE / RC）を集計  
- handicap：経験者は最終持ち点を半分（マイナスの場合は2倍）、初心者は最終持ち点を2倍（マイナスの場合は半分）に  
- 素点収支集計・handicap収支集計の双方を実施  
"""
)

# --------------------------
# 1. プレイヤー登録
# --------------------------

st.header("1. プレイヤー登録")
st.caption("ゲーム開始前に、参加者の基本情報と初期バイインだけ登録します。")

with st.form("player_registration"):
    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input("プレイヤー名", placeholder="例）田中")
    with col2:
        team = st.selectbox("チーム", options=["CSE", "RC"])

    col3, col4 = st.columns(2)
    with col3:
        skill = st.selectbox("スキル区分", options=["初心者", "経験者"])
    with col4:
        initial_buyin = st.number_input(
            "初期バイイン額",
            min_value=0,
            step=1000,
            value=0,
            help="ゲーム開始時に投入するBuy-in額を入力してください。",
        )

    submitted = st.form_submit_button("＋ プレイヤーを登録する")

    if submitted:
        if not name.strip():
            st.error("プレイヤー名を入力してください。")
        else:
            new_player = {
                "player_id": str(uuid.uuid4()),
                "name": name.strip(),
                "team": team,
                "skill": skill,
                "initial_buyin": int(initial_buyin),
                "rebuy_total": 0,
                "rebuy_times": 0,
                "final_stack": None,
            }
            append_player_row(new_player)
            st.success(f"{name} を登録しました。")
            st.rerun()

# 参加人数サマリー
df = load_players_df()
num_players = len(df)
num_cse = int((df["team"] == "CSE").sum()) if not df.empty else 0
num_rc = int((df["team"] == "RC").sum()) if not df.empty else 0

col1, col2, col3 = st.columns(3)
col1.metric("参加人数", f"{num_players} 人")
col2.metric("CSE人数", f"{num_cse} 人")
col3.metric("RC人数", f"{num_rc} 人")

st.markdown("---")

# --------------------------
# 2. プレイヤー一覧・途中経過
# --------------------------

st.header("2. プレイヤー一覧・途中経過")
st.caption("各プレイヤーのボックス内で、そのまま Re-buy を追加できます。")

if df.empty:
    st.info("まだプレイヤーが登録されていません。上のフォームから登録してください。")
else:
    for _, row in df.iterrows():
        pid = row["player_id"]
        player_name = row["name"]
        team = row["team"]
        skill = row["skill"]
        initial_buyin = int(row["initial_buyin"]) if not pd.isna(row["initial_buyin"]) else 0
        rebuy_total = int(row["rebuy_total"]) if not pd.isna(row["rebuy_total"]) else 0
        rebuy_times = int(row["rebuy_times"]) if not pd.isna(row["rebuy_times"]) else 0
        final_stack = (
            None if pd.isna(row["final_stack"]) or row["final_stack"] == "" else int(row["final_stack"])
        )

        with st.container():
            st.markdown(
    f"<div style='font-size: 1.3rem; font-weight: 700; color: white;'>{row['name']}</div>",
    unsafe_allow_html=True
)

            top_cols = st.columns([3, 1, 1])
            with top_cols[0]:
                st.markdown(
                    f"<span class='player-card-name'>{player_name}</span>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"Buyin: {initial_buyin:,}　Rebuy合計: {rebuy_total:,}（{rebuy_times}回）　"
                    f"最終Stack: {('未入力' if final_stack is None else f'{final_stack:,}')}",
                )
            with top_cols[1]:
                team_class = "badge-team-cse" if team == "CSE" else "badge-team-rc"
                st.markdown(
                    f"<span class='badge {team_class}'>{team}</span>",
                    unsafe_allow_html=True,
                )
            with top_cols[2]:
                skill_class = (
                    "badge-skill-beginner" if skill == "初心者" else "badge-skill-expert"
                )
                st.markdown(
                    f"<span class='badge {skill_class}'>{skill}</span>",
                    unsafe_allow_html=True,
                )

            st.markdown("</div>", unsafe_allow_html=True)

        # Rebuy 入力行
        col_rebuy_amount, col_minus, col_plus, col_button = st.columns([4, 1, 1, 3])
        key_base = f"rebuy_{pid}"

        with col_rebuy_amount:
            rebuy_input = st.number_input(
                "",
                min_value=0,
                step=1000,
                value=0,
                key=f"{key_base}_amount",
            )
        with col_minus:
            if st.button("－", key=f"{key_base}_minus"):
                current = st.session_state[f"{key_base}_amount"]
                st.session_state[f"{key_base}_amount"] = max(0, current - 1000)
                st.rerun()
        with col_plus:
            if st.button("＋", key=f"{key_base}_plus"):
                st.session_state[f"{key_base}_amount"] += 1000
                st.rerun()
        with col_button:
            if st.button("＋ Rebuy", key=f"{key_base}_btn"):
                if rebuy_input <= 0:
                    st.warning("Re-buy額は正の数を入力してください。")
                else:
                    new_rebuy_total = rebuy_total + int(rebuy_input)
                    new_rebuy_times = rebuy_times + 1
                    update_player_row(
                        pid,
                        {
                            "rebuy_total": new_rebuy_total,
                            "rebuy_times": new_rebuy_times,
                        },
                    )
                    st.success(f"{player_name} に Re-buy {rebuy_input:,} を追加しました。")
                    st.rerun()

    st.markdown("---")

# --------------------------
# 3. 途中経過（チーム別 Re-buy 集計）
# --------------------------

st.header("3. 途中経過")
st.caption("チームごとの Re-buy 額の途中経過を表示します。")

if df.empty:
    st.info("まだプレイヤーがいないため、途中経過は表示できません。")
else:
    df_rebuy = df.copy()
    df_rebuy["rebuy_total"] = pd.to_numeric(df_rebuy["rebuy_total"], errors="coerce").fillna(0)

    cse_rebuy = int(df_rebuy.loc[df_rebuy["team"] == "CSE", "rebuy_total"].sum())
    rc_rebuy = int(df_rebuy.loc[df_rebuy["team"] == "RC", "rebuy_total"].sum())
    total_rebuy = cse_rebuy + rc_rebuy

    col1, col2, col3 = st.columns(3)
    col1.metric("CSE Re-buy額合計", f"{cse_rebuy:,}")
    col2.metric("RC Re-buy額合計", f"{rc_rebuy:,}")
    col3.metric("Re-buy額合計（全体）", f"{total_rebuy:,}")

st.markdown("---")

# --------------------------
# 4. 最終スタック登録
# --------------------------

st.header("4. 最終スタック登録")
st.caption("ゲームから離脱した人は、その時点のスタックを登録してください。（0の場合は0を入力）")

if df.empty:
    st.info("プレイヤーがいないため、最終スタックは登録できません。")
else:
    for _, row in df.iterrows():
        pid = row["player_id"]
        player_name = row["name"]
        final_stack = (
            None if pd.isna(row["final_stack"]) or row["final_stack"] == "" else int(row["final_stack"])
        )

        col_label, col_input, col_button = st.columns([3, 2, 2])
        with col_label:
            st.write(f"**{player_name}** の最終Stack")

        with col_input:
            stack_value_default = 0 if final_stack is None else final_stack
            new_stack = st.number_input(
                "",
                value=stack_value_default,
                step=1000,
                key=f"final_stack_{pid}",
            )

        with col_button:
            if st.button("最終Stackを登録", key=f"final_stack_btn_{pid}"):
                update_player_row(pid, {"final_stack": int(new_stack)})
                st.success(f"{player_name} の最終Stackを {int(new_stack):,} で登録しました。")
                st.rerun()

st.markdown("---")

# --------------------------
# 5. 集計・ランキング
# --------------------------

st.header("5. 集計・ランキング")
st.caption("全員の最終スタックが入ったら、素点収支とhandicap収支のランキングを出力します。")

if df.empty:
    st.info("プレイヤーがいないため、集計は実行できません。")
else:
    # 最終スタックが入っているプレイヤーのみ対象
    df_rank = df.copy()
    df_rank["final_stack"] = pd.to_numeric(df_rank["final_stack"], errors="coerce")
    df_rank["initial_buyin"] = pd.to_numeric(df_rank["initial_buyin"], errors="coerce").fillna(0)
    df_rank["rebuy_total"] = pd.to_numeric(df_rank["rebuy_total"], errors="coerce").fillna(0)

    df_rank = df_rank[~df_rank["final_stack"].isna()].copy()

    if df_rank.empty:
        st.info("最終Stackが未入力のプレイヤーがいるため、ランキングを計算できません。")
    else:
        # 素点収支 = 最終Stack - (初期Buy-in + Re-buy総額)
        df_rank["profit"] = df_rank["final_stack"] - (
            df_rank["initial_buyin"] + df_rank["rebuy_total"]
        )

        # handicap収支
        def calc_handicap(row):
            profit = row["profit"]
            if pd.isna(profit):
                return None

            if profit >= 0:
                if row["skill"] == "初心者":
                    val = profit * 2
                else:  # 経験者
                    val = profit * 0.5
            else:  # マイナス
                if row["skill"] == "初心者":
                    val = profit * 0.5
                else:
                    val = profit * 2

            return int(round(val))

        df_rank["handicap_profit"] = df_rank.apply(calc_handicap, axis=1)

        # 表示用列
        display_cols = [
            "name",
            "team",
            "skill",
            "initial_buyin",
            "rebuy_total",
            "final_stack",
            "profit",
            "handicap_profit",
        ]

        # 個人ランキング（素点収支）
        st.subheader("個人ランキング（素点収支）")
        df_individual = df_rank.sort_values(
            by=["profit", "created_at"], ascending=[False, True]
        ).reset_index(drop=True)
        df_individual.index = df_individual.index + 1
        st.dataframe(
            df_individual[display_cols].rename(
                columns={
                    "name": "プレイヤー",
                    "team": "チーム",
                    "skill": "スキル",
                    "initial_buyin": "初期Buy-in",
                    "rebuy_total": "Re-buy合計",
                    "final_stack": "最終Stack",
                    "profit": "素点収支",
                    "handicap_profit": "handicap収支",
                }
            ),
            use_container_width=True,
        )

        # 個人ランキング（handicap収支）
        st.subheader("個人ランキング（handicap収支）")
        df_individual_h = df_rank.sort_values(
            by=["handicap_profit", "created_at"], ascending=[False, True]
        ).reset_index(drop=True)
        df_individual_h.index = df_individual_h.index + 1
        st.dataframe(
            df_individual_h[display_cols].rename(
                columns={
                    "name": "プレイヤー",
                    "team": "チーム",
                    "skill": "スキル",
                    "initial_buyin": "初期Buy-in",
                    "rebuy_total": "Re-buy合計",
                    "final_stack": "最終Stack",
                    "profit": "素点収支",
                    "handicap_profit": "handicap収支",
                }
            ),
            use_container_width=True,
        )

        # チーム別集計
        st.subheader("チームランキング（素点収支 / handicap収支）")
        team_agg = (
            df_rank.groupby("team")
            .agg(
                {
                    "profit": "sum",
                    "handicap_profit": "sum",
                    "player_id": "count",
                }
            )
            .rename(columns={"player_id": "人数"})
            .reset_index()
        )

        team_agg = team_agg.sort_values(by="profit", ascending=False)
        st.dataframe(
            team_agg.rename(
                columns={
                    "team": "チーム",
                    "profit": "素点収支合計",
                    "handicap_profit": "handicap収支合計",
                }
            ),
            use_container_width=True,
        )
