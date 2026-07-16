from pathlib import Path
import math
import re

import numpy as np
import pandas as pd
import pydeck as pdk
import streamlit as st


st.set_page_config(
    page_title="서울 공영주차장 찾기",
    page_icon="🅿️",
    layout="wide",
)

DEFAULT_CSV = Path(__file__).with_name("seoul_public_parking.csv")
SEOUL_CENTER = {"lat": 37.5665, "lon": 126.9780}


# -----------------------------
# 데이터 불러오기 및 전처리
# -----------------------------
@st.cache_data(show_spinner=False)
def read_csv_file(file_or_path):
    """서울시 CSV의 주요 인코딩을 순서대로 시도해 읽는다."""
    encodings = ("cp949", "euc-kr", "utf-8-sig", "utf-8")
    last_error = None

    for encoding in encodings:
        try:
            if hasattr(file_or_path, "seek"):
                file_or_path.seek(0)
            return pd.read_csv(file_or_path, encoding=encoding)
        except UnicodeDecodeError as error:
            last_error = error

    raise ValueError(
        "CSV 인코딩을 확인할 수 없습니다. CP949, EUC-KR 또는 UTF-8 형식의 파일을 사용해 주세요."
    ) from last_error


def find_column(df, candidates, required=False):
    """후보 이름 중 실제 데이터에 존재하는 첫 번째 열을 반환한다."""
    normalized = {str(col).strip(): col for col in df.columns}
    for candidate in candidates:
        if candidate in normalized:
            return normalized[candidate]

    if required:
        raise KeyError(f"필수 열을 찾지 못했습니다: {', '.join(candidates)}")
    return None


def numeric_series(df, column, default=np.nan):
    if column is None:
        return pd.Series(default, index=df.index, dtype="float64")
    return pd.to_numeric(df[column], errors="coerce")


def text_series(df, column, default=""):
    if column is None:
        return pd.Series(default, index=df.index, dtype="object")
    return df[column].fillna("").astype(str).str.strip()


def format_hhmm(value):
    """0, 930, 2400 같은 값을 00:00, 09:30, 24:00 형식으로 바꾼다."""
    if pd.isna(value):
        return "정보 없음"
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return "정보 없음"

    if number == 2400:
        return "24:00"

    hour, minute = divmod(number, 100)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return "정보 없음"
    return f"{hour:02d}:{minute:02d}"


def format_won(value):
    if pd.isna(value):
        return "정보 없음"
    value = float(value)
    if value <= 0:
        return "무료"
    return f"{value:,.0f}원"


def calculate_fee(row, minutes, day_type):
    """
    선택한 주차 시간의 예상 요금을 계산한다.
    토요일/공휴일 무료 표시가 있으면 0원으로 처리한다.
    그 외에는 기본요금 + 추가요금 방식으로 계산하고 일 최대요금을 적용한다.
    """
    if row["is_free"]:
        return 0.0

    if day_type == "토요일" and row["saturday_free"]:
        return 0.0
    if day_type == "공휴일" and row["holiday_free"]:
        return 0.0

    base_fee = row["base_fee"]
    base_minutes = row["base_minutes"]
    extra_fee = row["extra_fee"]
    extra_minutes = row["extra_minutes"]

    if pd.isna(base_fee):
        return np.nan

    base_fee = max(float(base_fee), 0)
    base_minutes = float(base_minutes) if pd.notna(base_minutes) else 0
    extra_fee = float(extra_fee) if pd.notna(extra_fee) else 0
    extra_minutes = float(extra_minutes) if pd.notna(extra_minutes) else 0

    if base_fee == 0:
        fee = 0.0
    elif base_minutes <= 0:
        fee = base_fee
    elif minutes <= base_minutes:
        fee = base_fee
    elif extra_minutes > 0:
        extra_count = math.ceil((minutes - base_minutes) / extra_minutes)
        fee = base_fee + extra_count * extra_fee
    else:
        fee = base_fee

    daily_max = row["daily_max"]
    if pd.notna(daily_max) and float(daily_max) > 0:
        fee = min(fee, float(daily_max))

    return float(fee)


