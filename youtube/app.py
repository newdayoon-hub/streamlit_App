from pathlib import Path
import zipfile, textwrap

base = Path("/mnt/data/youtube_comment_analyzer_stable")
(base / ".streamlit").mkdir(parents=True, exist_ok=True)
(base / "fonts").mkdir(parents=True, exist_ok=True)

app = r'''
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from wordcloud import WordCloud


st.set_page_config(page_title="YouTube 댓글 분석기", page_icon="💬", layout="wide")

FONT_PATH = Path("fonts/NanumGothic.ttf")

STOPWORDS = {
    "이", "그", "저", "것", "수", "등", "들", "및", "더", "좀", "정말", "진짜",
    "너무", "영상", "유튜브", "댓글", "사람", "때", "거", "게", "듯", "왜",
    "뭐", "어떻게", "여기", "저기", "그리고", "하지만", "그래서", "에서", "으로",
    "에게", "하고", "하는", "하면", "한", "하다", "합니다", "입니다", "있는",
    "없는", "있다", "없다", "같다", "같아요", "네요", "는데", "ㅋㅋ", "ㅎㅎ",
    "the", "a", "an", "and", "or", "to", "of", "in", "is", "it", "this", "that"
}

POSITIVE_WORDS = {
    "좋다", "좋아요", "좋아", "최고", "멋지다", "대박", "감동", "재밌다",
    "재미있다", "웃기다", "훌륭", "완벽", "응원", "고맙다", "감사", "사랑",
    "행복", "유익", "도움", "추천", "기대", "신기", "예쁘다", "귀엽다",
    "공감", "good", "great", "best", "love", "amazing", "awesome", "nice"
}

NEGATIVE_WORDS = {
    "싫다", "싫어", "별로", "최악", "실망", "화난다", "짜증", "노잼",
    "재미없다", "이상하다", "틀리다", "문제", "불편", "무섭다", "걱정",
    "비추천", "답답", "나쁘다", "못하다", "아쉽다", "오류", "실패",
    "bad", "worst", "hate", "boring", "wrong", "terrible"
}


def extract_video_id(value):
    value = value.strip()

    if re.fullmatch(r"[A-Za-z0-9_-]{11}", value):
        return value

    try:
        parsed = urlparse(value)
        host = parsed.netloc.lower().replace("www.", "")

        if host == "youtu.be":
            candidate = parsed.path.strip("/").split("/")[0]
        elif host in {"youtube.com", "m.youtube.com"}:
            if parsed.path == "/watch":
                candidate = parse_qs(parsed.query).get("v", [None])[0]
            elif parsed.path.startswith("/shorts/"):
                candidate = parsed.path.split("/shorts/")[1].split("/")[0]
            elif parsed.path.startswith("/embed/"):
                candidate = parsed.path.split("/embed/")[1].split("/")[0]
            else:
                candidate = None
        else:
            candidate = None

        if candidate and re.fullmatch(r"[A-Za-z0-9_-]{11}", candidate):
            return candidate
    except Exception:
        return None

    return None


def get_api_key():
    try:
        return str(st.secrets["YOUTUBE_API_KEY"]).strip()
    except Exception:
        st.error(
            'Streamlit Cloud의 Settings → Secrets에 '
            'YOUTUBE_API_KEY = "발급받은_API_KEY" 형식으로 등록하세요.'
        )
        st.stop()


@st.cache_data(ttl=1800)
def get_video_info(api_key, video_id):
    youtube = build("youtube", "v3", developerKey=api_key, cache_discovery=False)
    response = youtube.videos().list(
        part="snippet,statistics",
        id=video_id
    ).execute()

    if not response.get("items"):
        raise ValueError("영상을 찾을 수 없습니다.")

    item = response["items"][0]
    snippet = item["snippet"]
    stats = item.get("statistics", {})

    return {
        "title": snippet.get("title", ""),
        "channel": snippet.get("channelTitle", ""),
        "published_at": snippet.get("publishedAt", ""),
        "view_count": int(stats.get("viewCount", 0)),
        "like_count": int(stats.get("likeCount", 0)),
        "comment_count": int(stats.get("commentCount", 0)),
    }


@st.cache_data(ttl=1800)
def get_comments(api_key, video_id, max_comments, order):
    youtube = build("youtube", "v3", developerKey=api_key, cache_discovery=False)

    rows = []
    page_token = None

    while len(rows) < max_comments:
        response = youtube.commentThreads().list(
            part="snippet",
            videoId=video_id,
            maxResults=min(100, max_comments - len(rows)),
            order=order,
            textFormat="plainText",
            pageToken=page_token
        ).execute()

        for item in response.get("items", []):
            snippet = item["snippet"]["topLevelComment"]["snippet"]
            rows.append({
                "작성자": snippet.get("authorDisplayName", ""),
                "댓글": snippet.get("textDisplay", ""),
                "좋아요": int(snippet.get("likeCount", 0)),
                "답글 수": int(item["snippet"].get("totalReplyCount", 0)),
                "작성 시각": snippet.get("publishedAt", "")
            })

            if len(rows) >= max_comments:
                break

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    df = pd.DataFrame(rows)

    if not df.empty:
        df["작성 시각"] = pd.to_datetime(df["작성 시각"], utc=True, errors="coerce")
        df["작성 시각(KST)"] = df["작성 시각"].dt.tz_convert("Asia/Seoul")

    return df


def sentiment(text):
    value = str(text).lower()
    positive = sum(1 for word in POSITIVE_WORDS if word in value)
    negative = sum(1 for word in NEGATIVE_WORDS if word in value)

    if positive > negative:
        return "긍정"
    if negative > positive:
        return "부정"
    return "중립"


def tokenize(text):
    text = re.sub(r"https?://\S+", " ", str(text))
    tokens = re.findall(r"[가-힣]{2,}|[A-Za-z]{2,}", text.lower())
    return [token for token in tokens if token not in STOPWORDS]


st.title("💬 YouTube 댓글 분석기")
st.caption("YouTube 영상의 댓글 작성 추이, 반응도, 한글 워드클라우드를 분석합니다.")

api_key = get_api_key()

with st.sidebar:
    st.header("분석 설정")
    comment_count = st.slider("가져올 댓글 수", 20, 500, 100, 20)
    order_text = st.radio("댓글 정렬", ["최신순", "관련성순"])
    order = "time" if order_text == "최신순" else "relevance"
    max_words = st.slider("워드클라우드 단어 수", 30, 150, 80, 10)

video_url = st.text_input(
    "YouTube 영상 링크 또는 영상 ID",
    placeholder="https://www.youtube.com/watch?v=XXXXXXXXXXX"
)

if st.button("댓글 분석하기", type="primary", use_container_width=True):
    video_id = extract_video_id(video_url)

    if not video_id:
        st.warning("올바른 YouTube 링크 또는 11자리 영상 ID를 입력하세요.")
        st.stop()

    try:
        with st.spinner("영상 정보와 댓글을 불러오는 중입니다..."):
            video_info = get_video_info(api_key, video_id)
            comments = get_comments(api_key, video_id, comment_count, order)

        st.session_state["video_id"] = video_id
        st.session_state["video_info"] = video_info
        st.session_state["comments"] = comments

    except HttpError as error:
        message = str(error)

        if "commentsDisabled" in message:
            st.error("이 영상은 댓글이 비활성화되어 있습니다.")
        elif "quotaExceeded" in message:
            st.error("YouTube API 일일 할당량을 초과했습니다.")
        else:
            st.error("YouTube API 요청 중 오류가 발생했습니다.")
            st.code(message)
        st.stop()

    except Exception as error:
        st.error("앱 실행 중 오류가 발생했습니다.")
        st.exception(error)
        st.stop()


if "video_info" in st.session_state:
    video_id = st.session_state["video_id"]
    video_info = st.session_state["video_info"]
    comments = st.session_state["comments"]

    st.divider()

    left, right = st.columns([1.5, 1])

    with left:
        st.video(f"https://www.youtube.com/watch?v={video_id}")

    with right:
        st.subheader(video_info["title"])
        st.write(f"채널: **{video_info['channel']}**")

        c1, c2, c3 = st.columns(3)
        c1.metric("조회 수", f"{video_info['view_count']:,}")
        c2.metric("좋아요", f"{video_info['like_count']:,}")
        c3.metric("전체 댓글", f"{video_info['comment_count']:,}")

    if comments.empty:
        st.info("가져올 수 있는 공개 댓글이 없습니다.")
        st.stop()

    comments["반응"] = comments["댓글"].apply(sentiment)
    comments["참여도"] = comments["좋아요"] + comments["답글 수"] * 2

    positive_rate = (comments["반응"] == "긍정").mean() * 100
    negative_rate = (comments["반응"] == "부정").mean() * 100

    s1, s2, s3 = st.columns(3)
    s1.metric("분석 댓글", f"{len(comments):,}개")
    s2.metric("긍정 비율", f"{positive_rate:.1f}%")
    s3.metric("부정 비율", f"{negative_rate:.1f}%")

    tab1, tab2, tab3, tab4 = st.tabs(
        ["작성 추이", "댓글 반응도", "워드클라우드", "댓글 데이터"]
    )

    with tab1:
        daily = (
            comments.dropna(subset=["작성 시각(KST)"])
            .assign(날짜=lambda x: x["작성 시각(KST)"].dt.date)
            .groupby("날짜")
            .size()
            .reset_index(name="댓글 수")
        )

        if daily.empty:
            st.info("작성 시각 데이터가 없습니다.")
        else:
            st.line_chart(daily.set_index("날짜")["댓글 수"])

        hourly = (
            comments.dropna(subset=["작성 시각(KST)"])
            .assign(시간=lambda x: x["작성 시각(KST)"].dt.hour)
            .groupby("시간")
            .size()
            .reindex(range(24), fill_value=0)
        )
        st.markdown("#### 시간대별 댓글 작성 수")
        st.bar_chart(hourly)

    with tab2:
        reaction_counts = (
            comments["반응"]
            .value_counts()
            .reindex(["긍정", "중립", "부정"], fill_value=0)
        )

        st.bar_chart(reaction_counts)

        st.markdown("#### 참여도가 높은 댓글")
        top_comments = comments.sort_values(
            ["참여도", "좋아요"],
            ascending=False
        ).head(10)

        st.dataframe(
            top_comments[["반응", "댓글", "작성자", "좋아요", "답글 수", "참여도"]],
            use_container_width=True,
            hide_index=True
        )

    with tab3:
        if not FONT_PATH.exists():
            st.error(
                "fonts/NanumGothic.ttf 파일이 없습니다. "
                "GitHub 저장소의 fonts 폴더에 나눔고딕 TTF 파일을 업로드하세요."
            )
        else:
            frequencies = Counter()

            for text in comments["댓글"]:
                frequencies.update(tokenize(text))

            if not frequencies:
                st.warning("워드클라우드를 만들 단어가 없습니다.")
            else:
                wc = WordCloud(
                    font_path=str(FONT_PATH),
                    width=1200,
                    height=650,
                    background_color="white",
                    max_words=max_words,
                    collocations=False,
                    random_state=42
                ).generate_from_frequencies(frequencies)

                fig, ax = plt.subplots(figsize=(12, 6.5))
                ax.imshow(wc, interpolation="bilinear")
                ax.axis("off")
                st.pyplot(fig)
                plt.close(fig)

                top_words = pd.DataFrame(
                    frequencies.most_common(20),
                    columns=["단어", "빈도"]
                )
                st.dataframe(top_words, use_container_width=True, hide_index=True)

    with tab4:
        display_df = comments.copy()
        display_df["작성 시각(KST)"] = display_df["작성 시각(KST)"].dt.strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        st.dataframe(display_df, use_container_width=True, hide_index=True)

        csv_data = display_df.to_csv(index=False).encode("utf-8-sig")

        st.download_button(
            "CSV 다운로드",
            data=csv_data,
            file_name=f"youtube_comments_{video_id}.csv",
            mime="text/csv",
            use_container_width=True
        )

st.caption("감성 분석은 간단한 규칙 기반 방식이므로 참고용으로 활용하세요.")
'''

requirements = '''streamlit==1.40.2
google-api-python-client==2.154.0
pandas==2.2.3
matplotlib==3.9.2
wordcloud==1.9.4
'''

readme = '''# YouTube 댓글 분석기 안정 버전

## 필수 파일 구조

```text
youtube/
├─ app.py
├─ requirements.txt
└─ fonts/
   └─ NanumGothic.ttf
