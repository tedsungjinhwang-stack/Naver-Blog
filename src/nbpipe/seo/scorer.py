"""네이버 블로그 노출 최적화 관점의 온페이지 SEO 스코어러.

C-Rank(전문성)·D.I.A.(문서품질) 알고리즘이 선호하는 신호를 근사한 체크리스트로
점수화한다. 임계값은 config.seo 에서 조정(knowledge/hompan.md 리서치 반영).

주의: 실제 랭킹은 비공개 알고리즘이므로 이 점수는 '발행 전 자가진단' 용도다.
"""
from __future__ import annotations

import re
from typing import Any

from nbpipe.models import CheckResult, Intent, PostDraft, SeoReport

_HEADING_RE = re.compile(r"^#{2,4}\s+\S", re.MULTILINE)
_SENTENCE_SPLIT = re.compile(r"[.!?。…\n]+")
_TABLE_RE = re.compile(r"^\s*\|.+\|\s*$", re.MULTILINE)
_NUMBER_RE = re.compile(r"\d+\s*(원|만원|억|%|퍼센트|배|년|개월|위|명|건)")

# 정형(AI 티 나는) 서론/채우기 문구 — D.I.A.+ 감점 요인
_FORMULAIC_PATTERNS = [
    r"에\s*대해\s*(자세히\s*)?알아보(겠습니다|도록)",
    r"알아보는\s*시간을\s*가지",
    r"포스팅을\s*준비했",
    r"오늘은\s*.*에\s*대해\s*(이야기|얘기)",
    r"지금부터\s*하나씩\s*살펴보",
]


def _count_occurrences(text: str, term: str) -> int:
    if not term:
        return 0
    return len(re.findall(re.escape(term), text, flags=re.IGNORECASE))


# (key: weight) — weight 합으로 100점 정규화
_CHECK_WEIGHTS = {
    "title_length": 9,
    "title_keyword": 13,
    "title_keyword_spam": 4,
    "keyword_in_intro": 10,
    "body_length": 13,
    "headings": 10,
    "images": 10,
    "tags_count": 6,
    "primary_keyword_count": 9,
    "secondary_usage": 5,
    "uniqueness_signal": 8,
    "formulaic_intro": 5,
    "similar_doc_risk": 8,   # 감점형
}