def operation_text(row, day_type):
    if day_type == "평일":
        start, end = row["weekday_start"], row["weekday_end"]
    elif day_type == "토요일":
        start, end = row["weekend_start"], row["weekend_end"]
    else:
        start, end = row["holiday_start"], row["holiday_end"]

    if pd.isna(start) or pd.isna(end):
        return "운영시간 정보 없음"

    if int(float(start)) == 0 and int(float(end)) == 2400:
        return "24시간 운영"

    if int(float(start)) == 0 and int(float(end)) == 0:
        return "운영 여부 확인 필요"

    return f"{format_hhmm(start)}~{format_hhmm(end)}"


def is_operating(row, day_type):
    if day_type == "평일":
        start, end = row["weekday_start"], row["weekday_end"]
    elif day_type == "토요일":
        start, end = row["weekend_start"], row["weekend_end"]
    else:
        start, end = row["holiday_start"], row["holiday_end"]

    if pd.isna(start) or pd.isna(end):
        return False

    try:
        start, end = int(float(start)), int(float(end))
    except (TypeError, ValueError):
        return False

    # 00:00~24:00은 24시간 운영, 00:00~00:00은 불명확하므로 제외
    return end == 2400 or start != end


def prepare_data(raw):
    raw = raw.copy()
    raw.columns = [str(col).strip() for col in raw.columns]

    columns = {
        "name": find_column(raw, ["주차장명", "주차장 명"], required=True),
        "address": find_column(raw, ["주소", "도로명주소", "소재지도로명주소", "소재지지번주소"], required=True),
        "lat": find_column(raw, ["위도", "LAT", "lat", "latitude"], required=True),
        "lon": find_column(raw, ["경도", "LNG", "lon", "longitude"], required=True),
        "type": find_column(raw, ["주차장 종류명", "주차장종류명", "주차장 종류"]),
        "phone": find_column(raw, ["전화번호", "연락처"]),
        "spaces": find_column(raw, ["총 주차면", "주차구획수", "주차면수"]),
        "free_name": find_column(raw, ["유무료구분명", "유무료 구분명"]),
        "free_code": find_column(raw, ["유무료구분", "유무료 구분"]),
        "night_name": find_column(raw, ["야간무료개방여부명"]),
        "night_code": find_column(raw, ["야간무료개방여부"]),
        "saturday_name": find_column(raw, ["토요일 유,무료 구분명", "토요일 유무료 구분명"]),
        "holiday_name": find_column(raw, ["공휴일 유,무료 구분명", "공휴일 유무료 구분명"]),
        "weekday_start": find_column(raw, ["평일 운영 시작시각(HHMM)", "평일운영시작시각"]),
        "weekday_end": find_column(raw, ["평일 운영 종료시각(HHMM)", "평일운영종료시각"]),
        "weekend_start": find_column(raw, ["주말 운영 시작시각(HHMM)", "주말운영시작시각"]),
        "weekend_end": find_column(raw, ["주말 운영 종료시각(HHMM)", "주말운영종료시각"]),
        "holiday_start": find_column(raw, ["공휴일 운영 시작시각(HHMM)", "공휴일운영시작시각"]),
        "holiday_end": find_column(raw, ["공휴일 운영 종료시각(HHMM)", "공휴일운영종료시각"]),
        "base_fee": find_column(raw, ["기본 주차 요금", "기본주차요금"]),
        "base_minutes": find_column(raw, ["기본 주차 시간(분 단위)", "기본주차시간"]),
        "extra_fee": find_column(raw, ["추가 단위 요금", "추가단위요금"]),
        "extra_minutes": find_column(raw, ["추가 단위 시간(분 단위)", "추가단위시간"]),
        "daily_max": find_column(raw, ["일 최대 요금", "일최대요금"]),
        "monthly": find_column(raw, ["월 정기권 금액", "월정기권금액"]),
        "live_info": find_column(raw, ["주차현황 정보 제공여부명"]),
    }

    data = pd.DataFrame(index=raw.index)
    data["name"] = text_series(raw, columns["name"])
    data["address"] = text_series(raw, columns["address"])
    data["lat"] = numeric_series(raw, columns["lat"])
    data["lon"] = numeric_series(raw, columns["lon"])
    data["parking_type"] = text_series(raw, columns["type"], "정보 없음")
    data["phone"] = text_series(raw, columns["phone"], "정보 없음")
    data["spaces"] = numeric_series(raw, columns["spaces"])
    data["free_name"] = text_series(raw, columns["free_name"])
    data["free_code"] = text_series(raw, columns["free_code"])
    data["night_name"] = text_series(raw, columns["night_name"])
    data["night_code"] = text_series(raw, columns["night_code"])
    data["saturday_name"] = text_series(raw, columns["saturday_name"])
    data["holiday_name"] = text_series(raw, columns["holiday_name"])
    data["live_info"] = text_series(raw, columns["live_info"], "정보 없음")

    for key in (
        "weekday_start", "weekday_end", "weekend_start", "weekend_end",
        "holiday_start", "holiday_end", "base_fee", "base_minutes",
        "extra_fee", "extra_minutes", "daily_max", "monthly"
    ):
        data[key] = numeric_series(raw, columns[key])

    district_from_address = data["address"].str.extract(r"((?:서울특별시\s+)?[가-힣]+구)", expand=False)
    district_from_address = district_from_address.str.replace("서울특별시 ", "", regex=False)
    data["district"] = district_from_address.fillna("자치구 정보 없음")

    data["is_free"] = (
        data["free_name"].str.contains("무료", na=False)
        | data["free_code"].str.upper().eq("N")
        | data["base_fee"].fillna(-1).eq(0)
    )
    data["saturday_free"] = data["saturday_name"].str.contains("무료", na=False)
    data["holiday_free"] = data["holiday_name"].str.contains("무료", na=False)
    data["night_open"] = (
        data["night_name"].str.contains("개방", na=False)
        & ~data["night_name"].str.contains("미개방", na=False)
    ) | data["night_code"].str.upper().eq("Y")

    data["valid_coordinate"] = (
        data["lat"].between(37.0, 38.0)
        & data["lon"].between(126.0, 128.0)
    )

    data = data[data["name"].ne("") & data["address"].ne("")].copy()
    return data


