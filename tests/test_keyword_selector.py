from nbpipe.analysis import KeywordSelector, merge_keywords
from nbpipe.analysis.keyword_selector import _rank_decay
from nbpipe.config import load_config
from nbpipe.models import Keyword, Niche


def _cfg():
    return load_config()


def test_merge_keywords_dedup_and_sources():
    kws = [
        Keyword("ETF 투자", "seed_topics", rank=0),
        Keyword("etf 투자", "naver_autocomplete", rank=1, search_volume=50),
    ]
    merged = merge_keywords(kws)
    assert len(merged) == 1
    m = next(iter(merged.values()))
    assert m.sources == {"seed_topics", "naver_autocomplete"}
    assert m.search_volume == 50


def test_rank_decay_monotonic():
    assert _rank_decay(0) > _rank_decay(5) > _rank_decay(20)
    assert _rank_decay(None) < _rank_decay(0)


def test_select_filters_excluded_and_scores():
    sel = KeywordSelector(_cfg())
    kws = [
        Keyword("ETF 투자", "seed_topics", rank=0),
        Keyword("ETF 추천", "naver_autocomplete", rank=1),
        Keyword("성인 도박 사이트", "naver_autocomplete", rank=2),
    ]
    ranked = sel.select(
        kws, Niche.INVESTING,
        include_tokens=["ETF", "투자"],
        exclude_terms=["도박", "성인"],
    )
    terms = [m.term for m in ranked]
    assert "성인 도박 사이트" not in terms
    assert ranked[0].score >= ranked[-1].score  # 정렬됨


def test_recent_terms_excluded():
    sel = KeywordSelector(_cfg())
    kws = [Keyword("배당주", "seed_topics", rank=0),
           Keyword("연금저축", "seed_topics", rank=1)]
    ranked = sel.select(kws, Niche.INVESTING, recent_terms=["배당주"])
    assert "배당주" not in [m.term for m in ranked]


def test_build_topic_plans():
    sel = KeywordSelector(_cfg())
    kws = [Keyword(t, "seed_topics", rank=i) for i, t in
           enumerate(["ETF 투자", "ETF 추천", "배당주 투자", "연금저축"])]
    ranked = sel.select(kws, Niche.INVESTING)
    plans = sel.build_topic_plans(ranked, Niche.INVESTING, count=2, seeds=["ETF"])
    assert len(plans) == 2
    assert plans[0].primary_keyword
    assert plans[0].secondary_keywords
    # primary 는 secondary 에 중복되지 않음
    assert plans[0].primary_keyword not in plans[0].secondary_keywords
