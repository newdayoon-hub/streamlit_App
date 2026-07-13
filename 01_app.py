import streamlit as st
from st_clickable_images import clickable_images

st.set_page_config(
    page_title="Palette Voyage",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# -----------------------------
# 여행지 데이터
# main_color 값: Blue / Green / Pink / Orange / White / Purple
# -----------------------------
DESTINATIONS = [
    {
        "name": "산토리니",
        "country": "그리스",
        "main_color": "Blue",
        "color_ko": "파랑",
        "emoji": "💙",
        "image": "https://images.unsplash.com/photo-1570077188670-e3a8d69ac5ff?auto=format&fit=crop&w=1200&q=85",
        "short": "에게해의 푸른 바다와 하얀 마을",
        "description": "산토리니는 새하얀 집과 파란 지붕, 깊은 에게해가 어우러지는 그리스의 섬이다. 특히 이아 마을의 노을과 절벽을 따라 이어지는 골목 풍경으로 유명하다.",
        "best_season": "4월~6월, 9월~10월",
        "mood": "맑고 낭만적인",
        "point": "이아 마을, 칼데라 전망대, 피라",
    },
    {
        "name": "몰디브",
        "country": "몰디브",
        "main_color": "Blue",
        "color_ko": "파랑",
        "emoji": "💙",
        "image": "https://images.unsplash.com/photo-1514282401047-d79a71a590e8?auto=format&fit=crop&w=1200&q=85",
        "short": "투명한 바다 위의 작은 섬",
        "description": "몰디브는 인도양에 흩어진 산호섬으로, 투명한 청록빛 바다와 수상 가옥이 대표적인 풍경이다. 조용한 휴식과 스노클링을 즐기기 좋은 여행지다.",
        "best_season": "11월~4월",
        "mood": "고요하고 청량한",
        "point": "라군, 산호초, 수상 빌라",
    },
    {
        "name": "스위스 라우터브루넨",
        "country": "스위스",
        "main_color": "Green",
        "color_ko": "초록",
        "emoji": "💚",
        "image": "https://images.unsplash.com/photo-1527668752968-14dc70a27c95?auto=format&fit=crop&w=1200&q=85",
        "short": "폭포와 초원이 이어지는 알프스 계곡",
        "description": "라우터브루넨은 높은 절벽과 폭포, 초록빛 들판이 펼쳐지는 스위스의 계곡 마을이다. 기차를 타고 융프라우 지역의 여러 산악 마을로 이동하기 좋다.",
        "best_season": "5월~9월",
        "mood": "평화롭고 싱그러운",
        "point": "슈타우프바흐 폭포, 뮈렌, 벵엔",
    },
    {
        "name": "발리 우붓",
        "country": "인도네시아",
        "main_color": "Green",
        "color_ko": "초록",
        "emoji": "💚",
        "image": "https://images.unsplash.com/photo-1533669955142-6a73332af4db?auto=format&fit=crop&w=1200&q=85",
        "short": "열대 숲과 계단식 논의 풍경",
        "description": "우붓은 발리 내륙의 문화와 자연이 만나는 지역이다. 계단식 논, 열대 숲, 사원과 예술 마을이 어우러져 차분하게 머물기 좋다.",
        "best_season": "4월~10월",
        "mood": "자연스럽고 느긋한",
        "point": "뜨갈랄랑 논, 우붓 왕궁, 몽키 포레스트",
    },
    {
        "name": "가와즈",
        "country": "일본",
        "main_color": "Pink",
        "color_ko": "분홍",
        "emoji": "🩷",
        "image": "https://images.unsplash.com/photo-1522383225653-ed111181a951?auto=format&fit=crop&w=1200&q=85",
        "short": "강변을 물들이는 이른 벚꽃",
        "description": "시즈오카현 가와즈는 일반 벚꽃보다 일찍 피는 가와즈자쿠라로 알려져 있다. 강변 산책로를 따라 진한 분홍빛 꽃길이 이어진다.",
        "best_season": "2월 중순~3월 초",
        "mood": "포근하고 설레는",
        "point": "가와즈강 벚꽃길, 나나다루 폭포",
    },
    {
        "name": "프로방스",
        "country": "프랑스",
        "main_color": "Purple",
        "color_ko": "보라",
        "emoji": "💜",
        "image": "https://images.unsplash.com/photo-1499002238440-d264edd596ec?auto=format&fit=crop&w=1200&q=85",
        "short": "끝없이 펼쳐지는 라벤더 들판",
        "description": "프랑스 남부 프로방스는 여름이면 보랏빛 라벤더 밭으로 물든다. 작은 마을과 석조 건물, 따뜻한 햇빛이 어우러져 그림 같은 풍경을 만든다.",
        "best_season": "6월 말~7월",
        "mood": "향기롭고 몽환적인",
        "point": "발랑솔 고원, 세낭크 수도원",
    },
    {
        "name": "사하라 사막",
        "country": "모로코",
        "main_color": "Orange",
        "color_ko": "주황",
        "emoji": "🧡",
        "image": "https://images.unsplash.com/photo-1509316785289-025f5b846b35?auto=format&fit=crop&w=1200&q=85",
        "short": "햇빛에 붉게 빛나는 모래 언덕",
        "description": "사하라 사막에서는 바람이 만든 모래 능선과 넓은 하늘을 볼 수 있다. 특히 해 질 무렵에는 모래가 금빛과 주황빛으로 변한다.",
        "best_season": "10월~4월",
        "mood": "광활하고 신비로운",
        "point": "메르주가, 에르그 셰비 모래언덕",
    },
    {
        "name": "그랜드 캐니언",
        "country": "미국",
        "main_color": "Orange",
        "color_ko": "주황",
        "emoji": "🧡",
        "image": "https://images.unsplash.com/photo-1474044159687-1ee9f3a51722?auto=format&fit=crop&w=1200&q=85",
        "short": "붉은 지층이 만든 거대한 협곡",
        "description": "그랜드 캐니언은 콜로라도강의 침식으로 형성된 거대한 협곡이다. 시간대에 따라 암벽의 색이 달라지며, 전망대마다 서로 다른 규모와 깊이를 보여준다.",
        "best_season": "3월~5월, 9월~11월",
        "mood": "웅장하고 강렬한",
        "point": "사우스 림, 매더 포인트, 데저트 뷰",
    },
    {
        "name": "카파도키아",
        "country": "튀르키예",
        "main_color": "Orange",
        "color_ko": "주황",
        "emoji": "🧡",
        "image": "https://images.unsplash.com/photo-1528181304800-259b08848526?auto=format&fit=crop&w=1200&q=85",
        "short": "새벽 하늘을 채우는 열기구",
        "description": "카파도키아는 독특한 화산암 지형과 동굴 마을로 유명하다. 해 뜨기 전 수많은 열기구가 떠오르는 장면이 대표적인 풍경이다.",
        "best_season": "4월~6월, 9월~10월",
        "mood": "따뜻하고 비현실적인",
        "point": "괴레메, 러브 밸리, 우치히사르",
    },
    {
        "name": "아이슬란드",
        "country": "아이슬란드",
        "main_color": "White",
        "color_ko": "하양",
        "emoji": "🤍",
        "image": "https://images.unsplash.com/photo-1504829857797-ddff29c27927?auto=format&fit=crop&w=1200&q=85",
        "short": "빙하와 설원이 만든 차가운 풍경",
        "description": "아이슬란드는 빙하, 폭포, 화산 지형이 가까운 거리 안에 공존하는 섬나라다. 겨울의 설원과 여름의 긴 낮이 전혀 다른 분위기를 만든다.",
        "best_season": "6월~8월 또는 10월~3월",
        "mood": "차분하고 초현실적인",
        "point": "요쿨살론, 스코가포스, 골든 서클",
    },
    {
        "name": "돌로미티",
        "country": "이탈리아",
        "main_color": "White",
        "color_ko": "하양",
        "emoji": "🤍",
        "image": "https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?auto=format&fit=crop&w=1200&q=85",
        "short": "구름과 설산이 맞닿은 산악 풍경",
        "description": "돌로미티는 날카로운 봉우리와 고산 초원으로 유명한 이탈리아 북부의 산악 지대다. 계절과 빛에 따라 회백색 암벽이 분홍빛으로 물들기도 한다.",
        "best_season": "6월~9월, 12월~3월",
        "mood": "깨끗하고 장엄한",
        "point": "세체다, 트레 치메, 브라이에스 호수",
    },
    {
        "name": "장예 단샤",
        "country": "중국",
        "main_color": "Purple",
        "color_ko": "보라",
        "emoji": "💜",
        "image": "https://images.unsplash.com/photo-1500534314209-a25ddb2bd429?auto=format&fit=crop&w=1200&q=85",
        "short": "여러 색의 지층이 겹친 무지개 산",
        "description": "장예 단샤는 붉은색, 주황색, 보라색 계열의 지층이 물결처럼 이어지는 지형으로 알려져 있다. 햇빛과 날씨에 따라 산의 색감이 크게 달라진다.",
        "best_season": "5월~10월",
        "mood": "독특하고 예술적인",
        "point": "단샤 국가지질공원 전망대",
    },
]

COLOR_OPTIONS = {
    "전체": "All",
    "💙 파랑": "Blue",
    "💚 초록": "Green",
    "🩷 분홍": "Pink",
    "🧡 주황": "Orange",
    "🤍 하양": "White",
    "💜 보라": "Purple",
}

# -----------------------------
# 감성 디자인 CSS
# -----------------------------
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Gowun+Dodum&family=Playfair+Display:wght@600;700&display=swap');

    :root {
        --cream: #f8f4ed;
        --ink: #2f302d;
        --muted: #74756f;
        --line: rgba(60, 60, 50, 0.12);
    }

    .stApp {
        background:
            radial-gradient(circle at 8% 5%, rgba(222, 232, 218, 0.65), transparent 25%),
            radial-gradient(circle at 92% 8%, rgba(238, 217, 205, 0.55), transparent 24%),
            linear-gradient(180deg, #fbf8f2 0%, #f4efe7 100%);
        color: var(--ink);
    }

    html, body, [class*="css"] {
        font-family: "Gowun Dodum", sans-serif;
    }

    .block-container {
        max-width: 1240px;
        padding-top: 2.5rem;
        padding-bottom: 4rem;
    }

    .hero {
        text-align: center;
        padding: 3.2rem 1rem 2rem;
    }

    .eyebrow {
        color: #8b7769;
        font-size: 0.78rem;
        letter-spacing: 0.2em;
        text-transform: uppercase;
        margin-bottom: 0.7rem;
    }

    .hero h1 {
        font-family: "Playfair Display", serif;
        font-size: clamp(3rem, 7vw, 5.6rem);
        line-height: 0.95;
        color: #343530;
        margin: 0;
        letter-spacing: -0.04em;
    }

    .hero p {
        color: var(--muted);
        font-size: 1.06rem;
        margin: 1.3rem auto 0;
        max-width: 650px;
        line-height: 1.8;
    }

    .section-title {
        margin-top: 1.7rem;
        margin-bottom: 0.35rem;
        font-size: 1.55rem;
        font-weight: 700;
    }

    .section-note {
        color: var(--muted);
        margin-bottom: 1.2rem;
    }

    div[data-testid="stSelectbox"] > div,
    div[data-testid="stTextInput"] > div {
        background: rgba(255, 255, 255, 0.58);
        border-radius: 16px;
    }

    div[data-testid="stSelectbox"] label,
    div[data-testid="stTextInput"] label {
        color: #66675f;
        font-size: 0.9rem;
    }

    .travel-card-caption {
        text-align: center;
        color: #5c5d58;
        font-size: 0.95rem;
        margin-top: -0.35rem;
        margin-bottom: 1rem;
    }

    .info-chip {
        display: inline-block;
        background: rgba(116, 102, 91, 0.09);
        padding: 0.42rem 0.72rem;
        border-radius: 999px;
        margin: 0.18rem 0.18rem 0.18rem 0;
        color: #54554f;
        font-size: 0.88rem;
    }

    .quote-card {
        background: rgba(255, 255, 255, 0.58);
        border: 1px solid var(--line);
        padding: 1.2rem 1.35rem;
        border-radius: 22px;
        margin-top: 1rem;
        color: #5f605a;
        line-height: 1.75;
    }

    .footer {
        text-align: center;
        color: #92938d;
        font-size: 0.82rem;
        padding-top: 3rem;
    }

    /* clickable_images 내부 사진 스타일 보완 */
    iframe {
        border-radius: 22px !important;
    }

    div[data-testid="stDialog"] div[role="dialog"] {
        background: #faf7f1;
        border-radius: 28px;
    }

    @media (max-width: 700px) {
        .block-container {
            padding-left: 1rem;
            padding-right: 1rem;
        }
        .hero {
            padding-top: 1.7rem;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# -----------------------------
# 상세 정보 팝업
# -----------------------------
@st.dialog("여행지 이야기", width="large")
def show_destination(place):
    left, right = st.columns([1.18, 1], gap="large")

    with left:
        st.image(place["image"], use_container_width=True)

    with right:
        st.markdown(f"### {place['emoji']} {place['name']}")
        st.caption(f"{place['country']} · 대표 색상 {place['color_ko']}")
        st.write(place["description"])
        st.markdown(
            f"""
            <span class="info-chip">🗓 추천 시기 · {place['best_season']}</span>
            <span class="info-chip">✨ 분위기 · {place['mood']}</span>
            <span class="info-chip">📍 대표 장소 · {place['point']}</span>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="quote-card">“{place["short"]}”</div>',
            unsafe_allow_html=True,
        )

# -----------------------------
# 메인 화면
# -----------------------------
st.markdown(
    """
    <div class="hero">
        <div class="eyebrow">Find a place through color</div>
        <h1>Palette Voyage</h1>
        <p>
            지금 마음에 떠오르는 색을 골라 보세요.<br>
            세계의 풍경을 색으로 탐색하고, 사진을 눌러 그 장소의 이야기를 만나보세요.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

filter_col, search_col = st.columns([1, 1.45], gap="large")

with filter_col:
    selected_label = st.selectbox(
        "메인 색상",
        options=list(COLOR_OPTIONS.keys()),
        index=0,
    )

with search_col:
    keyword = st.text_input(
        "여행지 검색",
        placeholder="예: 산토리니, 프랑스, 알프스",
    ).strip().lower()

selected_color = COLOR_OPTIONS[selected_label]

filtered = [
    place
    for place in DESTINATIONS
    if (selected_color == "All" or place["main_color"] == selected_color)
    and (
        not keyword
        or keyword in place["name"].lower()
        or keyword in place["country"].lower()
        or keyword in place["short"].lower()
        or keyword in place["description"].lower()
    )
]

st.markdown('<div class="section-title">오늘의 풍경</div>', unsafe_allow_html=True)
st.markdown(
    f'<div class="section-note">{len(filtered)}개의 여행지가 선택되었습니다. 사진을 클릭해 자세히 살펴보세요.</div>',
    unsafe_allow_html=True,
)

if not filtered:
    st.info("조건에 맞는 여행지가 없습니다. 다른 색상이나 검색어를 선택해 보세요.")
else:
    clicked_index = clickable_images(
        paths=[place["image"] for place in filtered],
        titles=[
            f"{place['name']} · {place['country']} — {place['short']}"
            for place in filtered
        ],
        div_style={
            "display": "grid",
            "grid-template-columns": "repeat(auto-fit, minmax(260px, 1fr))",
            "gap": "18px",
            "padding": "6px 0 14px 0",
        },
        img_style={
            "width": "100%",
            "height": "245px",
            "object-fit": "cover",
            "border-radius": "22px",
            "cursor": "pointer",
            "box-shadow": "0 12px 32px rgba(50, 45, 38, 0.10)",
            "transition": "transform 0.25s ease, box-shadow 0.25s ease",
        },
        key=f"gallery-{selected_color}-{keyword}",
    )

    # 사진 제목을 별도 목록으로도 표시해 장소를 쉽게 확인하게 함
    with st.expander("현재 표시된 여행지 이름 보기"):
        names = " · ".join(
            f"{place['emoji']} {place['name']}({place['country']})"
            for place in filtered
        )
        st.write(names)

    if clicked_index > -1:
        show_destination(filtered[clicked_index])

st.markdown(
    """
    <div class="footer">
        Palette Voyage · Travel inspiration arranged by color
    </div>
    """,
    unsafe_allow_html=True,
)
