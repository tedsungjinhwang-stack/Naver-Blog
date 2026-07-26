"""니치·주제별 이미지 검색어 매핑.

Openverse/Pexels 같은 소스는 영문 검색 결과가 압도적으로 많으므로,
한글 주제 키워드를 영문 검색어로 옮겨준다.

동작:
  1) 글의 키워드(핵심/보조/제목)에서 트리거 단어를 찾는다.
  2) 매칭된 주제의 검색어를 우선 사용한다.
  3) 매칭이 없으면 니치 기본 검색어를 쓴다.
"""
from __future__ import annotations

from nbpipe.models import Niche

# 니치 기본 검색어 (매칭되는 세부 주제가 없을 때)
NICHE_DEFAULTS: dict[Niche, list[str]] = {
    Niche.ECONOMY: [
        "finance economy money",
        "bank interest rate",
        "korean won currency",
    ],
    Niche.INVESTING: [
        "stock market trading chart",
        "investment finance graph",
        "stock exchange screen",
    ],
    Niche.SIDEJOB: [
        "side job laptop work",
        "freelance work desk",
        "home office working",
    ],
    Niche.REALESTATE: [
        "apartment building city",
        "real estate house key",
        "housing complex korea",
    ],
}

# 세부 주제 트리거 → 영문 검색어
# (트리거는 소문자로 비교하며, 한글은 그대로 부분일치)
TOPIC_QUERIES: dict[Niche, list[tuple[tuple[str, ...], list[str]]]] = {
    Niche.ECONOMY: [
        (("금리", "기준금리", "코픽스", "interest"),
         ["interest rate bank", "central bank building", "percent sign finance"]),
        (("환율", "달러", "원화", "외환"),
         ["currency exchange dollar", "foreign exchange money", "us dollar bills"]),
        (("물가", "인플레", "인플레이션", "소비자물가"),
         ["grocery shopping price", "inflation shopping cart", "supermarket receipt"]),
        (("세금", "연말정산", "소득세", "부가세"),
         ["tax documents calculator", "tax form paperwork", "accounting desk"]),
        (("대출", "빚", "부채", "상환"),
         ["loan agreement document", "mortgage paperwork", "debt calculator"]),
        (("예금", "적금", "저축", "통장"),
         ["savings bank deposit", "piggy bank saving", "coins money jar"]),
        (("연금", "노후", "은퇴"),
         ["retirement planning senior", "pension savings", "elderly couple finance"]),
        (("고용", "취업", "실업", "일자리"),
         ["office workers employment", "job interview office", "business team work"]),
    ],
    Niche.INVESTING: [
        (("코스피", "코스닥", "지수", "증시", "주식"),
         ["stock market trading chart", "stock exchange screen", "candlestick chart"]),
        (("반도체", "삼성전자", "하이닉스", "메모리", "hbm"),
         ["semiconductor chip wafer", "computer chip technology",
          "microchip circuit board"]),
        (("etf", "펀드", "포트폴리오", "분산"),
         ["investment portfolio documents", "financial planning chart",
          "diversified investment"]),
        (("배당", "배당주", "인컴"),
         ["dividend money growth", "cash flow finance", "money plant growth"]),
        (("채권", "국채", "금리인하", "yield"),
         ["bond certificate finance", "treasury document", "financial documents"]),
        (("금", "은", "원자재", "유가", "원유"),
         ["gold bars bullion", "commodity oil barrel", "precious metals"]),
        (("코인", "비트코인", "가상자산", "crypto"),
         ["cryptocurrency bitcoin", "blockchain technology", "crypto trading screen"]),
        (("ai", "인공지능", "엔비디아", "빅테크"),
         ["artificial intelligence technology", "data center server",
          "computer technology abstract"]),
    ],
    Niche.SIDEJOB: [
        (("배달", "라이더", "쿠팡", "배민"),
         ["food delivery courier", "delivery scooter city",
          "delivery bag motorcycle"]),
        (("스마트스토어", "쇼핑몰", "이커머스", "위탁판매", "셀러"),
         ["online shop ecommerce", "packing parcel boxes", "small business shipping"]),
        (("블로그", "글쓰기", "애드포스트", "포스팅"),
         ["blogging laptop writing", "writing desk notebook", "typing keyboard work"]),
        (("유튜브", "영상", "쇼츠", "편집"),
         ["video camera studio", "video editing desk", "content creator filming"]),
        (("재택", "부업", "투잡", "사이드"),
         ["home office remote work", "laptop working late", "freelancer workspace"]),
        (("알바", "아르바이트", "시급"),
         ["part time work cafe", "barista working", "retail store worker"]),
        (("전자책", "강의", "클래스", "지식창업"),
         ["online course laptop", "ebook reading tablet", "online learning desk"]),
        (("디자인", "외주", "크몽", "프리랜서"),
         ["graphic design workspace", "freelance designer desk", "creative work desk"]),
    ],
    Niche.REALESTATE: [
        (("청약", "분양", "특별공급", "당첨"),
         ["apartment complex korea", "new apartment building",
          "residential construction"]),
        (("전세", "월세", "임대", "보증금", "계약"),
         ["rental contract signing", "house keys contract", "lease agreement paper"]),
        (("아파트", "단지", "실거래", "매매"),
         ["apartment building city", "residential apartment korea", "housing skyline"]),
        (("주담대", "담보대출", "ltv", "dsr", "대출"),
         ["mortgage loan house", "home loan document", "house money calculator"]),
        (("재건축", "재개발", "리모델링"),
         ["construction site building", "urban redevelopment", "building crane city"]),
        (("상가", "오피스텔", "수익형", "상업용"),
         ["commercial building storefront", "office building exterior",
          "retail street shop"]),
        (("인테리어", "집꾸미기", "리모델링"),
         ["home interior living room", "modern apartment interior",
          "cozy home design"]),
        (("토지", "땅", "농지", "전원주택"),
         ["land field countryside", "rural house land", "empty lot property"]),
    ],
}


def queries_for(
    niche: Niche,
    keywords: list[str] | None = None,
    limit: int = 3,
) -> list[str]:
    """니치 + 글 키워드로 이미지 검색어 목록을 만든다.

    매칭된 주제 검색어를 앞에 두고, 부족하면 니치 기본값으로 채운다.
    """
    haystack = " ".join(k for k in (keywords or []) if k).lower()

    picked: list[str] = []
    for triggers, qs in TOPIC_QUERIES.get(niche, []):
        if any(t.lower() in haystack for t in triggers):
            for q in qs:
                if q not in picked:
                    picked.append(q)

    for q in NICHE_DEFAULTS.get(niche, []):
        if len(picked) >= limit:
            break
        if q not in picked:
            picked.append(q)

    return picked[:limit]