# -----------------------------
# 화면
# -----------------------------
st.title("🅿️ 서울 공영주차장 찾기")
st.caption("자치구·요금·운영 조건을 비교하고 지도에서 공영주차장 위치를 확인하세요.")

with st.sidebar:
    st.header("데이터")
    uploaded_file = st.file_uploader(
        "서울시 공영주차장 CSV 업로드",
        type=["csv"],
        help="업로드하지 않으면 앱에 포함된 기본 CSV를 사용합니다.",
    )
    st.caption("업로드 파일은 현재 세션에서만 사용됩니다.")

try:
    raw_df = read_csv_file(uploaded_file if uploaded_file is not None else DEFAULT_CSV)
    parking = prepare_data(raw_df)
except Exception as error:
    st.error(f"데이터를 불러오지 못했습니다: {error}")
    st.stop()

districts = sorted([x for x in parking["district"].dropna().unique() if x != "자치구 정보 없음"])

with st.sidebar:
    st.header("검색 조건")
    selected_district = st.selectbox("자치구", ["전체"] + districts)
    day_type = st.radio("이용일", ["평일", "토요일", "공휴일"], horizontal=True)
    parking_minutes = st.slider(
        "예상 주차 시간",
        min_value=10,
        max_value=720,
        value=60,
        step=10,
        format="%d분",
    )

    search_text = st.text_input("주차장명·주소 검색", placeholder="예: 강남역, 종로구")
    only_free = st.checkbox("무료 주차장만")
    only_operating = st.checkbox(f"{day_type} 운영 주차장만", value=True)
    only_day_free = st.checkbox(f"{day_type} 무료 주차장만", value=False)
    only_night = st.checkbox("야간 무료 개방만")
    min_spaces = st.number_input("최소 주차면", min_value=0, value=0, step=10)

    st.header("지도 설정")
    max_markers = st.slider("지도에 표시할 최대 마커 수", 100, 1500, 800, 100)

parking["operating"] = parking.apply(lambda row: is_operating(row, day_type), axis=1)
parking["operation_text"] = parking.apply(lambda row: operation_text(row, day_type), axis=1)
parking["estimated_fee"] = parking.apply(
    lambda row: calculate_fee(row, parking_minutes, day_type), axis=1
)

if day_type == "평일":
    parking["selected_day_free"] = parking["is_free"]
elif day_type == "토요일":
    parking["selected_day_free"] = parking["is_free"] | parking["saturday_free"]
else:
    parking["selected_day_free"] = parking["is_free"] | parking["holiday_free"]

filtered = parking.copy()

