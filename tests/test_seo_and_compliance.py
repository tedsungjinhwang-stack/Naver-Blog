from nbpipe.config import load_config
from nbpipe.models import ImagePrompt, Intent, Niche, PostDraft
from nbpipe.seo import ComplianceChecker, SeoScorer


def _good_draft():
    body = "\n".join([
        "청약 가점은 무주택기간·부양가족·통장기간으로 계산합니다. 청약 가점 계산은 어렵지 않습니다.",
        "## 청약 가점 계산법",
        "| 항목 | 점수 |", "| --- | --- |", "| 무주택 | 32점 |",
        "무주택기간 32점, 부양가족 35점, 통장 17점으로 총 84점 만점입니다.",
        "## 실제 커트라인",
        "2025년 커트라인은 60점대였습니다. " * 20,
        "## 체크리스트", "- [ ] 무주택 확인", "- [ ] 통장 12개월",
        "청약 가점을 다시 점검하세요. 본 글은 정보 제공 목적이며 판단은 본인 책임입니다.",
    ])
    return PostDraft(
        niche=Niche.REALESTATE, primary_keyword="청약 가점",
        title="청약 가점 계산법 2026 총정리", intent=Intent.HOMEFEED,
        subtitles=["계산법", "커트라인", "체크리스트"], body_markdown=body,
        tags=["청약", "가점", "부동산", "무주택", "분양", "청약통장"],
        image_prompts=[ImagePrompt(f"p{i}", f"alt{i}", "캡처") for i in range(6)],
        summary="청약 가점 몇 점이면 될까요? 계산법과 커트라인을 정리했습니다.",
        meta={"secondary_keywords": ["무주택기간", "청약통장"]},
    )


def test_seo_scorer_good_draft_passes():
    scorer = SeoScorer(load_config())
    r = scorer.score(_good_draft())
    assert r.score >= 70
    assert r.passed
    keys = {c.key: c.passed for c in r.checks}
    assert keys["uniqueness_signal"]      # 표/수치/체크리스트
    assert keys["title_keyword_spam"]     # 키워드 1회
    assert keys["formulaic_intro"]        # 정형 서론 없음


def test_seo_scorer_detects_formulaic_and_spam():
    scorer = SeoScorer(load_config())
    bad = PostDraft(
        niche=Niche.ECONOMY, primary_keyword="기준금리",
        title="기준금리 기준금리 총정리",  # 2회 = 스팸
        body_markdown="오늘은 기준금리에 대해 알아보겠습니다. " + "내용 " * 50,
        summary="기준금리에 대해 알아보겠습니다.",
    )
    r = scorer.score(bad)
    fails = {c.key for c in r.checks if not c.passed}
    assert "title_keyword_spam" in fails
    assert "formulaic_intro" in fails
    assert "uniqueness_signal" in fails


def test_compliance_investing_blocks():
    chk = ComplianceChecker()
    r = chk.check("이 종목 수익 보장, 지금 매수하세요. 목표 수익률 30%", Niche.INVESTING)
    assert not r.passed
    labels = " ".join(c.label for c in r.blocks())
    assert "보장" in labels or "매수" in labels


def test_compliance_realestate_and_disclaimer():
    chk = ComplianceChecker()
    r = chk.check("단지 내 최저가! 확정 프리미엄 보장", Niche.REALESTATE)
    assert not r.passed  # 확정 프리미엄 = block


def test_compliance_affiliate_disclosure_required():
    chk = ComplianceChecker()
    # 쿠팡파트너스 언급하나 광고/제휴 표시 없음 -> block
    r = chk.check("이 제품은 쿠팡파트너스 링크로 구매 가능합니다.", Niche.SIDEJOB)
    assert not r.passed
    # 표시가 있으면 통과(다른 위반 없을 때)
    r2 = chk.check("이 글은 쿠팡파트너스 활동의 일환으로 광고 수수료를 제공받습니다.", Niche.SIDEJOB)
    assert r2.passed


def test_compliance_clean_text_passes():
    chk = ComplianceChecker()
    r = chk.check("경제 용어를 쉽게 정리했습니다. 물가와 금리의 관계를 살펴봅니다.", Niche.ECONOMY)
    assert r.passed
