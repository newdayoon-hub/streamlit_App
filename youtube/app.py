import re
from collections import Counter
from datetime import timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import altair as alt
import isodate
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

FONT_PATH = Path("fonts/NanumGothic.ttf")

KOREAN_STOPWORDS = {
    "이", "그", "저", "것", "수", "등", "들", "및", "더", "좀", "정말", "진짜",
    "너무", "영상", "유튜브", "댓글", "사람", "때", "거", "게", "듯", "왜",
    "뭐", "어떻게", "여기", "저기", "그리고", "하지만", "그래서", "에서", "으로",
    "에게", "하고", "하는", "하면", "한", "하다", "합니다", "입니다", "있는",
    "없는", "있다", "없다", "같다", "같아요", "입니다", "네요", "는데", "ㅋㅋ",
    "ㅎㅎ", "ㅋㅋㅋ", "ㅎㅎㅎ", "the", "a", "an", "and", "or", "to", "of",
    "in", "is", "it", "this", "that", "for", "on", "with", "you", "i"
}

POSITIVE_WORDS = {
    "좋다", "좋아요", "좋아", "최고", "멋지다", "멋져", "대박", "감동", "재밌다",
    "재미있다", "웃기다", "훌륭", "완벽", "응원", "고맙다", "감사", "사랑", "행복",
    "유익", "도움", "추천", "기대", "신기", "예쁘다", "귀엽다", "존경", "성공",
    "잘한다", "잘했", "맞다", "공감", "good", "great", "best", "love", "amazing",
    "awesome", "nice", "fun", "helpful", "thanks", "thank"
}

NEGATIVE_WORDS = {
    "싫다", "싫어", "별로", "최악", "실망", "화난다", "짜증", "노잼", "재미없다",
    "이상하다", "틀리다", "문제", "불편", "무섭다", "걱정", "비추천", "답답",
    "심하다", "나쁘다", "못하다", "아쉽다", "아쉬워", "거짓", "오류", "실패",
    "bad", "worst", "hate", "boring", "wrong", "terrible", "disappointing"
}

POSITIVE_EMOJIS = {"😀", "😃", "😄", "😁", "😊", "😍", "🥰", "👍", "❤️", "❤", "🔥", "👏", "🎉", "✨", "💯"}
NEGATIVE_EMOJIS = {"😡", "😠", "🤬", "😢", "😭", "👎", "💔", "😞", "😒", "😤"}

NEGATIONS = {"안", "않", "못", "아니", "별로"}


def extract_video_id(url_or_id: str) -> str | None:
    """일반 URL, 단축 URL, Shorts URL, embed URL 또는 11자리 ID에서 영상 ID를 추출한다."""
    value = url_or_id.strip()

    if re.fullmatch(r"[A-Za-z0-9_-]{11}", value):
        return value

    try:
        parsed = urlparse(value)
        host = parsed.netloc.lower().replace("www.", "")

        if host == "youtu.be":
            candidate = parsed.path.strip("/").split("/")[0]
            return candidate if re.fullmatch(r"[A-Za-z0-9_-]{11}", candidate) else None

        if host in {"youtube.com", "m.youtube.com", "music.youtube.com"}:
            if parsed.path == "/watch":
                candidate = parse_qs(parsed.query).get("v", [None])[0]
            elif parsed.path.startswith("/shorts/"):
                candidate = parsed.path.split("/shorts/")[1].split("/")[0]
            elif parsed.path.startswith("/embed/"):
                candidate = parsed.path.split("/embed/")[1].split("/")[0]
            elif parsed.path.startswith("/live/"):
                candidate = parsed.path.split("/live/")[1].split("/")[0]
            else:
                candidate = None

            return candidate if candidate and re.fullmatch(r"[A-Za-z0-9_-]{11}", candidate) else None
    except ValueError:
        return None

    return None


