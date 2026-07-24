import textwrap
from pathlib import Path

from nbpipe.authoring import parse_authored_post, render_brief, split_front_matter
from nbpipe.config import load_config
from nbpipe.models import Intent, Niche, TopicPlan


def test_split_front_matter():
    text = "---\nniche: economy\nprimary_keyword: 금리\n---\n## 본문\n내용"
    meta, body = split_front_matter(text)
    assert meta["niche"] == "economy"
    assert body.strip().startswith("## 본문")


def test_split_front_matter_absent():
    meta, body = split_front_matter("front-matter 없음\n본문")
    assert meta == {}
    assert "본문" in body


def test_parse_authored_post(tmp_path: Path):
    p = tmp_path / "post.md"
    p.write_text(textwrap.dedent("""\
        ---
        niche: 경제
        intent: homefeed
        primary_keyword: 기준금리
        secondary_keywords: [금리 인하, 대출 금리]
        title: 기준금리 인하, 내 대출이자 얼마나 줄까
        tags: [기준금리, 금리, 대출, 예금, 경제]
        summary: |
          기준금리가 내리면 무엇이 달라질까요?
        image_prompts:
          - position: 도입부 아래
            alt: 기준금리 추이
            prompt: 한국은행 기준금리 그래프 캡처
        ---
        ## 기준금리란
        기준금리는 한국은행이 정하는 정책금리입니다.
        ## 내 대출에 미치는 영향
        변동금리 대출이라면 이자가 줄어듭니다.
        """), encoding="utf-8")
    d = parse_authored_post(p)
    assert d.niche is Niche.ECONOMY
    assert d.intent is Intent.HOMEFEED
    assert d.primary_keyword == "기준금리"
    assert d.title.startswith("기준금리 인하")
    assert d.subtitles == ["기준금리란", "내 대출에 미치는 영향"]  # 본문에서 자동추출
    assert d.tags == ["기준금리", "금리", "대출", "예금", "경제"]
    assert d.meta["secondary_keywords"] == ["금리 인하", "대출 금리"]
    assert len(d.image_prompts) == 1


def test_parse_requires_niche_and_keyword(tmp_path: Path):
    import pytest
    p = tmp_path / "bad.md"
    p.write_text("---\nintent: search\n---\n본문", encoding="utf-8")
    with pytest.raises(ValueError):
        parse_authored_post(p)


def test_render_brief_roundtrip():
    cfg = load_config()
    plan = TopicPlan(
        niche=Niche.INVESTING, primary_keyword="ETF 투자",
        secondary_keywords=["배당 ETF"], intent=Intent.HOMEFEED,
    )
    brief = render_brief(plan, cfg.seo)
    assert "primary_keyword: ETF 투자" in brief
    # 브리핑은 주석 가이드 뒤에 front-matter 가 온다 → 첫 '---' 부터 파싱
    fm_text = brief[brief.index("---"):]
    meta, _body = split_front_matter(fm_text)
    assert meta.get("niche") == "investing"
    assert meta.get("intent") == "homefeed"