if selected_district != "전체":
    filtered = filtered[filtered["district"].eq(selected_district)]

if search_text.strip():
    keyword = re.escape(search_text.strip())
    filtered = filtered[
        filtered["name"].str.contains(keyword, case=False, na=False, regex=True)
        | filtered["address"].str.contains(keyword, case=False, na=False, regex=True)
    ]

if only_free:
    filtered = filtered[filtered["is_free"]]
if only_operating:
    filtered = filtered[filtered["operating"]]
if only_day_free:
    filtered = filtered[filtered["selected_day_free"]]
if only_night:
    filtered = filtered[filtered["night_open"]]
if min_spaces > 0:
    filtered = filtered[filtered["spaces"].fillna(0).ge(min_spaces)]

# 예상요금이 알려진 곳을 먼저 보여주고, 같은 요금이면 주차면이 큰 곳을 우선한다.
filtered = filtered.sort_values(
    ["estimated_fee", "spaces", "name"],
    ascending=[True, False, True],
    na_position="last",
).copy()

known_fee_count = filtered["estimated_fee"].notna().sum()
free_count = filtered["selected_day_free"].sum()
coordinate_count = filtered["valid_coordinate"].sum()

m1, m2, m3, m4 = st.columns(4)
m1.metric("검색 결과", f"{len(filtered):,}곳")
m2.metric(f"{day_type} 무료", f"{int(free_count):,}곳")
m3.metric("요금 계산 가능", f"{int(known_fee_count):,}곳")
m4.metric("지도 표시 가능", f"{int(coordinate_count):,}곳")

if filtered.empty:
    st.warning("조건에 맞는 주차장이 없습니다. 필터 조건을 줄여 보세요.")
    st.stop()

# -----------------------------
# 최저가 추천
# -----------------------------
st.subheader("💡 가장 저렴한 주차장 추천")

recommendable = filtered[filtered["estimated_fee"].notna()].copy()
if recommendable.empty:
    st.info("현재 조건에서는 요금을 계산할 수 있는 주차장이 없습니다.")
else:
    min_fee = recommendable["estimated_fee"].min()
    cheapest = recommendable[recommendable["estimated_fee"].eq(min_fee)].head(3)

    cols = st.columns(len(cheapest))
    for col, (_, row) in zip(cols, cheapest.iterrows()):
        with col:
            st.markdown(f"#### {row['name']}")
            st.metric(f"{parking_minutes}분 예상 요금", format_won(row["estimated_fee"]))
            st.write(row["address"])
            st.caption(
                f"{day_type} {row['operation_text']} · "
                f"주차면 {int(row['spaces']):,}면"
                if pd.notna(row["spaces"])
                else f"{day_type} {row['operation_text']} · 주차면 정보 없음"
            )

    if len(recommendable[recommendable["estimated_fee"].eq(min_fee)]) > 3:
        st.caption("같은 최저 예상 요금의 주차장이 더 있습니다. 아래 목록에서 확인할 수 있습니다.")

st.caption(
    "예상 요금은 CSV의 기본요금·기본시간·추가요금·추가시간·일 최대요금을 기준으로 계산한 값입니다. "
    "현장 정책과 다를 수 있으므로 방문 전 운영기관에 확인하세요."
)

# -----------------------------
# 지도
# -----------------------------
st.subheader("🗺️ 주차장 지도")

map_df = filtered[filtered["valid_coordinate"]].head(max_markers).copy()

if map_df.empty:
    st.info("현재 검색 결과에는 지도에 표시할 수 있는 위도·경도 정보가 없습니다.")
