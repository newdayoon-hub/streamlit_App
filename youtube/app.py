from pathlib import Path
import textwrap, zipfile, os

root = Path("/mnt/data/youtube_comment_analyzer")
(root / ".streamlit").mkdir(parents=True, exist_ok=True)
(root / "fonts").mkdir(parents=True, exist_ok=True)

app_code = r'''
import re
from collections import Counter
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import altair as alt
import pandas as pd
import requests
import streamlit as st
from transformers import pipeline
from wordcloud import WordCloud


st.set_page_config(
    page_title="유튜브 댓글 분석기",
    page_icon="💬",
    layout="wide",
)

st.markdown(
    """
    <style>
    .block-container {max-width: 1200px; padding-top: 2rem;}
    [data-testid="stMetricValue"] {font-size: 1.75rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

API_URL = "https://www.googleapis.com/youtube/v3/commentThreads"
FONT_PATH = Path("youtube/NanumGothic.ttf")
MODEL_NAME = "Copycats/koelectra-base-v3-generalized-sentiment-analysis"

STOPWORDS = {
    "영상", "유튜브", "댓글", "진짜", "정말", "너무", "그냥", "이거", "저거",
    "것", "수", "등", "더", "좀", "잘", "안", "왜", "내가", "제가", "우리",
    "이", "그", "저", "을", "를", "은", "는", "이랑", "하고", "에서", "으로",
    "로", "에", "와", "과", "도", "만", "까지", "부터", "한", "하는", "합니다",
    "했어요", "있다", "있는", "없는", "같아요", "ㅋㅋ", "ㅋㅋㅋ", "ㅎㅎ", "ㅠㅠ",
}


def extract_video_id(url_or_id: str) -> str | None:
    """일반 URL, Shorts URL, youtu.be URL 또는 11자리 영상 ID에서 ID를 추출한다."""
    value = url_or_id.strip()

    if re.fullmatch(r"[\w-]{11}", value):
        return value

    try:
        parsed = urlparse(value)
        host = parsed.netloc.lower().replace("www.", "")

        if host == "youtu.be":
            candidate = parsed.path.strip("/").split("/")[0]
            return candidate if re.fullmatch(r"[\w-]{11}", candidate) else None

        if host in {"youtube.com", "m.youtube.com", "music.youtube.com"}:
            if parsed.path == "/watch":
                candidate = parse_qs(parsed.query).get("v", [""])[0]
            elif parsed.path.startswith("/shorts/"):
                candidate = parsed.path.split("/shorts/", 1)[1].split("/")[0]
            elif parsed.path.startswith("/embed/"):
                candidate = parsed.path.split("/embed/", 1)[1].split("/")[0]
            else:
                candidate = ""

            return candidate if re.fullmatch(r"[\w-]{11}", candidate) else None
    except ValueError:
        return None

    return None


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_comments(video_id: str, api_key: str, limit: int) -> pd.DataFrame:
    """YouTube Data API v3에서 최신순 최상위 댓글을 지정 개수만큼 가져온다."""
    rows = []
    page_token = None

    while len(rows) < limit:
        params = {
            "part": "snippet",
            "videoId": video_id,
            "key": api_key,
            "maxResults": min(100, limit - len(rows)),
            "order": "time",
            "textFormat": "plainText",
        }
        if page_token:
            params["pageToken"] = page_token

        response = requests.get(API_URL, params=params, timeout=20)

        if response.status_code != 200:
            try:
                message = response.json()["error"]["message"]
            except Exception:
                message = response.text
            raise RuntimeError(f"YouTube API 오류: {message}")

        payload = response.json()

        for item in payload.get("items", []):
            snippet = item["snippet"]["topLevelComment"]["snippet"]
            rows.append(
                {
                    "작성자": snippet.get("authorDisplayName", ""),
                    "댓글": snippet.get("textDisplay", ""),
                    "작성시각": snippet.get("publishedAt", ""),
                    "수정시각": snippet.get("updatedAt", ""),
                    "좋아요": int(snippet.get("likeCount", 0)),
                    "답글수": int(item["snippet"].get("totalReplyCount", 0)),
                }
            )

        page_token = payload.get("nextPageToken")
        if not page_token:
            break

    df = pd.DataFrame(rows)
    if not df.empty:
        df["작성시각"] = pd.to_datetime(df["작성시각"], utc=True).dt.tz_convert(
            "Asia/Seoul"
        )
    return df


@st.cache_resource(show_spinner="한국어 감성 분석 모델을 불러오는 중입니다...")
def load_sentiment_model():
    return pipeline(
        task="text-classification",
        model=MODEL_NAME,
        tokenizer=MODEL_NAME,
        device=-1,
    )


def normalize_sentiment_label(label: str) -> str:
    value = label.lower()
    if value in {"1", "label_1", "positive", "pos"} or "긍정" in value:
        return "긍정"
    if value in {"0", "label_0", "negative", "neg"} or "부정" in value:
        return "부정"
    return "중립"


def analyze_sentiment(texts: list[str]) -> tuple[list[str], list[float]]:
    classifier = load_sentiment_model()
    cleaned = [str(text)[:500] if str(text).strip() else " " for text in texts]
    outputs = classifier(
        cleaned,
        batch_size=16,
        truncation=True,
        max_length=128,
    )

    labels, scores = [], []
    for output in outputs:
        score = float(output["score"])
        label = normalize_sentiment_label(output["label"])

        # 이 모델은 기본적으로 이진 분류이므로 확신도가 낮은 결과를 중립으로 처리한다.
        if score < 0.65:
            label = "중립"

        labels.append(label)
        scores.append(score)

    return labels, scores


def tokenize_korean(texts: pd.Series) -> list[str]:
    """가벼운 정규식 기반 토큰화. 두 글자 이상의 한글 단어만 남긴다."""
    words = []
    for text in texts.fillna("").astype(str):
        tokens = re.findall(r"[가-힣]{2,}", text)
        words.extend(token for token in tokens if token not in STOPWORDS)
    return words


def make_wordcloud(words: list[str]):
    if not FONT_PATH.exists():
        raise FileNotFoundError(
            f"한글 폰트 파일이 없습니다: {FONT_PATH}. "
            "GitHub 저장소의 fonts 폴더에 NanumGothic.ttf를 넣어 주세요."
        )

    frequencies = Counter(words)
    if not frequencies:
        return None

    return WordCloud(
        font_path=str(FONT_PATH),
        width=1200,
        height=650,
        background_color="white",
        max_words=120,
        collocations=False,
        prefer_horizontal=0.9,
        random_state=42,
    ).generate_from_frequencies(frequencies)


def sentiment_chart(df: pd.DataFrame):
    counts = (
        df["감성"]
        .value_counts()
        .reindex(["긍정", "중립", "부정"], fill_value=0)
        .rename_axis("감성")
        .reset_index(name="댓글 수")
    )
    return (
        alt.Chart(counts)
        .mark_arc(innerRadius=55)
        .encode(
            theta=alt.Theta("댓글 수:Q"),
            color=alt.Color(
                "감성:N",
                scale=alt.Scale(
                    domain=["긍정", "중립", "부정"],
                    range=["#2EAD72", "#F2B84B", "#E65B65"],
                ),
                legend=alt.Legend(orient="bottom"),
            ),
            tooltip=["감성:N", "댓글 수:Q"],
        )
        .properties(height=330)
    )


st.title("💬 유튜브 댓글 분석기")
st.caption(
    "영상 링크를 입력하면 최신 댓글을 수집해 작성 추이, 감성 반응, 핵심 단어를 분석합니다."
)

with st.sidebar:
    st.header("분석 설정")
    video_url = st.text_input(
        "유튜브 영상 링크",
        placeholder="https://www.youtube.com/watch?v=...",
    )
    comment_limit = st.slider(
        "분석할 댓글 개수",
        min_value=20,
        max_value=500,
        value=100,
        step=20,
    )
    analyze_button = st.button(
        "댓글 분석 시작",
        type="primary",
        use_container_width=True,
    )
    st.caption("댓글은 최신순으로 수집하며, 답글은 개수만 표시합니다.")

if analyze_button:
    video_id = extract_video_id(video_url)

    if not video_id:
        st.error("올바른 유튜브 영상 링크 또는 11자리 영상 ID를 입력해 주세요.")
        st.stop()

    try:
        api_key = st.secrets["YOUTUBE_API_KEY"]
    except (KeyError, FileNotFoundError):
        st.error(
            "YouTube API 키가 설정되지 않았습니다. "
            "Streamlit Cloud의 App settings → Secrets에 "
            '`YOUTUBE_API_KEY = "키"` 형식으로 등록해 주세요.'
        )
        st.stop()

    st.subheader("영상")
    st.video(f"https://www.youtube.com/watch?v={video_id}")

    try:
        with st.spinner("유튜브 댓글을 가져오는 중입니다..."):
            comments = fetch_comments(video_id, api_key, comment_limit)
    except Exception as error:
        st.error(str(error))
        st.info(
            "댓글이 비활성화된 영상, 비공개 영상, 잘못된 API 키 또는 "
            "API 할당량 초과 여부를 확인해 주세요."
        )
        st.stop()

    if comments.empty:
        st.warning("가져올 수 있는 공개 댓글이 없습니다.")
        st.stop()

    with st.spinner("댓글의 감성을 분석하는 중입니다..."):
        comments["감성"], comments["감성확신도"] = analyze_sentiment(
            comments["댓글"].tolist()
        )

    comments["날짜"] = comments["작성시각"].dt.date.astype(str)
    comments["시간대"] = comments["작성시각"].dt.hour

    positive_rate = (comments["감성"] == "긍정").mean() * 100
    negative_rate = (comments["감성"] == "부정").mean() * 100
    avg_likes = comments["좋아요"].mean()

    st.divider()
    metric1, metric2, metric3, metric4 = st.columns(4)
    metric1.metric("수집 댓글", f"{len(comments):,}개")
    metric2.metric("긍정 반응", f"{positive_rate:.1f}%")
    metric3.metric("부정 반응", f"{negative_rate:.1f}%")
    metric4.metric("평균 좋아요", f"{avg_likes:.1f}개")

    st.subheader("1. 댓글 작성 추이")
    tab_daily, tab_hourly = st.tabs(["날짜별 추이", "시간대별 분포"])

    with tab_daily:
        daily = comments.groupby("날짜", as_index=False).size()
        daily.columns = ["날짜", "댓글 수"]
        daily_chart = (
            alt.Chart(daily)
            .mark_line(point=True)
            .encode(
                x=alt.X("날짜:T", title="작성 날짜"),
                y=alt.Y("댓글 수:Q", title="댓글 수"),
                tooltip=[
                    alt.Tooltip("날짜:T", title="날짜"),
                    alt.Tooltip("댓글 수:Q", title="댓글 수"),
                ],
            )
            .properties(height=360)
        )
        st.altair_chart(daily_chart, use_container_width=True)

    with tab_hourly:
        hourly = (
            comments.groupby("시간대", as_index=False)
            .size()
            .set_index("시간대")
            .reindex(range(24), fill_value=0)
            .rename(columns={"size": "댓글 수"})
            .reset_index()
        )
        hourly_chart = (
            alt.Chart(hourly)
            .mark_bar()
            .encode(
                x=alt.X(
                    "시간대:O",
                    title="작성 시간대(한국 시간)",
                    sort=list(range(24)),
                ),
                y=alt.Y("댓글 수:Q", title="댓글 수"),
                tooltip=["시간대:O", "댓글 수:Q"],
            )
            .properties(height=360)
        )
        st.altair_chart(hourly_chart, use_container_width=True)

    st.subheader("2. 댓글 반응도")
    reaction_left, reaction_right = st.columns([1, 1.35])

    with reaction_left:
        st.altair_chart(sentiment_chart(comments), use_container_width=True)

    with reaction_right:
        sentiment_likes = (
            comments.groupby("감성", as_index=False)["좋아요"]
            .mean()
            .rename(columns={"좋아요": "평균 좋아요"})
        )
        likes_chart = (
            alt.Chart(sentiment_likes)
            .mark_bar()
            .encode(
                x=alt.X(
                    "감성:N",
                    sort=["긍정", "중립", "부정"],
                    title="감성",
                ),
                y=alt.Y("평균 좋아요:Q", title="평균 좋아요 수"),
                tooltip=[
                    "감성:N",
                    alt.Tooltip("평균 좋아요:Q", format=".2f"),
                ],
                color=alt.Color(
                    "감성:N",
                    scale=alt.Scale(
                        domain=["긍정", "중립", "부정"],
                        range=["#2EAD72", "#F2B84B", "#E65B65"],
                    ),
                    legend=None,
                ),
            )
            .properties(height=330)
        )
        st.altair_chart(likes_chart, use_container_width=True)

    st.caption(
        "감성 분석은 한국어 분류 모델의 추정 결과입니다. "
        "반어법, 짧은 표현, 이모지 중심 댓글은 잘못 분류될 수 있습니다."
    )

    st.subheader("3. 한글 워드클라우드")
    words = tokenize_korean(comments["댓글"])

    try:
        wordcloud = make_wordcloud(words)
        if wordcloud is None:
            st.info("워드클라우드를 만들 수 있는 두 글자 이상의 한글 단어가 부족합니다.")
        else:
            st.image(
                wordcloud.to_array(),
                use_container_width=True,
                caption="댓글에서 자주 등장한 한글 단어",
            )

            top_words = pd.DataFrame(
                Counter(words).most_common(20),
                columns=["단어", "빈도"],
            )
            with st.expander("상위 단어 빈도 보기"):
                st.dataframe(top_words, use_container_width=True, hide_index=True)
    except FileNotFoundError as error:
        st.error(str(error))

    st.subheader("4. 댓글 데이터")
    display_df = comments[
        ["작성시각", "작성자", "댓글", "좋아요", "답글수", "감성", "감성확신도"]
    ].copy()
    display_df["작성시각"] = display_df["작성시각"].dt.strftime(
        "%Y-%m-%d %H:%M"
    )
    display_df["감성확신도"] = display_df["감성확신도"].round(3)

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "댓글": st.column_config.TextColumn(width="large"),
            "감성확신도": st.column_config.ProgressColumn(
                min_value=0.0,
                max_value=1.0,
                format="%.3f",
            ),
        },
    )

    csv_data = display_df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "분석 결과 CSV 다운로드",
        data=csv_data,
        file_name=f"youtube_comments_{video_id}.csv",
        mime="text/csv",
    )
else:
    st.info("왼쪽에서 유튜브 링크와 댓글 개수를 설정한 뒤 분석을 시작해 주세요.")
'''

requirements = '''streamlit>=1.42,<2
pandas>=2.2,<3
requests>=2.32,<3
altair>=5.4,<6
wordcloud>=1.9.4,<2
Pillow>=10.4,<12
transformers>=4.48,<5
torch>=2.5,<3
safetensors>=0.5,<1
sentencepiece>=0.2,<1
'''

secrets_example = '''YOUTUBE_API_KEY = "여기에_YouTube_Data_API_v3_키를_입력"
'''

gitignore = '''.streamlit/secrets.toml
__pycache__/
*.pyc
'''

   └─ secrets.toml   # 로컬 테스트용이며 GitHub에 올리지 않음
