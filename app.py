import json
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="국내 주식 배당금 관리 대시보드",
    page_icon="💰",
    layout="wide",
)

BASE_DIR = Path(__file__).parent
DATA_FILE = BASE_DIR / "dividend_data.csv"
SETTINGS_FILE = BASE_DIR / "settings.json"

MONTH_COLS = [f"{m}월" for m in range(1, 13)]
YEAR_COL = "연도"
DEFAULT_YEAR = "2026"
BASE_COLS = [YEAR_COL, "종목명", "종목코드", "보유수량", "시가배당률(%)"]
ALL_COLS = BASE_COLS + MONTH_COLS
NUM_COLS = ["보유수량", "시가배당률(%)"] + MONTH_COLS
TEXT_COLS = [YEAR_COL, "종목명", "종목코드"]


def empty_row() -> dict:
    row = {col: DEFAULT_YEAR if col == YEAR_COL else "" for col in TEXT_COLS}
    row.update({col: "" for col in NUM_COLS})
    return row


def prepare_df(df: pd.DataFrame) -> pd.DataFrame:
    if "섹터" in df.columns and YEAR_COL not in df.columns:
        df = df.rename(columns={"섹터": YEAR_COL})

    df = df.reindex(columns=ALL_COLS, fill_value="").copy()
    for col in TEXT_COLS:
        df[col] = df[col].fillna("").astype(str).str.strip()
    df[YEAR_COL] = df[YEAR_COL].replace("", DEFAULT_YEAR)
    df["보유수량"] = pd.to_numeric(df["보유수량"], errors="coerce").fillna(0).astype(int)
    df["시가배당률(%)"] = pd.to_numeric(df["시가배당률(%)"], errors="coerce").fillna(0.0)
    for col in MONTH_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    return df


def to_editor_df(df: pd.DataFrame) -> pd.DataFrame:
    df = prepare_df(df)
    editor_df = df.copy()
    editor_df["보유수량"] = editor_df["보유수량"].map(lambda x: "" if x == 0 else str(int(x)))
    editor_df["시가배당률(%)"] = editor_df["시가배당률(%)"].map(
        lambda x: "" if x == 0 else f"{x:g}"
    )
    for col in MONTH_COLS:
        editor_df[col] = editor_df[col].map(lambda x: "" if x == 0 else str(int(x)))
    return editor_df


def load_data() -> pd.DataFrame:
    if DATA_FILE.exists():
        return prepare_df(pd.read_csv(DATA_FILE, encoding="utf-8-sig", dtype=str))
    return pd.DataFrame(columns=ALL_COLS)


def save_data(df: pd.DataFrame) -> None:
    prepare_df(df).to_csv(DATA_FILE, index=False, encoding="utf-8-sig")


def load_settings() -> dict:
    if SETTINGS_FILE.exists():
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    return {"monthly_goal": 1_500_000}


def save_settings(settings: dict) -> None:
    SETTINGS_FILE.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def calc_metrics(df: pd.DataFrame, monthly_goal: int) -> tuple[int, float, float]:
    monthly_totals = df[MONTH_COLS].sum()
    total_annual = int(monthly_totals.sum())
    monthly_avg = total_annual / 12
    goal_rate = (monthly_avg / monthly_goal * 100) if monthly_goal > 0 else 0.0
    return total_annual, monthly_avg, goal_rate


def summarize_by_code(df: pd.DataFrame) -> pd.DataFrame:
    df = prepare_df(df)
    df = df[df["종목코드"].str.strip() != ""].copy()

    if df.empty:
        return pd.DataFrame(
            columns=[YEAR_COL, "종목코드", "종목명", "입력 건수", "보유수량 합계"]
            + MONTH_COLS
            + ["연간 총액"]
        )

    agg_kwargs = {
        "종목명": ("종목명", "first"),
        "입력 건수": ("종목코드", "size"),
        "보유수량 합계": ("보유수량", "sum"),
    }
    for month in MONTH_COLS:
        agg_kwargs[month] = (month, "sum")

    grouped = df.groupby([YEAR_COL, "종목코드"], as_index=False).agg(**agg_kwargs)
    grouped["연간 총액"] = grouped[MONTH_COLS].sum(axis=1).astype(int)
    grouped = grouped.sort_values(["연도", "연간 총액"], ascending=[True, False]).reset_index(
        drop=True
    )

    return grouped[
        [YEAR_COL, "종목코드", "종목명", "입력 건수", "보유수량 합계"] + MONTH_COLS + ["연간 총액"]
    ]


