from pathlib import Path
import zipfile
import textwrap

root = Path("/mnt/data/youtube_comment_analyzer_rebuilt")
(root / "youtube" / "fonts").mkdir(parents=True, exist_ok=True)
(root / "youtube" / ".streamlit").mkdir(parents=True, exist_ok=True)

app_py = r'''
import re
from collections import Counter
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from wordcloud import WordCloud


st.set_page_config(
    page_title="YouTube 댓글 분석기",
    page_icon="💬",
    layout="wide",
)

FONT_PATH = Path(__file__).parent / "fonts" / "NanumGothic.ttf"

STOPWORDS = {
    "이", "그", "저", "것", "수", "등", "들", "및", "더", "좀", "정말", "진짜",
    "너무", "영상", "유튜브", "댓글", "사람", "때", "거", "게", "듯", "왜",
    "뭐", "어떻게", "여기", "저기", "그리고", "하지만", "그래서", "에서", "으로",
    "에게", "하고", "하는", "하면", "한", "하다", "합니다", "입니다", "있는",
    "없는", "있다", "없다", "같다", "같아요", "네요", "는데", "ㅋㅋ", "ㅎㅎ",
    "the", "a", "an", "and", "or", "to", "of", "in", "is", "it", "this", "that",
}

POSITIVE_WORDS = {
    "좋다", "좋아요", "좋아", "최고", "멋지다", "멋져", "대박", "감동",
    "재밌다", "재미있다", "웃기다", "훌륭", "완벽", "응원", "고맙다",
    "감사", "사랑", "행복", "유익", "도움", "추천", "기대", "신기",
    "예쁘다", "귀엽다", "존경", "성공", "잘한다", "잘했", "공감",
    "good", "great", "best", "love", "amazing", "awesome", "nice",
}

NEGATIVE_WORDS = {
    "싫다", "싫어", "별로", "최악", "실망", "화난다", "짜증", "노잼",
    "재미없다", "이상하다", "틀리다", "문제", "불편", "무섭다", "걱정",
    "비추천", "답답", "심하다", "나쁘다", "못하다", "아쉽다", "거짓",
    "오류", "실패", "bad", "worst", "hate", "boring", "wrong", "terrible",
}

POSITIVE_EMOJIS = {"😀", "😃", "😄", "😁", "😊", "😍", "🥰", "👍", "❤", "❤️", "🔥", "👏", "🎉", "✨", "💯"}
NEGATIVE_EMOJIS = {"😡", "😠", "🤬", "😢", "😭", "👎", "💔", "😞", "😒", "😤"}


def extract_video_id(value: str) -> str | None:
    value = value.strip()

    if re.fullmatch(r"[A-Za-z0-9_-]{11}", value):
        return value

    try:
        parsed = urlparse(value)
        host = parsed.netloc.lower().replace("www.", "")
        candidate = None

        if host == "youtu.be":
            candidate = parsed.path.strip("/").split("/")[0]

        elif host in {"youtube.com", "m.youtube.com", "music.youtube.com"}:
            if parsed.path == "/watch":
                candidate = parse_qs(parsed.query).get("v", [None])[0]
            elif parsed.path.startswith("/shorts/"):
                candidate = parsed.path.split("/shorts/")[1].split("/")[0]
            elif parsed.path.startswith("/embed/"):
                candidate = parsed.path.split("/embed/")[1].split("/")[0]
            elif parsed.path.startswith("/live/"):
                candidate = parsed.path.split("/live/")[1].split("/")[0]

        if candidate and re.fullmatch(r"[A-Za-z0-9_-]{11}", candidate):
            return candidate

    except Exception:
        return None

    return None


def get_api_key() -> str:
    try:
        key = str(st.secrets["YOUTUBE_API_KEY"]).strip()
    except Exception:
        st.error(
            "YouTube API 키가 설정되지 않았습니다.\n\n"
            'Streamlit Cloud의 App settings → Secrets에 다음 형식으로 입력하세요.\n\n'
            'YOUTUBE_API_KEY = "발급받은_API_KEY"'
        )
        st.stop()

    if not key:
        st.error("Secrets의 YOUTUBE_API_KEY 값이 비어 있습니다.")
        st.stop()

    return key


def youtube_client(api_key: str):
    return build(
        "youtube",
        "v3",
        developerKey=api_key,
        cache_discovery=False,
    )


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_video_info(api_key: str, video_id: str) -> dict:
    youtube = youtube_client(api_key)

    response = youtube.videos().list(
        part="snippet,statistics",
        id=video_id,
    ).execute()

    items = response.get("items", [])
    if not items:
        raise ValueError("영상을 찾을 수 없습니다. 삭제·비공개 영상인지 확인하세요.")

    item = items[0]
    snippet = item.get("snippet", {})
    statistics = item.get("statistics", {})

    return {
        "title": snippet.get("title", ""),
        "channel": snippet.get("channelTitle", ""),
        "published_at": snippet.get("publishedAt", ""),
        "view_count": int(statistics.get("viewCount", 0)),
        "like_count": int(statistics.get("likeCount", 0)),
        "comment_count": int(statistics.get("commentCount", 0)),
    }


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_comments(
    api_key: str,
    video_id: str,
    requested_count: int,
    order: str,
) -> pd.DataFrame:
    youtube = youtube_client(api_key)

    rows = []
    page_token = None

    while len(rows) < requested_count:
        request_count = min(100, requested_count - len(rows))

        response = youtube.commentThreads().list(
            part="snippet",
            videoId=video_id,
            maxResults=request_count,
            order=order,
            textFormat="plainText",
            pageToken=page_token,
        ).execute()

        for item in response.get("items", []):
            thread_snippet = item.get("snippet", {})
            top_level = thread_snippet.get("topLevelComment", {})
            snippet = top_level.get("snippet", {})

            rows.append(
                {
                    "작성자": snippet.get("authorDisplayName", "알 수 없음"),
                    "댓글": snippet.get("textDisplay", ""),
                    "좋아요": int(snippet.get("likeCount", 0)),
                    "답글 수": int(thread_snippet.get("totalReplyCount", 0)),
                    "작성 시각": snippet.get("publishedAt"),
                }
            )

            if len(rows) >= requested_count:
                break

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    df = pd.DataFrame(rows)

    if not df.empty:
        df["작성 시각"] = pd.to_datetime(
            df["작성 시각"],
            utc=True,
            errors="coerce",
        )
        df["작성 시각(KST)"] = df["작성 시각"].dt.tz_convert("Asia/Seoul")

    return df


def classify_sentiment(text: str) -> str:
    value = str(text).lower()

    positive_score = sum(1 for word in POSITIVE_WORDS if word in value)
    negative_score = sum(1 for word in NEGATIVE_WORDS if word in value)

    positive_score += sum(value.count(emoji) for emoji in POSITIVE_EMOJIS)
    negative_score += sum(value.count(emoji) for emoji in NEGATIVE_EMOJIS)

    if "ㅋㅋ" in value or "ㅎㅎ" in value:
        positive_score += 1

    if positive_score > negative_score:
        return "긍정"
    if negative_score > positive_score:
        return "부정"
    return "중립"


def tokenize(text: str) -> list[str]:
    value = re.sub(r"https?://\S+|www\.\S+", " ", str(text))
    value = re.sub(r"[@#][A-Za-z0-9_가-힣]+", " ", value)

    tokens = re.findall(r"[가-힣]{2,}|[A-Za-z]{2,}", value.lower())

    return [
        token
        for token in tokens
        if token not in STOPWORDS and not token.isdigit()
    ]


def handle_http_error(error: HttpError) -> None:
    message = str(error)

    if "commentsDisabled" in message:
        st.error("이 영상은 댓글이 비활성화되어 있어 분석할 수 없습니다.")
    elif "quotaExceeded" in message or "dailyLimitExceeded" in message:
        st.error("YouTube Data API 일일 할당량을 초과했습니다.")
    elif "videoNotFound" in message:
        st.error("영상을 찾을 수 없습니다.")
    else:
        st.error("YouTube API 요청 중 오류가 발생했습니다.")
        with st.expander("오류 상세 보기"):
            st.code(message)


def format_kst(value: str) -> str:
    timestamp = pd.to_datetime(value, utc=True, errors="coerce")

    if pd.isna(timestamp):
        return "-"

    return timestamp.tz_convert("Asia/Seoul").strftime("%Y-%m-%d %H:%M")


st.title("💬 YouTube 댓글 분석기")
st.caption(
    "영상 링크를 입력하면 댓글 작성 추이, 댓글 반응도, 참여도, "
    "한글 워드클라우드를 분석합니다."
)

with st.expander("분석 기준 안내"):
    st.markdown(
        """
- 댓글 작성 시각은 **한국 시간(KST)**으로 변환합니다.
- 댓글 반응도는 한국어·영어 감성 표현과 이모지를 활용한 **규칙 기반 참고용 분석**입니다.
- 참여도 점수는 `좋아요 수 + 답글 수 × 2`로 계산합니다.
- 댓글 정렬 방식에 따라 가져오는 댓글 표본이 달라질 수 있습니다.
        """
    )

api_key = get_api_key()

with st.sidebar:
    st.header("분석 설정")

    requested_count = st.slider(
        "가져올 댓글 수",
        min_value=20,
        max_value=500,
        value=100,
        step=20,
    )

    order_label = st.radio(
        "댓글 정렬",
        ["최신순", "관련성순"],
    )
    order = "time" if order_label == "최신순" else "relevance"

    max_words = st.slider(
        "워드클라우드 단어 수",
        min_value=30,
        max_value=150,
        value=80,
        step=10,
    )

    background_color = st.selectbox(
        "워드클라우드 배경",
        ["white", "black"],
    )

video_input = st.text_input(
    "YouTube 영상 링크 또는 영상 ID",
    placeholder="https://www.youtube.com/watch?v=XXXXXXXXXXX",
)

if st.button(
    "댓글 분석하기",
    type="primary",
    use_container_width=True,
):
    video_id = extract_video_id(video_input)

    if not video_id:
        st.warning("올바른 YouTube 영상 링크 또는 11자리 영상 ID를 입력하세요.")
        st.stop()

    try:
        with st.spinner("영상 정보와 댓글을 불러오는 중입니다..."):
            video_info = fetch_video_info(api_key, video_id)
            comments = fetch_comments(
                api_key,
                video_id,
                requested_count,
                order,
            )

        st.session_state["video_id"] = video_id
        st.session_state["video_info"] = video_info
        st.session_state["comments"] = comments

    except HttpError as error:
        handle_http_error(error)
        st.stop()

    except ValueError as error:
        st.error(str(error))
        st.stop()

    except Exception as error:
        st.error("앱 실행 중 예상하지 못한 오류가 발생했습니다.")
        with st.expander("오류 상세 보기"):
            st.exception(error)
        st.stop()


if "video_info" in st.session_state:
    video_id = st.session_state["video_id"]
    video_info = st.session_state["video_info"]
    comments = st.session_state["comments"].copy()

    st.divider()

    video_col, info_col = st.columns([1.5, 1])

    with video_col:
        st.video(f"https://www.youtube.com/watch?v={video_id}")

    with info_col:
        st.subheader(video_info["title"])
        st.write(f"채널: **{video_info['channel']}**")
        st.write(f"게시일: **{format_kst(video_info['published_at'])} KST**")

        metric_1, metric_2, metric_3 = st.columns(3)
        metric_1.metric("조회 수", f"{video_info['view_count']:,}")
        metric_2.metric("좋아요", f"{video_info['like_count']:,}")
        metric_3.metric("전체 댓글", f"{video_info['comment_count']:,}")

    if comments.empty:
        st.info("가져올 수 있는 공개 댓글이 없습니다.")
        st.stop()

    comments["반응"] = comments["댓글"].apply(classify_sentiment)
    comments["참여도"] = comments["좋아요"] + comments["답글 수"] * 2

    positive_rate = (comments["반응"] == "긍정").mean() * 100
    neutral_rate = (comments["반응"] == "중립").mean() * 100
    negative_rate = (comments["반응"] == "부정").mean() * 100

    st.subheader("분석 요약")

    summary_1, summary_2, summary_3, summary_4 = st.columns(4)
    summary_1.metric("분석 댓글", f"{len(comments):,}개")
    summary_2.metric("긍정 비율", f"{positive_rate:.1f}%")
    summary_3.metric("중립 비율", f"{neutral_rate:.1f}%")
    summary_4.metric("부정 비율", f"{negative_rate:.1f}%")

    tab_1, tab_2, tab_3, tab_4 = st.tabs(
        ["📈 작성 추이", "😊 댓글 반응도", "☁️ 워드클라우드", "📋 댓글 데이터"]
    )

    with tab_1:
        st.markdown("#### 일별 댓글 작성 추이")

        valid_time = comments.dropna(subset=["작성 시각(KST)"]).copy()

        daily = (
            valid_time.assign(
                날짜=valid_time["작성 시각(KST)"].dt.date
            )
            .groupby("날짜")
            .size()
            .reset_index(name="댓글 수")
        )

        if daily.empty:
            st.info("댓글 작성 시각 데이터가 없습니다.")
        else:
            st.line_chart(
                daily.set_index("날짜")["댓글 수"],
                height=380,
            )

        st.markdown("#### 시간대별 댓글 작성 수")

        hourly = (
            valid_time.assign(
                시간=valid_time["작성 시각(KST)"].dt.hour
            )
            .groupby("시간")
            .size()
            .reindex(range(24), fill_value=0)
        )

        st.bar_chart(
            hourly,
            height=380,
        )

        if not hourly.empty:
            peak_hour = int(hourly.idxmax())
            peak_count = int(hourly.max())
            st.info(
                f"표본에서 댓글 작성이 가장 많았던 시간대는 "
                f"**{peak_hour}시**이며, 댓글은 **{peak_count}개**입니다."
            )

    with tab_2:
        st.markdown("#### 긍정·중립·부정 반응 분포")

        reaction_counts = (
            comments["반응"]
            .value_counts()
            .reindex(["긍정", "중립", "부정"], fill_value=0)
        )

        st.bar_chart(
            reaction_counts,
            height=380,
        )

        st.markdown("#### 반응별 참여도")

        engagement_by_reaction = (
            comments.groupby("반응")["참여도"]
            .sum()
            .reindex(["긍정", "중립", "부정"], fill_value=0)
        )

        st.bar_chart(
            engagement_by_reaction,
            height=380,
        )

        st.markdown("#### 참여도가 높은 댓글")

        top_comments = (
            comments.sort_values(
                ["참여도", "좋아요"],
                ascending=False,
            )
            .head(10)
        )

        st.dataframe(
            top_comments[
                ["반응", "댓글", "작성자", "좋아요", "답글 수", "참여도"]
            ],
            use_container_width=True,
            hide_index=True,
        )

    with tab_3:
        reaction_filter = st.multiselect(
            "워드클라우드에 포함할 반응",
            ["긍정", "중립", "부정"],
            default=["긍정", "중립", "부정"],
        )

        filtered_comments = comments[
            comments["반응"].isin(reaction_filter)
        ]

        if not FONT_PATH.exists():
            st.error(
                "나눔고딕 폰트가 없습니다.\n\n"
                "`youtube/fonts/NanumGothic.ttf` 경로에 폰트 파일을 업로드하세요."
            )
        else:
            frequencies = Counter()

            for text in filtered_comments["댓글"]:
                frequencies.update(tokenize(text))

            if not frequencies:
                st.warning("워드클라우드를 만들 수 있는 단어가 충분하지 않습니다.")
            else:
                wordcloud = WordCloud(
                    font_path=str(FONT_PATH),
                    width=1400,
                    height=750,
                    background_color=background_color,
                    max_words=max_words,
                    collocations=False,
                    prefer_horizontal=0.9,
                    random_state=42,
                ).generate_from_frequencies(frequencies)

                figure, axis = plt.subplots(figsize=(14, 7.5))
                axis.imshow(wordcloud, interpolation="bilinear")
                axis.axis("off")
                plt.tight_layout(pad=0)

                st.pyplot(figure)
                plt.close(figure)

                st.markdown("#### 상위 단어")

                top_words = pd.DataFrame(
                    frequencies.most_common(30),
                    columns=["단어", "빈도"],
                )

                st.dataframe(
                    top_words,
                    use_container_width=True,
                    hide_index=True,
                )

    with tab_4:
        display_df = comments.copy()

        display_df["작성 시각(KST)"] = display_df[
            "작성 시각(KST)"
        ].dt.strftime("%Y-%m-%d %H:%M:%S")

        reaction_filter_table = st.multiselect(
            "표시할 반응",
            ["긍정", "중립", "부정"],
            default=["긍정", "중립", "부정"],
            key="reaction_filter_table",
        )

        keyword = st.text_input(
            "댓글 검색",
            placeholder="검색할 단어를 입력하세요",
        )

        display_df = display_df[
            display_df["반응"].isin(reaction_filter_table)
        ]

        if keyword.strip():
            display_df = display_df[
                display_df["댓글"].str.contains(
                    keyword.strip(),
                    case=False,
                    na=False,
                    regex=False,
                )
            ]

        st.dataframe(
            display_df[
                [
                    "작성자",
                    "댓글",
                    "반응",
                    "좋아요",
                    "답글 수",
                    "참여도",
                    "작성 시각(KST)",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )

        csv_data = display_df.to_csv(
            index=False
        ).encode("utf-8-sig")

        st.download_button(
            "분석 결과 CSV 다운로드",
            data=csv_data,
            file_name=f"youtube_comments_{video_id}.csv",
            mime="text/csv",
            use_container_width=True,
        )

st.caption(
    "댓글 반응도 분석은 규칙 기반 참고용 결과입니다. "
    "반어법, 신조어, 문맥에 따라 실제 의미와 다르게 분류될 수 있습니다."
)
'''

requirements_txt = '''streamlit
google-api-python-client
pandas
matplotlib
wordcloud
'''

runtime_txt = '''python-3.13
'''

secrets_example = '''YOUTUBE_API_KEY = "YOUR_YOUTUBE_DATA_API_KEY"
'''

readme_md = '''# YouTube 댓글 분석기

## 폴더 구조

```text
streamlit_app/
├─ runtime.txt
└─ youtube/
   ├─ app.py
   ├─ requirements.txt
   ├─ .streamlit/
   │  └─ secrets.toml.example
   └─ fonts/
      └─ NanumGothic.ttf
