import tempfile
from pathlib import Path

from nbpipe.collectors import NaverAutocompleteCollector, SeedTopicsCollector
from nbpipe.config import load_config
from nbpipe.models import ImagePrompt, Intent, Keyword, Niche, PostDraft
from nbpipe.output import DraftWriter


def test_seed_topics_collector():
    c = SeedTopicsCollector(load_config())
    out = c.collect(["기준금리", "  ", "물가"], Niche.ECONOMY)
    assert [k.term for k in out] == ["기준금리", "물가"]
    assert all(k.source == "seed_topics" for k in out)


def test_autocomplete_parse_without_network(monkeypatch):
    c = NaverAutocompleteCollector(load_config())
    sample = {"query": ["ETF"], "items": [[["ETF 투자방법", "x"], ["ETF 추천", "y"]]]}
    monkeypatch.setattr(c, "_get_json", lambda url, params=None: sample)
    res = c._query_one("ETF")
    assert res == ["ETF 투자방법", "ETF 추천"]


def test_autocomplete_handles_error(monkeypatch):
    c = NaverAutocompleteCollector(load_config())
    def boom(url, params=None):
        raise RuntimeError("network down")
    monkeypatch.setattr(c, "_get_json", boom)
    assert c._query_one("ETF") == []  # 예외 시 조용히 빈 리스트


def test_draft_writer_outputs_files():
    draft = PostDraft(
        niche=Niche.SIDEJOB, primary_keyword="블로그 부업",
        title="블로그 부업 시작 가이드", intent=Intent.HOMEFEED,
        subtitles=["시작", "수익"], body_markdown="## 시작\n내용입니다.\n## 수익\n내용입니다.",
        tags=["부업", "블로그", "재택", "부수입", "애드포스트"],
        image_prompts=[ImagePrompt("상단", "블로그 부업", "캡처")],
        summary="블로그 부업, 이렇게 시작하세요.",
    )
    with tempfile.TemporaryDirectory() as d:
        files = DraftWriter(d).write(draft, ["markdown", "html"])
        assert len(files) == 2
        md = next(f for f in files if f.suffix == ".md")
        html = next(f for f in files if f.suffix == ".html")
        md_text = md.read_text(encoding="utf-8")
        assert "블로그 부업 시작 가이드" in md_text
        assert "홈피드형" in md_text            # intent 표시
        assert "발행 체크리스트" in md_text
        html_text = html.read_text(encoding="utf-8")
        assert "<h1>" in html_text and "블로그 부업" in html_text


def test_config_defaults_loaded():
    cfg = load_config()
    assert cfg.seo["title_len_max"] == 30
    assert cfg.seo["min_images"] == 6
    assert cfg.collectors["naver_related"] is False
    assert "generation" not in cfg.data  # API 생성 설정 없음
