"""이미지 검색어 매핑 + 출처 표기 + 렌더링 회귀 테스트 (네트워크 불필요)."""
from nbpipe.media.queries import NICHE_DEFAULTS, queries_for
from nbpipe.models import FetchedImage, Niche, PostDraft
from nbpipe.output.draft_writer import DraftWriter


def test_all_niches_have_defaults():
    for n in Niche:
        assert NICHE_DEFAULTS.get(n), f"{n} 기본 검색어 없음"


def test_topic_trigger_beats_default():
    q = queries_for(Niche.REALESTATE, ["전세 계약"])
    assert "rental contract signing" in q
    assert q[0] != NICHE_DEFAULTS[Niche.REALESTATE][0]


def test_unknown_keyword_falls_back_to_niche_default():
    q = queries_for(Niche.SIDEJOB, ["존재하지않는주제xyz"])
    assert q == NICHE_DEFAULTS[Niche.SIDEJOB][:3]


def test_specific_trigger_beats_shorter_one():
    """'쿠팡파트너스'(제휴마케팅)가 '쿠팡이츠'(배달)로 잘못 잡히지 않아야 한다."""
    q = queries_for(Niche.SIDEJOB, ["쿠팡파트너스"])
    assert "smartphone online shopping" in q
    assert "food delivery courier" not in q


def test_shopping_shorts_mapping():
    for kw in (["유튜브 쇼핑 쇼츠"], ["쇼핑쇼츠"], ["제휴마케팅"]):
        q = queries_for(Niche.SIDEJOB, kw)
        assert "smartphone online shopping" in q, kw


def test_queries_respect_limit():
    assert len(queries_for(Niche.INVESTING, ["코스피"], limit=2)) == 2


def test_attribution_rules():
    cc0 = FetchedImage(title="t", url="u", license_code="cc0", source="wikimedia")
    by = FetchedImage(title="t", url="u", license_code="by", source="flickr",
                      creator="Someone", license_url="https://x/by")
    assert not cc0.needs_attribution
    assert by.needs_attribution
    assert "Someone" in by.credit_line()
    assert "표기 의무 없음" in cc0.credit_line()


def test_naver_text_separates_photos_and_placeholders(tmp_path):
    draft = PostDraft(
        niche=Niche.INVESTING, primary_keyword="코스피", title="제목",
        body_markdown="## 소제목\n\n본문임.\n", tags=["코스피"],
        stock_images=[
            FetchedImage(title="a", url="u1", license_code="by", source="flickr",
                         creator="C", file="a.jpg", path="/x/a.jpg"),
            FetchedImage(title="b", url="u2", license_code="cc0",
                         source="rawpixel", file="b.jpg", path="/x/b.jpg"),
        ],
    )
    txt = DraftWriter(tmp_path)._render_naver_text(draft)
    assert "[사진A] a.jpg" in txt          # 실제 파일은 [사진X]
    assert "[사진B] b.jpg" in txt
    assert "[이미지 출처]" in txt           # BY 한 장이므로 출처 블록 존재
    assert "by C" in txt


def test_no_credit_block_when_all_public_domain(tmp_path):
    draft = PostDraft(
        niche=Niche.ECONOMY, primary_keyword="금리", title="제목",
        body_markdown="본문임.\n",
        stock_images=[FetchedImage(title="a", url="u", license_code="cc0",
                                   source="rawpixel", file="a.jpg")],
    )
    txt = DraftWriter(tmp_path)._render_naver_text(draft)
    assert "[사진A] a.jpg" in txt
    # 헤더 안내문에는 단어가 등장하므로, 실제 출처 블록(줄 시작)만 검사한다
    assert not any(ln.startswith("[이미지 출처]") for ln in txt.splitlines())
