import uuid
from datetime import datetime

import pandas as pd
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials


# ==============================
# 設定
# ==============================

SHEET_NAME = "players"  # Google Sheets 内のシート名


# ==============================
# Google Sheets 接続
# ==============================

@st.cache_resource
def get_gspread_client():
    """
    Streamlit Cloud の st.secrets に格納したサービスアカウント情報から
    gspread クライアントを生成する。
    """
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
    """
    Google Sheets の players シート（ワークシート）を取得する。
    st.secrets["spreadsheet_id"] に対象スプレッドシートIDを入れておく想定。
    """
    client = get_gspread_client()
    spreadsheet = client.open_by_key(st.secrets["spreadsheet_id"])
    try:
        ws = spreadsheet.worksheet(SHEET_NAME)
    except gspread.WorksheetNotFound:
        # 初回用：シートがなければ作成してヘッダ行をセット
        ws = spreadsheet.add_worksheet(title=SHEET_NAME, rows=200, cols=10)
        ws.append_row([
            "player_id",
            "name",
            "team",
            "skill",
            "initial_buyin",
            "rebuy_total",
            "rebuy_count",
            "final_stack",
            "created_at",
            "updated_at",
        ])
    return ws


def load_players_df():
    """
    players シートを DataFrame として読み込む。
    空シートの場合は空の DataFrame を返す。
    """
    ws = get_worksheet()
    rows = ws.get_all_values()
    if not rows or len(rows) == 1:
        columns = [
            "player_id",
            "name",
            "team",
            "skill",
            "initial_buyin",
            "rebuy_total",
            "rebuy_count",
            "final_stack",
            "created_at",
            "updated_at",
        ]
        return pd.DataFrame(columns=columns)

    header = rows[0]
    data = rows[1:]
    df = pd.DataFrame(data, columns=header)

    # 数値列を適切に変換
    for col in ["initial_buyin", "rebuy_total", "rebuy_count", "final_stack"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # created_at で登録順を安定させる（なければそのまま）
    if "created_at" in df.columns:
        df = df.sort_values("created_at", kind="mergesort")

    return df


def write_players_df(df: pd.DataFrame):
    """
    DataFrame 全体を players シートに書き戻す（上書き）。
    行数がそこまで多くない前提なので、シンプルに全書き換え方式にする。
    """
    ws = get_worksheet()
    ws.clear()
    ws.append_row(list(df.columns))
    if len(df) > 0:
        rows = df.astype(str).values.tolist()
        ws.append_rows(rows)


# ==============================
# 集計ロジック
# ==============================

def compute_profit_and_adjusted(df: pd.DataFrame) -> pd.DataFrame:
    """
    DataFrame に profit（収支）と adjusted_profit（傾斜後収支）列を追加して返す。
    収支 = final_stack - (initial_buyin + rebuy_total)
    傾斜は収支に対して実施。
    """
    df = df.copy()

    df["total_buyin"] = df["initial_buyin"].fillna(0) + df["rebuy_total"].fillna(0)
    df["profit"] = df["final_stack"] - df["total_buyin"]

    def adjust_profit(row):
        profit = row["profit"]
        skill = row["skill"]  # "experienced" or "beginner"
        if pd.isna(profit):
            return None

        if profit >= 0:
            if skill == "experienced":
                val = profit / 2
            else:  # beginner
                val = profit * 2
        else:
            if skill == "experienced":
                val = profit * 2
            else:
                val = profit / 2

        return round(val)

    df["adjusted_profit"] = df.apply(adjust_profit, axis=1)

    return df


def sort_for_ranking(df: pd.DataFrame, key: str) -> pd.DataFrame:
    """
    ランキング用のソート。
    - key の降順
    - 同値の場合は登録順を維持するため安定ソート。
    """
    df = df.copy()
    df = df.reset_index(drop=False).rename(columns={"index": "_orig_index"})
    df = df.sort_values(
        by=[key, "_orig_index"],
        ascending=[False, True],
        kind="mergesort",
    )
    return df


# ==============================
# スタイル（CSS）
# ==============================

def inject_css():
    st.markdown(
        """
        <style>
        /* 全体背景とフォント色 */
        .main {
            background: radial-gradient(circle at top left, #1f2933, #020617);
            color: #e5e7eb;
        }
        /* タイトル */
        .app-title {
            font-size: 1.6rem;
            font-weight: 700;
            padding: 0.5rem 0;
        }
        .app-subtitle {
            font-size: 0.9rem;
            color: #9ca3af;
            margin-bottom: 0.5rem;
        }
        /* セクションヘッダ */
        .section-header {
            font-size: 1.1rem;
            font-weight: 600;
            margin-top: 1rem;
            margin-bottom: 0.2rem;
        }
        .section-caption {
            font-size: 0.8rem;
            color: #9ca3af;
            margin-bottom: 0.6rem;
        }
        /* プレイヤーカード */
        .player-card {
            border-radius: 12px;
            padding: 0.7rem 0.8rem;
            margin-bottom: 0.3rem;
            background: rgba(15, 23, 42, 0.9);
            border: 1px solid rgba(148, 163, 184, 0.35);
        }
        .player-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 0.25rem;
        }
        .player-name {
            font-weight: 600;
            font-size: 0.95rem;
        }
        .badge-group {
            display: flex;
            gap: 0.25rem;
        }
        .badge {
            padding: 0.15rem 0.5rem;
            border-radius: 999px;
            font-size: 0.7rem;
            font-weight: 600;
            display: inline-block;
        }
        .badge-team-cse {
            background: rgba(56, 189, 248, 0.15);
            color: #38bdf8;
            border: 1px solid rgba(56, 189, 248, 0.6);
        }
        .badge-team-rc {
            background: rgba(249, 115, 22, 0.15);
            color: #fb923c;
            border: 1px solid rgba(249, 115, 22, 0.6);
        }
        .badge-skill-beginner {
            background: rgba(22, 163, 74, 0.15);
            color: #4ade80;
            border: 1px solid rgba(22, 163, 74, 0.6);
        }
        .badge-skill-experienced {
            background: rgba(239, 68, 68, 0.12);
            color: #fca5a5;
            border: 1px solid rgba(239, 68, 68, 0.6);
        }
        .player-meta {
            font-size: 0.8rem;
            color: #cbd5f5;
            display: flex;
            flex-wrap: wrap;
            gap: 0.7rem;
            margin-bottom: 0.4rem;
        }
        .player-meta span {
            white-space: nowrap;
        }
        .meta-label {
            color: #9ca3af;
        }
        /* ボタン（全体のトーン統一） */
        button[kind="primary"] {
            background: linear-gradient(90deg, #22c55e, #16a34a) !important;
            color: white !important;
            border-radius: 999px !important;
            border: none !important;
        }
        button[kind="secondary"] {
            border-radius: 999px !important;
        }
        /* DataFrame テーブルの文字少し小さめに */
        .stDataFrame table {
            font-size: 0.8rem !important;
        }
        /* 警告・インフォのカード少しだけ透明感 */
        .stAlert > div {
            background-color: rgba(15, 23, 42, 0.95) !important;
            border-radius: 12px !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ==============================
# UI
# ==============================

def main():
    st.set_page_config(
        page_title="ポーカー大会 収支集計アプリ",
        layout="centered",
    )

    inject_css()

    # ヘッダ
    st.markdown(
        """
        <div class="app-title">🃏 ポーカー大会 収支集計アプリ</div>
        <div class="app-subtitle">スマホ1台で、バイイン・Rebuy・最終スタックから収支と傾斜後収支を自動で集計。</div>
        """,
        unsafe_allow_html=True,
    )

    # データ読み込み
    df = load_players_df()

    # =========================
    # 1. プレイヤー登録
    # =========================
    st.markdown(
        '<div class="section-header">1. プレイヤー登録</div>'
        '<div class="section-caption">ゲーム開始前に、参加者の基本情報と初期バイインだけ登録します。</div>',
        unsafe_allow_html=True,
    )

    with st.form("add_player_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        name = col1.text_input("プレイヤー名", placeholder="例）田中")
        team = col2.selectbox("チーム", ["CSE", "RC"])

        col3, col4 = st.columns(2)
        skill_jp = col3.selectbox("スキル区分", ["初心者", "経験者"])
        initial_buyin = col4.number_input(
            "初期バイイン額",
            min_value=0,
            step=100,
            help="最初に参加するときのバイイン額を入力してください。",
        )

        submitted = st.form_submit_button("＋ プレイヤーを登録する")

        if submitted:
            if not name:
                st.error("プレイヤー名を入力してください。")
            else:
                skill = "beginner" if skill_jp == "初心者" else "experienced"
                now = datetime.now().isoformat(timespec="seconds")
                new_row = {
                    "player_id": str(uuid.uuid4()),
                    "name": name,
                    "team": team,
                    "skill": skill,
                    "initial_buyin": int(initial_buyin),
                    "rebuy_total": 0,
                    "rebuy_count": 0,
                    "final_stack": None,
                    "created_at": now,
                    "updated_at": now,
                }
                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                write_players_df(df)
                st.success(f"{name} を登録しました。")
                st.experimental_rerun()

    # 簡単なサマリー
    with st.container():
        colA, colB, colC = st.columns(3)
        colA.metric("参加人数", f"{len(df)} 人")
        total_buyin_display = int(df["initial_buyin"].fillna(0).sum()) if len(df) else 0
        colB.metric("初期バイイン合計", f"{total_buyin_display:,}")
        total_rebuy_display = int(df["rebuy_total"].fillna(0).sum()) if len(df) else 0
        colC.metric("Rebuy 合計", f"{total_rebuy_display:,}")

    st.markdown("---")

    # =========================
    # 2. プレイヤー一覧・途中経過（カード＋行ごとの Rebuy 入力）
    # =========================
    st.markdown(
        '<div class="section-header">2. プレイヤー一覧・途中経過</div>'
        '<div class="section-caption">各プレイヤーのカード内で、そのまま Rebuy を追加できます。</div>',
        unsafe_allow_html=True,
    )

    if len(df) == 0:
        st.info("まだプレイヤーが登録されていません。上のフォームから登録してください。")
    else:
        for _, row in df.iterrows():
            team = row["team"]
            skill = row["skill"]  # "beginner" / "experienced"
            buyin = row["initial_buyin"] if not pd.isna(row["initial_buyin"]) else 0
            rebuy_total = row["rebuy_total"] if not pd.isna(row["rebuy_total"]) else 0
            rebuy_count = int(row["rebuy_count"]) if not pd.isna(row["rebuy_count"]) else 0
            final_stack = row["final_stack"]

            team_badge_cls = "badge-team-cse" if team == "CSE" else "badge-team-rc"
            skill_badge_cls = (
                "badge-skill-beginner" if skill == "beginner" else "badge-skill-experienced"
            )
            skill_label = "初心者" if skill == "beginner" else "経験者"

            final_stack_str = (
                f"{int(final_stack):,}"
                if not pd.isna(final_stack)
                else "未入力"
            )

            card_html = f"""
            <div class="player-card">
                <div class="player-header">
                    <div class="player-name">{row['name']}</div>
                    <div class="badge-group">
                        <span class="badge {team_badge_cls}">{team}</span>
                        <span class="badge {skill_badge_cls}">{skill_label}</span>
                    </div>
                </div>
                <div class="player-meta">
                    <span><span class="meta-label">Buyin:</span> {int(buyin):,}</span>
                    <span><span class="meta-label">Rebuy合計:</span> {int(rebuy_total):,}（{rebuy_count}回）</span>
                    <span><span class="meta-label">最終Stack:</span> {final_stack_str}</span>
                </div>
            </div>
            """
            st.markdown(card_html, unsafe_allow_html=True)

            # 行ごとの Rebuy 入力（A案）
            col_r1, col_r2 = st.columns([3, 1])
            rebuy_amount = col_r1.number_input(
                f"Rebuy金額（{row['name']}）",
                min_value=0,
                step=100,
                key=f"rebuy_amount_{row['player_id']}",
                label_visibility="collapsed",
            )
            with col_r2:
                if st.button("＋ Rebuy", key=f"rebuy_button_{row['player_id']}"):
                    if rebuy_amount <= 0:
                        st.error("Rebuy金額は 0 より大きい値を入力してください。")
                    else:
                        idx = df.index[df["player_id"] == row["player_id"]][0]
                        df.loc[idx, "rebuy_total"] = (df.loc[idx, "rebuy_total"] or 0) + int(
                            rebuy_amount
                        )
                        df.loc[idx, "rebuy_count"] = (df.loc[idx, "rebuy_count"] or 0) + 1
                        df.loc[idx, "updated_at"] = datetime.now().isoformat(timespec="seconds")
                        write_players_df(df)
                        st.success(f"{row['name']} に Rebuy {int(rebuy_amount):,} を追加しました。")
                        st.experimental_rerun()

    st.markdown("---")

    # =========================
    # 3. 最終スタック登録
    # =========================
    st.markdown(
        '<div class="section-header">3. 最終スタック登録</div>'
        '<div class="section-caption">ゲームから離脱した人は、その時点のスタックを登録します。（マイナスも可）</div>',
        unsafe_allow_html=True,
    )

    if len(df) == 0:
        st.info("プレイヤーがいないため、最終スタックは登録できません。")
    else:
        with st.form("final_stack_form", clear_on_submit=True):
            col1, col2 = st.columns([2, 1])
            player_names = df["name"].tolist()
            selected_name_fs = col1.selectbox("最終スタックを登録するプレイヤー", player_names)
            final_stack_val = col2.number_input(
                "最終Stack",
                step=100,
                format="%d",
                help="離脱時点のスタックを入力してください。マイナスも入力可能です。",
            )
            final_submit = st.form_submit_button("💾 最終Stackを保存")

            if final_submit:
                idx = df.index[df["name"] == selected_name_fs][0]
                df.loc[idx, "final_stack"] = int(final_stack_val)
                df.loc[idx, "updated_at"] = datetime.now().isoformat(timespec="seconds")
                write_players_df(df)
                st.success(f"{selected_name_fs} の最終Stackを {int(final_stack_val):,} に更新しました。")
                st.experimental_rerun()

    st.markdown("---")

    # =========================
    # 4. 集計
    # =========================
    st.markdown(
        '<div class="section-header">4. 集計・ランキング</div>'
        '<div class="section-caption">全員の最終スタックが入ったら、収支と傾斜後収支のランキングを出します。</div>',
        unsafe_allow_html=True,
    )

    if len(df) == 0:
        st.info("プレイヤーがいないため、集計は実行できません。")
    else:
        if df["final_stack"].isna().any():
            st.warning("⚠ 一部プレイヤーの最終Stackが未入力です。そのプレイヤーの収支は計算されません。")

        if st.button("▶ 集計を実行する"):
            df_calc = compute_profit_and_adjusted(df)

            # 個人別 収支ランキング
            st.markdown("#### 個人別 収支ランキング")
            df_profit_rank = sort_for_ranking(df_calc.dropna(subset=["profit"]), "profit")
            if len(df_profit_rank) == 0:
                st.info("収支を計算できるプレイヤーがいません。")
            else:
                tmp = df_profit_rank.copy()
                tmp["Skill"] = tmp["skill"].map({"beginner": "初心者", "experienced": "経験者"})
                tmp["収支表示"] = tmp["profit"].apply(
                    lambda x: f"🟢 +{int(x):,}" if x >= 0 else f"🔴 {int(x):,}"
                )
                tmp["Team"] = tmp["team"]
                tmp["Name"] = tmp["name"]
                tmp["Buyin"] = tmp["initial_buyin"].astype("Int64")
                tmp["Rebuy合計"] = tmp["rebuy_total"].astype("Int64")
                tmp["Rebuy回数"] = tmp["rebuy_count"].astype("Int64")
                tmp["最終Stack"] = tmp["final_stack"].astype("Int64")

                display_cols = [
                    "Name",
                    "Team",
                    "Skill",
                    "Buyin",
                    "Rebuy合計",
                    "Rebuy回数",
                    "最終Stack",
                    "収支表示",
                ]
                tmp = tmp[display_cols]
                tmp.insert(0, "順位", range(1, len(tmp) + 1))
                st.dataframe(tmp, use_container_width=True, hide_index=True)

            # 個人別 傾斜後収支ランキング
            st.markdown("#### 個人別 傾斜後収支ランキング")
            df_adj_rank = sort_for_ranking(df_calc.dropna(subset=["adjusted_profit"]), "adjusted_profit")
            if len(df_adj_rank) == 0:
                st.info("傾斜後収支を計算できるプレイヤーがいません。")
            else:
                tmp2 = df_adj_rank.copy()
                tmp2["Skill"] = tmp2["skill"].map({"beginner": "初心者", "experienced": "経験者"})
                tmp2["収支表示"] = tmp2["profit"].apply(
                    lambda x: f"🟢 +{int(x):,}" if x >= 0 else f"🔴 {int(x):,}"
                )
                tmp2["傾斜後収支表示"] = tmp2["adjusted_profit"].apply(
                    lambda x: f"🟢 +{int(x):,}" if x >= 0 else f"🔴 {int(x):,}"
                )

                tmp2["Name"] = tmp2["name"]
                tmp2["Team"] = tmp2["team"]

                display_cols2 = [
                    "Name",
                    "Team",
                    "Skill",
                    "収支表示",
                    "傾斜後収支表示",
                ]
                tmp2 = tmp2[display_cols2]
                tmp2.insert(0, "順位", range(1, len(tmp2) + 1))
                st.dataframe(tmp2, use_container_width=True, hide_index=True)

            # チーム別ランキング
            st.markdown("#### チーム別 収支・傾斜後収支")

            if "profit" in df_calc.columns and "adjusted_profit" in df_calc.columns:
                team_agg = df_calc.groupby("team").agg(
                    profit_sum=("profit", "sum"),
                    adjusted_profit_sum=("adjusted_profit", "sum"),
                ).reset_index()

                team_agg = team_agg.sort_values(
                    by=["profit_sum", "team"],
                    ascending=[False, True],
                )

                team_agg["収支表示"] = team_agg["profit_sum"].apply(
                    lambda x: f"🟢 +{int(x):,}" if x >= 0 else f"🔴 {int(x):,}"
                )
                team_agg["傾斜後収支表示"] = team_agg["adjusted_profit_sum"].apply(
                    lambda x: f"🟢 +{int(x):,}" if x >= 0 else f"🔴 {int(x):,}"
                )

                team_agg = team_agg.rename(columns={"team": "Team"})
                team_agg_display = team_agg[["Team", "収支表示", "傾斜後収支表示"]]
                team_agg_display.insert(0, "順位", range(1, len(team_agg_display) + 1))
                st.dataframe(team_agg_display, use_container_width=True, hide_index=True)
            else:
                st.info("チーム別の集計に必要なデータが不足しています。")

    st.markdown("---")

    # =========================
    # 5. 全データリセット
    # =========================
    st.markdown(
        '<div class="section-header">5. 全データリセット</div>'
        '<div class="section-caption">大会が完全に終了したら、次の大会に向けてデータをクリアします。</div>',
        unsafe_allow_html=True,
    )

    if st.button("🗑 すべてリセットする"):
        empty_df = pd.DataFrame(
            columns=[
                "player_id",
                "name",
                "team",
                "skill",
                "initial_buyin",
                "rebuy_total",
                "rebuy_count",
                "final_stack",
                "created_at",
                "updated_at",
            ]
        )
        write_players_df(empty_df)
        st.success("全データをリセットしました。")
        st.experimental_rerun()


if __name__ == "__main__":
    main()
