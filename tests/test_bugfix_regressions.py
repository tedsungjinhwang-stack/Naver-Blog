"""코드리뷰에서 확인된 버그들의 회귀 방지 테스트."""
from nbpipe.analysis import KeywordSelector
from nbpipe.config import load_config
from nbpipe.models import ImagePrompt, Intent, Keyword, Niche, PostDraft
from nbpipe.output.draft_writer import _inline
from nbpipe.seo import ComplianceChecker, SeoScorer


def _draft(body, **kw):
    base = dict(
        niche=Niche.ECONOMY, primary_keyword="금리", title="금리 정리 2026",
        intent=Intent.SEARCH, body_markdown=body, tags=["금리"],
        image_prompts=[ImagePrompt("p", "a", "x")], summary="금리 요약",
        meta={"secondary_keywords": []},
    )
    base.update(kw)
    return PostDraft(**base)


def test_affiliate_disclosure_not_bypassed_by_제휴_substring():
    """#2: '제휴링크' 가 disclosure 마커 '제휴' 를 포함해 자동통과되던 버그."""
    chk = ComplianceChecker()
    r = chk.check("제휴링크 첨부합니다. 참고하세요.", Niche.SIDEJOB)
    assert not r.passed  # 대가성 고지 없음 → block
    r2 = chk.check("제휴링크입니다. 이 글은 광고를 포함합니다.", Niche.SIDEJOB)
    assert r2.passed     # '광고' 고지 있음 → 통과


def test_two_tables_not_flagged_as_duplicate():
    """#3: 표 구분선 '| --- |' 중복이 유사문서로 오탐되던 버그."""
    body = "\n".join([
        "금리는 이렇게 움직입니다. 서로 다른 문장 하나입니다.",
        "| 항목 | 값 |", "| --- | --- |", "| 기준금리 | 3.5 |",
        "완전히 다른 설명 문장이 여기에 옵니다. 내용을 채웁니다.",
        "| 구분 | 결과 |", "| --- | --- |", "| 예금 | 감소 |",
    ])
    r = SeoScorer(load_config()).score(_draft(body))
    risk = next(c for c in r.checks if c.key == "similar_doc_risk")
    assert risk.passed  # 표 구분선 반복은 위험으로 잡지 않음


def test_inline_does_not_italicize_footnote_asterisks():
    """#9: '30만원* 기준' 이 통째로 <em> 처리되던 버그."""
    out = _inline("월 적립 30만원* 기준, 연 360만원* 예상")
    assert "<em>" not in out
    # 진짜 마크다운 이탤릭은 유지
    assert _inline("이건 *강조* 입니다") == "이건 <em>강조</em> 입니다"


def test_select_limit_zero_returns_empty():
    """#5: limit=0 이 max_keywords 로 대체되던 버그."""
    sel = KeywordSelector(load_config())
    kws = [Keyword("금리", "seed_topics", rank=0), Keyword("환율", "seed_topics", rank=1)]
    assert sel.select(kws, Niche.ECONOMY, limit=0) == []
    assert len(sel.select(kws, Niche.ECONOMY, limit=1)) == 1


def test_multiword_include_token_matches_bonus():
    """#6: 멀티워드 include_token('미국 증시')이 보너스 매칭 안 되던 버그."""
    sel = KeywordSelector(load_config())
    kws = [
        Keyword("미국 증시 전망", "naver_autocomplete", rank=0),
        Keyword("날씨 정보", "naver_autocomplete", rank=1),
    ]
    ranked = sel.select(kws, Niche.ECONOMY, include_tokens=["미국 증시"])
    by_term = {m.term: m.score for m in ranked}
    # '미국 증시 전망' 이 니치 보너스를 받아 '날씨 정보' 보다 높아야 함
    assert by_term["미국 증시 전망"] > by_term["날씨 정보"]


def test_secondary_usage_rounds_up_half():
    """#8: 홀수 보조키워드에서 '절반 이상'이 내림돼 미달인데 통과하던 버그."""
    cfg = load_config()
    body = "금리 " * 400 + " 인하 관련 설명"  # secondary '인하'만 등장
    d = _draft(body, meta={"secondary_keywords": ["인하", "동결", "인상"]})  # 3개 중 1개 사용
    r = SeoScorer(cfg).score(d)
    sec = next(c for c in r.checks if c.key == "secondary_usage")
    assert not sec.passed  # 3개면 2개 이상 필요 → 1개는 미달