else:
    map_df["fee_label"] = map_df["estimated_fee"].apply(format_won)
    map_df["base_fee_label"] = map_df["base_fee"].apply(format_won)
    map_df["space_label"] = map_df["spaces"].apply(
        lambda x: f"{int(x):,}면" if pd.notna(x) else "정보 없음"
    )
    map_df["free_label"] = np.where(map_df["selected_day_free"], f"{day_type} 무료", "유료")
    map_df["night_label"] = np.where(map_df["night_open"], "야간 무료 개방", "야간 무료 미개방")
    map_df["marker_color"] = map_df["selected_day_free"].map(
        {True: [34, 197, 94, 190], False: [37, 99, 235, 180]}
    )

    center_lat = float(map_df["lat"].median())
    center_lon = float(map_df["lon"].median())
    zoom = 11.5 if selected_district != "전체" else 9.8

    layer = pdk.Layer(
        "ScatterplotLayer",
        data=map_df,
        get_position="[lon, lat]",
        get_fill_color="marker_color",
        get_radius=70 if selected_district != "전체" else 95,
        radius_min_pixels=4,
        radius_max_pixels=14,
        pickable=True,
        auto_highlight=True,
        stroked=True,
        get_line_color=[255, 255, 255, 180],
        line_width_min_pixels=1,
    )

    tooltip = {
        "html": """
        <div style="font-family: sans-serif; max-width: 310px;">
          <b style="font-size: 15px;">{name}</b><br/>
          <span>📍 {address}</span><br/>
          <span>💳 예상 요금: <b>{fee_label}</b></span><br/>
          <span>🕒 {operation_text}</span><br/>
          <span>🅿️ {space_label} · {free_label}</span><br/>
          <span>🌙 {night_label}</span>
        </div>
        """,
        "style": {
            "backgroundColor": "rgba(20, 24, 32, 0.94)",
            "color": "white",
            "fontSize": "13px",
            "padding": "10px",
        },
    }

    deck = pdk.Deck(
        layers=[layer],
        initial_view_state=pdk.ViewState(
            latitude=center_lat,
            longitude=center_lon,
            zoom=zoom,
            pitch=0,
        ),
        map_style=None,
        tooltip=tooltip,
    )
    st.pydeck_chart(deck, use_container_width=True, height=600)
    st.caption("초록 마커는 선택한 이용일에 무료, 파란 마커는 유료입니다. 마커에 마우스를 올리면 상세 정보가 표시됩니다.")

# -----------------------------
# 비교 목록 및 다운로드
# -----------------------------
st.subheader("📋 검색 결과 비교")

display = filtered.copy()
display["예상 요금"] = display["estimated_fee"].apply(format_won)
display["기본 요금"] = display["base_fee"].apply(format_won)
display["운영시간"] = display["operation_text"]
display["무료 여부"] = np.where(display["selected_day_free"], f"{day_type} 무료", "유료")
display["야간 개방"] = np.where(display["night_open"], "무료 개방", "미개방")
display["총 주차면"] = display["spaces"].apply(
    lambda x: int(x) if pd.notna(x) else None
)

table = display[
    [
        "name", "district", "address", "예상 요금", "기본 요금",
        "운영시간", "무료 여부", "야간 개방", "총 주차면",
        "parking_type", "phone"
    ]
].rename(
    columns={
        "name": "주차장명",
        "district": "자치구",
        "address": "주소",
        "parking_type": "종류",
        "phone": "전화번호",
    }
)

st.dataframe(
    table,
    use_container_width=True,
    hide_index=True,
    column_config={
        "주차장명": st.column_config.TextColumn(width="medium"),
        "주소": st.column_config.TextColumn(width="large"),
        "예상 요금": st.column_config.TextColumn(width="small"),
        "운영시간": st.column_config.TextColumn(width="medium"),
    },
)

download_df = filtered.copy()
download_df["선택 이용일"] = day_type
download_df["선택 주차시간(분)"] = parking_minutes
download_df["예상 요금(원)"] = download_df["estimated_fee"]
download_df["선택일 운영시간"] = download_df["operation_text"]

st.download_button(
    "⬇️ 현재 검색 결과 CSV 내려받기",
    data=download_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
    file_name="filtered_public_parking.csv",
    mime="text/csv",
)

with st.expander("앱 사용 안내와 데이터 주의사항"):
    st.markdown(
        """
        - **자치구별 최저가 추천**은 선택한 이용일과 예상 주차시간을 반영합니다.
        - **무료 판단**은 전체 무료 여부와 토요일·공휴일 무료 여부를 함께 사용합니다.
        - 좌표가 없는 주차장은 표와 추천에는 나타날 수 있지만 지도에는 표시되지 않습니다.
        - `00:00~24:00`은 24시간 운영으로 처리합니다.
        - `00:00~00:00`은 휴무인지 정보 누락인지 구분하기 어려워 ‘운영 여부 확인 필요’로 표시합니다.
        - 실시간 잔여 주차면 데이터가 아니라 안내 정보이므로 실제 이용 가능 여부는 현장에서 달라질 수 있습니다.
        """
    )