def filter_by_year(df: pd.DataFrame, view_year: str) -> pd.DataFrame:
    if view_year == "전체":
        return df
    return df[df[YEAR_COL] == view_year].copy()


def calc_yearly_totals(df: pd.DataFrame) -> dict[str, int]:
    df = prepare_df(df)
    if df.empty:
        return {}
    df["연간 총액"] = df[MONTH_COLS].sum(axis=1).astype(int)
    return df.groupby(YEAR_COL)["연간 총액"].sum().astype(int).sort_index().to_dict()


def format_short_year(year: str) -> str:
    year = str(year).strip()
    return year[-2:] if len(year) >= 2 else year


def render_monthly_chart(df: pd.DataFrame) -> None:
    monthly_data = pd.DataFrame(
        {
            "월": MONTH_COLS,
            "배당금": df[MONTH_COLS].sum().values.astype(int),
        }
    )
    monthly_data["금액표시"] = monthly_data["배당금"].map(lambda x: f"{int(x):,} 원")

    base = alt.Chart(monthly_data).encode(
        x=alt.X("월:N", sort=MONTH_COLS, title=None),
        y=alt.Y("배당금:Q", title="배당금 (원)"),
    )

    bars = base.mark_bar(color="#FFB6C1")
    labels = base.mark_text(
        align="center",
        baseline="bottom",
        dy=-5,
        color="#444444",
        fontSize=12,
    ).encode(text="금액표시:N")

    chart = (bars + labels).properties(height=420)
    st.altair_chart(chart, use_container_width=True)


def row_label(row: pd.Series, idx: int) -> str:
    name = str(row["종목명"]).strip()
    code = str(row["종목코드"]).strip()
    if name and code:
        return f"{name} ({code})"
    if name:
        return name
    if code:
        return f"종목코드 {code}"
    return f"종목 {idx + 1}"


def update_dividend_df(new_df: pd.DataFrame) -> None:
    prepared = prepare_df(new_df)
    if not prepared.equals(st.session_state.dividend_df):
        save_data(prepared)
    st.session_state.dividend_df = prepared


if "dividend_df" not in st.session_state:
    st.session_state.dividend_df = load_data()

settings = load_settings()

st.title("💰 국내 주식 배당금 관리 대시보드")
st.caption("입력한 내용은 파일에 자동 저장됩니다. 새로고침해도 사라지지 않아요.")

with st.sidebar:
    st.header("⚙️ 설정")
    monthly_goal = st.number_input(
        "월 목표 배당금 (원)",
        min_value=0,
        value=int(settings.get("monthly_goal", 1_500_000)),
        step=100_000,
        format="%d",
    )

    if monthly_goal != settings.get("monthly_goal"):
        save_settings({"monthly_goal": monthly_goal})

    all_years = sorted(
        prepare_df(st.session_state.dividend_df)[YEAR_COL].unique().tolist() or [DEFAULT_YEAR]
    )
    view_year = st.selectbox("조회 연도", ["전체", *all_years], index=1 if DEFAULT_YEAR in all_years else 0)

    st.divider()
    st.markdown("**빠른 작업**")

    if st.button("➕ 빈 종목 추가", use_container_width=True):
        st.session_state.dividend_df = pd.concat(
            [st.session_state.dividend_df, pd.DataFrame([empty_row()])],
            ignore_index=True,
        )
        save_data(st.session_state.dividend_df)
        st.rerun()

    sidebar_df = prepare_df(st.session_state.dividend_df)
    delete_options = {
        row_label(sidebar_df.iloc[i], i): i for i in range(len(sidebar_df))
    }

    selected_to_delete = st.multiselect(
        "삭제할 종목 선택",
        options=list(delete_options.keys()),
        placeholder="삭제할 항목을 고르세요",
    )

    if st.button(
        "🗑️ 선택 항목 삭제",
        use_container_width=True,
        disabled=not selected_to_delete,
    ):
        drop_indices = [delete_options[label] for label in selected_to_delete]
        st.session_state.dividend_df = (
            sidebar_df.drop(index=drop_indices).reset_index(drop=True)
        )
        save_data(st.session_state.dividend_df)
        st.rerun()

    st.divider()
    st.caption(f"저장 위치: `{DATA_FILE.name}`")