def get_api_key() -> str:
    try:
        key = st.secrets["YOUTUBE_API_KEY"]
    except (KeyError, FileNotFoundError):
        st.error(
            "YouTube API 키가 설정되지 않았습니다. "
            "Streamlit Cloud의 App settings → Secrets에 "
            '`YOUTUBE_API_KEY = "발급받은_키"` 형식으로 등록하세요.'
        )
        st.stop()

    if not str(key).strip():
        st.error("Secrets의 YOUTUBE_API_KEY 값이 비어 있습니다.")
        st.stop()

    return str(key).strip()


def youtube_client(api_key: str):
    return build("youtube", "v3", developerKey=api_key, cache_discovery=False)


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_video_info(api_key: str, video_id: str) -> dict:
    youtube = youtube_client(api_key)
    response = (
        youtube.videos()
        .list(part="snippet,statistics,contentDetails", id=video_id)
        .execute()
    )

    if not response.get("items"):
        raise ValueError("영상을 찾을 수 없습니다. 비공개·삭제 영상인지 확인하세요.")

    item = response["items"][0]
    snippet = item["snippet"]
    statistics = item.get("statistics", {})
    content = item.get("contentDetails", {})

    duration_seconds = int(isodate.parse_duration(content.get("duration", "PT0S")).total_seconds())

    return {
        "video_id": video_id,
        "title": snippet.get("title", ""),
        "channel": snippet.get("channelTitle", ""),
        "published_at": snippet.get("publishedAt", ""),
        "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
        "view_count": int(statistics.get("viewCount", 0)),
        "like_count": int(statistics.get("likeCount", 0)),
        "comment_count": int(statistics.get("commentCount", 0)),
        "duration_seconds": duration_seconds,
    }


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_comments(
    api_key: str,
    video_id: str,
    requested_count: int,
    order: str,
    include_replies: bool,
) -> pd.DataFrame:
    youtube = youtube_client(api_key)
    rows: list[dict] = []
    page_token = None

    while len(rows) < requested_count:
        page_size = min(100, requested_count - len(rows))

        request = youtube.commentThreads().list(
            part="snippet,replies" if include_replies else "snippet",
            videoId=video_id,
            maxResults=page_size,
            order=order,
            textFormat="plainText",
            pageToken=page_token,
        )
        response = request.execute()

        for item in response.get("items", []):
            thread = item["snippet"]
            top = thread["topLevelComment"]
            snippet = top["snippet"]

            rows.append(
                {
                    "comment_id": top["id"],
                    "comment_type": "최상위 댓글",
                    "author": snippet.get("authorDisplayName", "알 수 없음"),
                    "text": snippet.get("textDisplay", ""),
                    "like_count": int(snippet.get("likeCount", 0)),
                    "reply_count": int(thread.get("totalReplyCount", 0)),
                    "published_at": snippet.get("publishedAt"),
                    "updated_at": snippet.get("updatedAt"),
                }
            )

            if include_replies and len(rows) < requested_count:
                for reply in item.get("replies", {}).get("comments", []):
                    reply_snippet = reply["snippet"]
                    rows.append(
                        {
                            "comment_id": reply["id"],
                            "comment_type": "답글",
                            "author": reply_snippet.get("authorDisplayName", "알 수 없음"),
                            "text": reply_snippet.get("textDisplay", ""),
                            "like_count": int(reply_snippet.get("likeCount", 0)),
                            "reply_count": 0,
                            "published_at": reply_snippet.get("publishedAt"),
                            "updated_at": reply_snippet.get("updatedAt"),
                        }
                    )
                    if len(rows) >= requested_count:
                        break

            if len(rows) >= requested_count:
                break

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    df = pd.DataFrame(rows)

    if df.empty:
        return df

    df["published_at"] = pd.to_datetime(df["published_at"], utc=True, errors="coerce")
    df["updated_at"] = pd.to_datetime(df["updated_at"], utc=True, errors="coerce")
    df["published_kst"] = df["published_at"].dt.tz_convert("Asia/Seoul")
    return df


def tokenize(text: str) -> list[str]:
    text = re.sub(r"https?://\S+|www\.\S+", " ", str(text))
    text = re.sub(r"[@#][A-Za-z0-9_가-힣]+", " ", text)
    tokens = re.findall(r"[가-힣]{2,}|[A-Za-z]{2,}", text.lower())
    return [
        token for token in tokens
        if token not in KOREAN_STOPWORDS and not token.isdigit()
    ]


