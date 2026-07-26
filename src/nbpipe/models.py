"""파이프라인 전역에서 오가는 데이터 모델.

외부 의존성 없이 표준 라이브러리(dataclasses)만 사용한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class Niche(str, Enum):
    """지원 니치. 값은 파일명/설정 키로도 쓰인다."""

    ECONOMY = "economy"        # 경제
    INVESTING = "investing"    # 투자(주식/재테크)
    SIDEJOB = "sidejob"        # 부업
    REALESTATE = "realestate"  # 부동산

    @property
    def korean(self) -> str:
        return {
            Niche.ECONOMY: "경제",
            Niche.INVESTING: "투자",
            Niche.SIDEJOB: "부업",
            Niche.REALESTATE: "부동산",
        }[self]

    @classmethod
    def from_str(cls, value: str) -> "Niche":
        v = (value or "").strip().lower()
        # 한글 별칭도 허용
        aliases = {
            "경제": cls.ECONOMY,
            "투자": cls.INVESTING,
            "주식": cls.INVESTING,
            "재테크": cls.INVESTING,
            "부업": cls.SIDEJOB,
            "부동산": cls.REALESTATE,
        }
        if v in aliases:
            return aliases[v]
        for member in cls:
            if member.value == v:
                return member
        raise ValueError(
            f"알 수 없는 니치: {value!r}. "
            f"가능: {', '.join(m.value for m in cls)} (또는 한글 경제/투자/부업/부동산)"
        )


class Intent(str, Enum):
    """콘텐츠 목표 유형. 리서치 결과 '검색형/홈피드형' 투트랙이 표준.

    - HOMEFEED: 홈판(모바일 메인 추천피드) 겨냥. 이슈 연결·감정 후킹·반전 제목,
      2,000자+ 롱폼, 저녁 발행. (사용자 기본 목표)
    - SEARCH  : 검색 상위노출 겨냥. 키워드·정보밀도·구조화, 오전 발행.
    """

    HOMEFEED = "homefeed"
    SEARCH = "search"

    @property
    def korean(self) -> str:
        return {Intent.HOMEFEED: "홈피드형", Intent.SEARCH: "검색형"}[self]

    @classmethod
    def from_str(cls, value: str) -> "Intent":
        v = (value or "").strip().lower()
        aliases = {"홈피드": cls.HOMEFEED, "홈판": cls.HOMEFEED, "검색": cls.SEARCH}
        if v in aliases:
            return aliases[v]
        for member in cls:
            if member.value == v:
                return member
        raise ValueError(f"알 수 없는 intent: {value!r} (homefeed|search)")

    def publish_window(self) -> str:
        """리서치 기반 권장 발행 시간대."""
        return "저녁 7~10시" if self is Intent.HOMEFEED else "화~목 오전 7~10시"


@dataclass
class Keyword:
    """단일 키워드 후보와 그 출처/점수."""

    term: str
    source: str                       # 예: naver_autocomplete, seed_topics ...
    score: float = 0.0                # 선정 스코어(정규화 전 raw 가중치 합)
    rank: int | None = None           # 소스 내부 순위(있을 때)
    search_volume: int | None = None  # DataLab 등에서 얻은 상대 검색량(있을 때)
    meta: dict[str, Any] = field(default_factory=dict)

    def normalized(self) -> str:
        """공백/특수문자를 정리한 비교용 키."""
        return re.sub(r"\s+", " ", self.term.strip()).lower()


@dataclass
class TopicPlan:
    """생성 단계로 넘길 하나의 글 기획안."""

    niche: Niche
    primary_keyword: str
    secondary_keywords: list[str] = field(default_factory=list)
    intent: Intent = Intent.HOMEFEED         # 검색형/홈피드형
    seed_topic: str | None = None            # 사용자가 지정한 원 주제
    angle: str | None = None                 # 콘텐츠 앵글/포맷 힌트
    rationale: str | None = None             # 이 키워드를 고른 이유(로그용)
    keywords: list[Keyword] = field(default_factory=list)  # 근거가 된 원 키워드들

    def all_keywords(self) -> list[str]:
        out = [self.primary_keyword, *self.secondary_keywords]
        seen: set[str] = set()
        uniq: list[str] = []
        for k in out:
            key = k.strip().lower()
            if key and key not in seen:
                seen.add(key)
                uniq.append(k.strip())
        return uniq


@dataclass
class CheckResult:
    """개별 SEO/컴플라이언스 체크 1건의 결과."""

    key: str
    label: str
    passed: bool
    detail: str = ""
    severity: str = "warn"   # info | warn | block
    value: Any = None
    target: Any = None


@dataclass
class SeoReport:
    score: int = 0
    passed: bool = False
    checks: list[CheckResult] = field(default_factory=list)

    def failures(self, severity: str | None = None) -> list[CheckResult]:
        return [
            c for c in self.checks
            if not c.passed and (severity is None or c.severity == severity)
        ]


@dataclass
class ComplianceReport:
    passed: bool = True
    checks: list[CheckResult] = field(default_factory=list)

    def blocks(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed and c.severity == "block"]


@dataclass
class ImagePrompt:
    """이미지 자리표시자 + 생성/촬영 가이드(초안엔 실제 이미지 대신 안내만)."""

    position: str        # 예: "본문 상단", "소제목2 아래"
    alt: str             # 대체텍스트(키워드 포함 권장)
    prompt: str          # 이미지 생성/삽입 가이드
    caption: str = ""


# 출처 표기 의무가 없는 라이선스(퍼블릭 도메인 계열 + 자체 라이선스)
_NO_ATTRIBUTION = {"cc0", "pdm", "pexels", "unsplash"}


@dataclass
class FetchedImage:
    """API로 수집한 실제 이미지 파일 + 라이선스/출처 정보."""

    title: str
    url: str                     # 원본 이미지 URL
    license_code: str            # cc0 / pdm / by / by-sa / pexels / unsplash
    source: str                  # flickr, wikimedia, rawpixel, pexels ...
    query: str = ""              # 어떤 검색어로 찾았는지
    page_url: str = ""           # 원저작물 페이지
    creator: str = ""
    license_url: str = ""
    file: str = ""               # 저장된 파일명(다운로드 후 채워짐)
    path: str = ""               # 저장 경로

    @property
    def needs_attribution(self) -> bool:
        return self.license_code.lower() not in _NO_ATTRIBUTION

    def credit_line(self) -> str:
        """블로그 하단에 붙일 출처 문구."""
        if not self.needs_attribution:
            return (f"{self.title} — {self.source} "
                    f"({self.license_code.upper()}, 출처 표기 의무 없음)")
        parts = [f'"{self.title}"', f"by {self.creator or 'Unknown'}"]
        if self.page_url:
            parts.append(f"({self.page_url})")
        parts.append(f"/ {self.license_code.upper()}")
        if self.license_url:
            parts.append(self.license_url)
        return " ".join(parts)

    def as_dict(self) -> dict[str, Any]:
        return {
            "file": self.file, "title": self.title, "creator": self.creator,
            "license": self.license_code, "license_url": self.license_url,
            "source": self.source, "page_url": self.page_url,
            "query": self.query, "needs_attribution": self.needs_attribution,
        }


@dataclass
class PostDraft:
    """최종 초안 산출물."""

    niche: Niche
    primary_keyword: str
    title: str
    intent: Intent = Intent.HOMEFEED
    title_candidates: list[str] = field(default_factory=list)
    subtitles: list[str] = field(default_factory=list)   # 소제목(목차)
    body_markdown: str = ""
    tags: list[str] = field(default_factory=list)
    image_prompts: list[ImagePrompt] = field(default_factory=list)
    stock_images: list[FetchedImage] = field(default_factory=list)  # API 수집 이미지
    summary: str = ""                                    # 도입부/요약
    meta: dict[str, Any] = field(default_factory=dict)   # 모델/토큰/키워드 등
    seo: SeoReport | None = None
    compliance: ComplianceReport | None = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def char_count(self) -> int:
        """공백 제외 본문 글자수(네이버 체감 분량 근사)."""
        return len(re.sub(r"\s+", "", self.body_markdown))

    def slug(self) -> str:
        base = re.sub(r"[^\w가-힣]+", "-", self.primary_keyword.strip())
        return re.sub(r"-+", "-", base).strip("-")[:40] or "post"