@st.fragment
def dividend_workspace(monthly_goal: int, view_year: str) -> None:
    current_df = filter_by_year(prepare_df(st.session_state.dividend_df), view_year)
    total_annual, monthly_avg, goal_rate = calc_metrics(current_df, monthly_goal)

    year_label = f" ({view_year}년)" if view_year != "전체" else ""

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(f"올해 총 예상 배당금{year_label}", f"{total_annual:,.0f} 원")

    with col2:
        st.metric(f"월 평균 배당금{year_label}", f"{monthly_avg:,.0f} 원")

    with col3:
        st.metric(f"월 목표 달성률{year_label}", f"{goal_rate:.1f} %")

    st.divider()

    st.subheader("✏️ 보유 종목 입력 / 수정")
    st.info("숫자 칸도 종목명처럼 입력 후 Enter를 누르면 바로 저장됩니다.")

    edited_df = st.data_editor(
        to_editor_df(st.session_state.dividend_df),
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            YEAR_COL: st.column_config.TextColumn(YEAR_COL, help="예: 2026, 2027"),
            "종목명": st.column_config.TextColumn("종목명", help="예: 삼성전자"),
            "종목코드": st.column_config.TextColumn("종목코드", help="예: 005930"),
            "보유수량": st.column_config.TextColumn("보유수량", help="숫자만 입력"),
            "시가배당률(%)": st.column_config.TextColumn("시가배당률(%)", help="예: 3.5"),
            **{
                month: st.column_config.TextColumn(month, help="원 단위 숫자")
                for month in MONTH_COLS
            },
        },
    )

    update_dividend_df(edited_df)

    result_df = filter_by_year(st.session_state.dividend_df.copy(), view_year)
    result_df["연간 총액"] = result_df[MONTH_COLS].sum(axis=1).astype(int)

    st.subheader(f"📋 연간 총액 (자동 계산){year_label}")
    st.dataframe(
        result_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "연간 총액": st.column_config.NumberColumn("연간 총액", format="%d"),
            **{
                month: st.column_config.NumberColumn(month, format="%d")
                for month in MONTH_COLS
            },
        },
    )

    yearly_totals = calc_yearly_totals(st.session_state.dividend_df)
    _, annual_total_col = st.columns([3, 1])
    with annual_total_col:
        for year, total in yearly_totals.items():
            st.markdown(f"**{format_short_year(year)}년 연간총액:** {total:,} 원")

    code_summary_df = summarize_by_code(
        filter_by_year(st.session_state.dividend_df.copy(), view_year)
        if view_year != "전체"
        else st.session_state.dividend_df.copy()
    )

    st.subheader(f"🔗 종목코드별 배당금 합계{year_label}")
    st.caption("같은 연도·종목코드로 여러 번 입력한 항목을 자동으로 합산합니다.")

    if code_summary_df.empty:
        st.warning("종목코드를 입력하면 여기에 합계가 표시됩니다.")
    else:
        st.dataframe(
            code_summary_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "입력 건수": st.column_config.NumberColumn("입력 건수", format="%d"),
                "보유수량 합계": st.column_config.NumberColumn("보유수량 합계", format="%d"),
                "연간 총액": st.column_config.NumberColumn("연간 총액", format="%d"),
                **{
                    month: st.column_config.NumberColumn(month, format="%d")
                    for month in MONTH_COLS
                },
            },
        )

        code_total = int(code_summary_df["연간 총액"].sum())
        _, code_total_col = st.columns([3, 1])
        with code_total_col:
            st.markdown(f"**총액:** {code_total:,} 원")

    st.subheader("📅 월별 배당금 합계")
    render_monthly_chart(result_df)


dividend_workspace(monthly_goal, view_year)