def sentiment_score(text: str) -> int:
    normalized = str(text).lower()
    tokens = re.findall(r"[가-힣]+|[a-z]+", normalized)
    score = 0

    for i, token in enumerate(tokens):
        token_score = 0

        if token in POSITIVE_WORDS or any(word in token for word in POSITIVE_WORDS if len(word) >= 2):
            token_score += 1
        if token in NEGATIVE_WORDS or any(word in token for word in NEGATIVE_WORDS if len(word) >= 2):
            token_score -= 1

        previous = tokens[max(0, i - 2):i]
        if token_score != 0 and any(neg in previous for neg in NEGATIONS):
            token_score *= -1

        score += token_score

    score += sum(normalized.count(emoji) for emoji in POSITIVE_EMOJIS)
    score -= sum(normalized.count(emoji) for emoji in NEGATIVE_EMOJIS)

    if "ㅋㅋ" in normalized or "ㅎㅎ" in normalized:
        score += 1

    return score


def sentiment_label(score: int) -> str:
    if score >= 1:
        return "긍정"
    if score <= -1:
        return "부정"
    return "중립"


def prepare_analysis(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    result["sentiment_score"] = result["text"].apply(sentiment_score)
    result["sentiment"] = result["sentiment_score"].apply(sentiment_label)
    result["engagement_score"] = (
        result["like_count"] + result["reply_count"] * 2
    )
    result["text_length"] = result["text"].str.len()
    return result


def format_number(value: int) -> str:
    return f"{int(value):,}"


def duration_text(total_seconds: int) -> str:
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"


def build_time_series(df: pd.DataFrame, granularity: str) -> pd.DataFrame:
    local_time = df["published_kst"]

    if granularity == "시간별":
        grouped = (
            df.assign(period=local_time.dt.floor("h"))
            .groupby("period")
            .size()
            .reset_index(name="댓글 수")
        )
    elif granularity == "요일별":
        day_order = ["월", "화", "수", "목", "금", "토", "일"]
        day_names = local_time.dt.dayofweek.map(dict(enumerate(day_order)))
        grouped = (
            df.assign(period=day_names)
            .groupby("period")
            .size()
            .reindex(day_order, fill_value=0)
            .rename_axis("period")
            .reset_index(name="댓글 수")
        )
    elif granularity == "시간대별(0~23시)":
        grouped = (
            df.assign(period=local_time.dt.hour)
            .groupby("period")
            .size()
            .reindex(range(24), fill_value=0)
            .rename_axis("period")
            .reset_index(name="댓글 수")
        )
    else:
        grouped = (
            df.assign(period=local_time.dt.date)
            .groupby("period")
            .size()
            .reset_index(name="댓글 수")
        )

    return grouped


def make_wordcloud(texts: list[str], max_words: int, background_color: str):
    if not FONT_PATH.exists():
        raise FileNotFoundError(
            f"{FONT_PATH} 파일이 없습니다. GitHub 저장소의 fonts 폴더에 "
            "NanumGothic.ttf를 업로드하세요."
        )

    frequencies = Counter()
    for text in texts:
        frequencies.update(tokenize(text))

    if not frequencies:
        return None, frequencies

    wc = WordCloud(
        font_path=str(FONT_PATH),
        width=1400,
        height=750,
        background_color=background_color,
        max_words=max_words,
        collocations=False,
        prefer_horizontal=0.9,
        random_state=42,
    ).generate_from_frequencies(frequencies)

    return wc, frequencies


def show_api_error(error: HttpError):
    status = getattr(error.resp, "status", None)
    message = str(error)

    if status == 403 and "commentsDisabled" in message:
        st.error("이 영상은 댓글이 비활성화되어 있어 분석할 수 없습니다.")
    elif status == 403 and ("quotaExceeded" in message or "dailyLimitExceeded" in message):
        st.error("YouTube Data API 일일 할당량을 초과했습니다.")
    elif status == 400:
        st.error("요청 형식이 올바르지 않습니다. 영상 링크를 다시 확인하세요.")
    else:
        st.error(f"YouTube API 요청 중 오류가 발생했습니다: {error}")


st.title("💬 YouTube 댓글 분석기")
st.caption("영상 링크를 입력하면 댓글 작성 추이, 감성 반응도, 참여도, 한글 워드클라우드를 분석합니다.")

with st.expander("분석 기준 안내"):
    st.markdown(
        """
        - **댓글 작성 추이**: 선택한 댓글 표본의 한국 시간(KST) 기준 작성 시점을 집계합니다.
        - **댓글 반응도**: 한국어·영어 긍정/부정 표현과 이모지를 이용한 가벼운 규칙 기반 분석입니다.
        - **참여도 점수**: `좋아요 수 + 답글 수 × 2`로 계산한 비교용 지표입니다.
        - API에서 가져오는 댓글은 선택한 정렬 방식에 따라 달라지므로 전체 댓글의 완전한 여론조사로 해석하면 안 됩니다.
        """
    )

api_key = get_api_key()

with st.sidebar:
    st.header("분석 설정")
    requested_count = st.slider(
        "가져올 댓글 수",
        min_value=20,
        max_value=1000,
        value=200,
        step=20,
        help="답글 포함 시 최상위 댓글과 답글을 합친 최대 개수입니다.",
    )
    order_label = st.radio(
        "댓글 정렬",
        ["최신순", "관련성순"],
        horizontal=True,
    )
    order = "time" if order_label == "최신순" else "relevance"
    include_replies = st.checkbox(
        "API 응답에 포함된 답글도 분석",
        value=False,
        help="댓글 스레드 응답에 포함된 일부 답글을 함께 분석합니다.",
    )
    granularity = st.selectbox(
        "작성 추이 집계 단위",
        ["일별", "시간별", "요일별", "시간대별(0~23시)"],
    )
    max_words = st.slider("워드클라우드 단어 수", 30, 200, 100, 10)
    wc_background = st.selectbox("워드클라우드 배경", ["white", "black"])

video_input = st.text_input(
    "YouTube 영상 링크 또는 영상 ID",
    placeholder="https://www.youtube.com/watch?v=XXXXXXXXXXX",
)

analyze = st.button("댓글 분석하기", type="primary", use_container_width=True)

if analyze:
    video_id = extract_video_id(video_input)

    if not video_id:
        st.warning("올바른 YouTube 영상 링크 또는 11자리 영상 ID를 입력하세요.")
        st.stop()

    try:
        with st.spinner("영상 정보와 댓글을 가져오는 중입니다..."):
            video_info = fetch_video_info(api_key, video_id)
            comments = fetch_comments(
                api_key,
                video_id,
                requested_count,
                order,
                include_replies,
            )
    except HttpError as error:
        show_api_error(error)
        st.stop()
    except ValueError as error:
        st.error(str(error))
        st.stop()
    except Exception as error:
        st.exception(error)
        st.stop()

    st.session_state["video_info"] = video_info
    st.session_state["comments"] = comments
    st.session_state["video_url"] = f"https://www.youtube.com/watch?v={video_id}"

if "video_info" in st.session_state and "comments" in st.session_state:
    video_info = st.session_state["video_info"]
    comments = st.session_state["comments"]
    video_url = st.session_state["video_url"]

    st.divider()

    left, right = st.columns([1.45, 1])

    with left:
        st.video(video_url)

    with right:
        st.subheader(video_info["title"])
        st.write(f"채널: **{video_info['channel']}**")
        published = pd.to_datetime(video_info["published_at"], utc=True, errors="coerce")
        if pd.notna(published):
            st.write(f"게시일: **{published.tz_convert('Asia/Seoul').strftime('%Y-%m-%d %H:%M')} KST**")
        st.write(f"영상 길이: **{duration_text(video_info['duration_seconds'])}**")

        m1, m2, m3 = st.columns(3)
        m1.metric("조회 수", format_number(video_info["view_count"]))
        m2.metric("좋아요 수", format_number(video_info["like_count"]))
        m3.metric("전체 댓글 수", format_number(video_info["comment_count"]))

    if comments.empty:
        st.info("가져올 수 있는 공개 댓글이 없습니다.")
        st.stop()

    df = prepare_analysis(comments)

    st.subheader("분석 요약")
    positive_rate = (df["sentiment"] == "긍정").mean() * 100
    negative_rate = (df["sentiment"] == "부정").mean() * 100
    average_likes = df["like_count"].mean()
    total_engagement = df["engagement_score"].sum()

    a, b, c, d = st.columns(4)
    a.metric("분석 댓글", f"{len(df):,}개")
    b.metric("긍정 비율", f"{positive_rate:.1f}%")
    c.metric("부정 비율", f"{negative_rate:.1f}%")
    d.metric("평균 좋아요", f"{average_likes:.1f}")

    tab1, tab2, tab3, tab4 = st.tabs(
        ["📈 작성 추이", "😊 댓글 반응도", "☁️ 워드클라우드", "📋 댓글 데이터"]
    )

    with tab1:
        time_df = build_time_series(df, granularity)

        # Altair 버전 차이로 인한 type 인자 오류를 피하기 위해
        # 시간축과 범주축을 명시적인 shorthand로 분리한다.
        if granularity in {"일별", "시간별"}:
            time_df["period"] = pd.to_datetime(time_df["period"], errors="coerce")
            x_encoding = alt.X("period:T", title=granularity.replace("별", ""))
            tooltip_encoding = [alt.Tooltip("period:T", title="구간"), alt.Tooltip("댓글 수:Q")]
        else:
            time_df["period"] = time_df["period"].astype(str)
            x_encoding = alt.X("period:N", title=granularity.replace("별", ""), sort=None)
            tooltip_encoding = [alt.Tooltip("period:N", title="구간"), alt.Tooltip("댓글 수:Q")]

        time_chart = (
            alt.Chart(time_df)
            .mark_line(point=True)
            .encode(
                x=x_encoding,
                y=alt.Y("댓글 수:Q", title="댓글 수"),
                tooltip=tooltip_encoding,
            )
            .properties(height=430)
            .interactive()
        )
        st.altair_chart(time_chart, use_container_width=True)

        if not time_df.empty:
            peak_row = time_df.loc[time_df["댓글 수"].idxmax()]
            st.info(f"표본에서 댓글 작성이 가장 많았던 구간: **{peak_row['period']}** · **{int(peak_row['댓글 수'])}개**")

    with tab2:
        sentiment_counts = (
            df["sentiment"]
            .value_counts()
            .reindex(["긍정", "중립", "부정"], fill_value=0)
            .rename_axis("반응")
            .reset_index(name="댓글 수")
        )

        c1, c2 = st.columns(2)

        with c1:
            sentiment_chart = (
                alt.Chart(sentiment_counts)
                .mark_arc(innerRadius=70)
                .encode(
                    theta=alt.Theta("댓글 수:Q"),
                    color=alt.Color(
                        "반응:N",
                        scale=alt.Scale(
                            domain=["긍정", "중립", "부정"],
                            range=["#2ca02c", "#9e9e9e", "#d62728"],
                        ),
                    ),
                    tooltip=["반응", "댓글 수"],
                )
                .properties(height=380, title="감성 반응 분포")
            )
            st.altair_chart(sentiment_chart, use_container_width=True)

        with c2:
            engagement = (
                df.groupby("sentiment", as_index=False)
                .agg(
                    댓글_수=("text", "size"),
                    좋아요_합계=("like_count", "sum"),
                    참여도_합계=("engagement_score", "sum"),
                )
            )
            engagement_chart = (
                alt.Chart(engagement)
                .mark_bar()
                .encode(
                    x=alt.X("sentiment:N", title="반응"),
                    y=alt.Y("참여도_합계:Q", title="참여도 점수 합계"),
                    color=alt.Color(
                        "sentiment:N",
                        legend=None,
                        scale=alt.Scale(
                            domain=["긍정", "중립", "부정"],
                            range=["#2ca02c", "#9e9e9e", "#d62728"],
                        ),
                    ),
                    tooltip=["sentiment", "댓글_수", "좋아요_합계", "참여도_합계"],
                )
                .properties(height=380, title="반응별 참여도")
            )
            st.altair_chart(engagement_chart, use_container_width=True)

        st.markdown("#### 참여도가 높은 댓글")
        top_comments = (
            df.sort_values(["engagement_score", "like_count"], ascending=False)
            .head(10)
            [["sentiment", "text", "author", "like_count", "reply_count", "engagement_score"]]
            .rename(
                columns={
                    "sentiment": "반응",
                    "text": "댓글",
                    "author": "작성자",
                    "like_count": "좋아요",
                    "reply_count": "답글",
                    "engagement_score": "참여도 점수",
                }
            )
        )
        st.dataframe(top_comments, use_container_width=True, hide_index=True)

    with tab3:
        sentiment_filter = st.multiselect(
            "워드클라우드에 포함할 반응",
            ["긍정", "중립", "부정"],
            default=["긍정", "중립", "부정"],
        )

        filtered = df[df["sentiment"].isin(sentiment_filter)]

        try:
            wc, frequencies = make_wordcloud(
                filtered["text"].tolist(),
                max_words=max_words,
                background_color=wc_background,
            )
        except FileNotFoundError as error:
            st.error(str(error))
            wc = None
            frequencies = Counter()

        if wc is None:
            st.warning("워드클라우드를 만들 수 있는 단어가 충분하지 않습니다.")
        else:
            figure, axis = plt.subplots(figsize=(14, 7.5))
            axis.imshow(wc, interpolation="bilinear")
            axis.axis("off")
            plt.tight_layout(pad=0)
            st.pyplot(figure)
            plt.close(figure)

            top_words = pd.DataFrame(
                frequencies.most_common(30),
                columns=["단어", "빈도"],
            )
            word_chart = (
                alt.Chart(top_words)
                .mark_bar()
                .encode(
                    x=alt.X("빈도:Q", title="등장 횟수"),
                    y=alt.Y("단어:N", sort="-x", title="단어"),
                    tooltip=["단어", "빈도"],
                )
                .properties(height=600, title="상위 단어 30개")
            )
            st.altair_chart(word_chart, use_container_width=True)

    with tab4:
        display_df = (
            df.assign(
                작성시각_KST=df["published_kst"].dt.strftime("%Y-%m-%d %H:%M:%S")
            )
            [[
                "comment_type",
                "author",
                "text",
                "sentiment",
                "sentiment_score",
                "like_count",
                "reply_count",
                "engagement_score",
                "작성시각_KST",
            ]]
            .rename(
                columns={
                    "comment_type": "유형",
                    "author": "작성자",
                    "text": "댓글",
                    "sentiment": "반응",
                    "sentiment_score": "감성 점수",
                    "like_count": "좋아요",
                    "reply_count": "답글",
                    "engagement_score": "참여도 점수",
                }
            )
        )

        reaction_filter = st.multiselect(
            "표시할 반응",
            ["긍정", "중립", "부정"],
            default=["긍정", "중립", "부정"],
            key="table_reaction_filter",
        )
        keyword = st.text_input("댓글 검색", placeholder="검색할 단어를 입력하세요")

        filtered_table = display_df[display_df["반응"].isin(reaction_filter)]
        if keyword.strip():
            filtered_table = filtered_table[
                filtered_table["댓글"].str.contains(
                    keyword.strip(),
                    case=False,
                    na=False,
                    regex=False,
                )
            ]

        st.dataframe(filtered_table, use_container_width=True, hide_index=True)

        csv_data = filtered_table.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "분석 결과 CSV 다운로드",
            data=csv_data,
            file_name=f"youtube_comments_{video_info['video_id']}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    st.caption(
        "감성 분석은 규칙 기반의 참고용 결과입니다. 반어법, 신조어, 문맥에 따라 실제 의미와 다르게 분류될 수 있습니다."
    )