class SeoScorer:
    def __init__(self, config: Any) -> None:
        self.cfg = getattr(config, "seo", {}) or {}

    def score(self, draft: PostDraft) -> SeoReport:
        body = draft.body_markdown or ""
        char_count = draft.char_count()
        title = draft.title or ""
        primary = draft.primary_keyword or ""
        checks: list[CheckResult] = []

        def add(key, label, passed, *, detail="", value=None, target=None,
                severity="warn"):
            checks.append(CheckResult(
                key=key, label=label, passed=passed, detail=detail,
                value=value, target=target, severity=severity,
            ))

        # 1. 제목 길이
        tmin = self.cfg.get("title_len_min", 12)
        tmax = self.cfg.get("title_len_max", 40)
        tlen = len(title)
        add("title_length", "제목 길이", tmin <= tlen <= tmax,
            value=f"{tlen}자", target=f"{tmin}~{tmax}자",
            detail="너무 짧거나(정보부족) 길면(잘림) 노출·클릭에 불리")

        # 2. 제목에 핵심 키워드 & 앞쪽 배치
        pos = title.lower().find(primary.lower()) if primary else -1
        add("title_keyword", "제목 내 핵심 키워드(앞쪽 배치)",
            pos != -1 and pos <= 15,
            value=(f"위치 {pos}" if pos != -1 else "없음"), target="0~15자",
            detail="핵심 키워드를 제목 앞부분에 자연스럽게 배치")

        # 2-b. 제목 키워드 과반복(스팸) 방지 — 리서치: 제목엔 메인 키워드 1회만
        title_kc = _count_occurrences(title, primary)
        add("title_keyword_spam", "제목 키워드 1회 사용", title_kc <= 1,
            value=f"{title_kc}회", target="1회",
            detail="제목에 동일 키워드 2회 이상은 스팸/패널티 위험")

        # 3. 도입부 키워드 (요약+본문 앞부분)
        head = re.sub(r"\s+", "", (draft.summary or "") + body[:200])
        add("keyword_in_intro", "도입부(첫 문단) 키워드 등장",
            bool(primary) and primary.replace(" ", "") in head,
            detail="첫 문단 안에 핵심 키워드 1회 이상")

        # 4. 본문 분량 (intent별: 홈피드형은 2,000자+)
        bmin = int(self.cfg.get("body_char_min", 1700))
        if draft.intent == Intent.HOMEFEED:
            bmin = max(bmin, 2000)
        add("body_length", "본문 분량(공백제외)", char_count >= bmin,
            value=f"{char_count:,}자", target=f"≥{bmin:,}자 ({draft.intent.korean})",
            detail="정보성·체류시간 확보를 위한 최소 분량")

        # 5. 소제목(목차)
        n_head = len(_HEADING_RE.findall(body)) or len(draft.subtitles)
        hmin = self.cfg.get("min_headings", 3)
        add("headings", "소제목(목차) 개수", n_head >= hmin,
            value=n_head, target=f"≥{hmin}",
            detail="소제목으로 가독성/구조화 → 체류시간↑")

        # 6. 이미지
        n_img = len(draft.image_prompts)
        imin = self.cfg.get("min_images", 5)
        add("images", "이미지 개수(자리표시자 기준)", n_img >= imin,
            value=n_img, target=f"≥{imin}",
            detail="직접 촬영/제작 이미지 권장(펌 이미지 지양)")

        # 7. 태그
        n_tags = len(draft.tags)
        gmin = self.cfg.get("tags_min", 5)
        gmax = self.cfg.get("tags_max", 10)
        add("tags_count", "태그 개수", gmin <= n_tags <= gmax,
            value=n_tags, target=f"{gmin}~{gmax}",
            detail="핵심+연관 위주, 무관 태그 남발 금지")

        # 8. 핵심 키워드 반복(과최적화 방지)
        kc = _count_occurrences(body, primary)
        kmin = self.cfg.get("primary_keyword_min_count", 3)
        kmax = self.cfg.get("primary_keyword_max_count", 8)
        add("primary_keyword_count", "핵심 키워드 반복 횟수",
            kmin <= kc <= kmax,
            value=kc, target=f"{kmin}~{kmax}",
            detail="너무 적으면 관련성↓, 너무 많으면 키워드 스터핑 감점")

        # 9. 보조 키워드 활용
        used = sum(1 for k in draft.meta.get("secondary_keywords", [])
                   if _count_occurrences(body, k) > 0)
        n_sec = len(draft.meta.get("secondary_keywords", []))
        add("secondary_usage", "보조 키워드 활용",
            n_sec == 0 or used >= max(1, (n_sec + 1) // 2),  # 올림('절반 이상')
            value=f"{used}/{n_sec}", target="절반 이상",
            detail="연관 키워드를 본문에 자연스럽게 녹임")

        # 10. 고유성 신호(표/구체 수치/체크리스트) — D.I.A.+ 대응 최우선
        has_table = bool(_TABLE_RE.search(body))
        has_numbers = len(_NUMBER_RE.findall(body)) >= 3
        has_checklist = bool(re.search(r"^\s*(- \[.\]|✓|✅|\d+\.)", body, re.MULTILINE))
        uniq_score = sum([has_table, has_numbers, has_checklist])
        add("uniqueness_signal", "고유성 요소(표/수치/체크리스트)", uniq_score >= 1,
            value=f"표:{has_table} 수치:{has_numbers} 목록:{has_checklist}",
            target="1개 이상",
            detail="실경험·구체 수치·표/체크리스트로 복붙 불가한 고유 정보 확보")

        # 11. 정형(AI 티) 서론/채우기 문구
        formulaic = [p for p in _FORMULAIC_PATTERNS
                     if re.search(p, (draft.summary or "") + body)]
        add("formulaic_intro", "정형 서론/채우기 문구 회피", not formulaic,
            value=("발견" if formulaic else "없음"),
            detail="‘~에 대해 알아보겠습니다’ 식 정형 서론은 D.I.A.+ 감점 요인")

        # 12. 유사문서/스터핑 위험(휴리스틱)
        risk, risk_detail = self._similarity_risk(body, primary, char_count, kc)
        add("similar_doc_risk", "유사문서/스터핑 위험", not risk,
            detail=risk_detail, severity="warn")

        # 점수 계산
        total_w = sum(_CHECK_WEIGHTS.values())
        got = sum(_CHECK_WEIGHTS.get(c.key, 0) for c in checks if c.passed)
        score = round(got / total_w * 100)
        passed = score >= self.cfg.get("pass_score", 70)
        return SeoReport(score=score, passed=passed, checks=checks)

    def _similarity_risk(
        self, body: str, primary: str, char_count: int, kc: int
    ) -> tuple[bool, str]:
        reasons: list[str] = []
        # (a) 키워드 밀도 과다
        if char_count > 0:
            density = kc / max(1.0, char_count / 500.0)  # 500자당 등장수
            if density > 3.0:
                reasons.append(f"키워드 밀도 과다(500자당 {density:.1f}회)")
        # (b) 동일 문장 반복 (마크다운 표/구분선 등 구조적 라인은 제외)
        sentences = [
            s.strip() for s in _SENTENCE_SPLIT.split(body)
            if len(s.strip()) > 10
            and not s.lstrip().startswith("|")          # 표 행
            and not re.fullmatch(r"[|\-:_=\s]+", s.strip())  # 구분선
        ]
        seen: dict[str, int] = {}
        for s in sentences:
            seen[s] = seen.get(s, 0) + 1
        dup = [s for s, n in seen.items() if n >= 2]
        if dup:
            reasons.append(f"동일 문장 반복 {len(dup)}건")
        if reasons:
            return True, "; ".join(reasons)
        return False, "특이사항 없음"
