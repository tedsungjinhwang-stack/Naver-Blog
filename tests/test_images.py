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
    assert "product review filming" in q
    assert "food delivery courier" not in q


def test_shopping_shorts_mapping():
    for kw in (["유튜브 쇼핑 쇼츠"], ["쇼핑쇼츠"], ["제휴마케팅"]):
        q = queries_for(Niche.SIDEJOB, kw)
        assert "product review filming" in q, kw


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


def test_markdown_table_becomes_html_table():
    """리치 복사의 핵심이 표라, 마크다운 표는 반드시 <table>로 변환돼야 한다."""
    from nbpipe.output.draft_writer import _md_to_html_body
    md = "| 구분 | 값 |\n| --- | --- |\n| 이자 | 75만원 |\n"
    out = _md_to_html_body(md)
    assert "<table>" in out and "<th>구분</th>" in out and "<td>75만원</td>" in out
    assert "---" not in out          # 구분선이 셀로 새어나오지 않아야 함
    assert "<p>|" not in out         # 파이프 원문이 문단으로 남지 않아야 함


def test_paste_html_has_copy_zone_and_buttons(tmp_path):
    from nbpipe.models import Intent, PostDraft
    from nbpipe.output.draft_writer import DraftWriter
    draft = PostDraft(
        niche=Niche.ECONOMY, primary_keyword="기준금리", title="제목",
        intent=Intent.HOMEFEED, tags=["기준금리", "대출"],
        body_markdown="## 소제목\n\n본문임.\n\n| a | b |\n| --- | --- |\n| 1 | 2 |\n",
    )
    out = DraftWriter(tmp_path)._render_paste_html(draft)
    assert 'id="copy-body"' in out
    assert "본문 복사" in out and "제목 복사" in out and "태그 복사" in out
    assert "<table>" in out
    # 복사 영역 안에 안내 UI가 섞여 들어가면 네이버 본문까지 딸려간다
    body = out.split('<div id="copy-body">')[1]
    assert "<button" not in body


def test_paste_html_included_in_default_formats(tmp_path):
    from nbpipe.models import PostDraft
    from nbpipe.output.draft_writer import DraftWriter
    draft = PostDraft(niche=Niche.ECONOMY, primary_keyword="금리", title="t",
                      body_markdown="본문임.\n")
    names = {p.suffix for p in DraftWriter(tmp_path).write(draft)}
    assert ".html" in names and ".txt" in names and ".md" in names
    assert any(p.name.endswith(".paste.html")
               for p in DraftWriter(tmp_path).write(draft))


def test_images_embedded_at_their_slots(tmp_path):
    """front-matter 의 file 이 지정된 이미지는 지정한 소제목 자리에 삽입돼야 한다."""
    import base64
    from nbpipe.models import ImagePrompt, PostDraft
    from nbpipe.output.draft_writer import DraftWriter

    png = tmp_path / "a.png"
    # 1x1 PNG
    png.write_bytes(base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="))
    draft = PostDraft(
        niche=Niche.INVESTING, primary_keyword="코스피", title="t",
        body_markdown="## 첫째\n\n가.\n\n## 둘째\n\n나.\n",
        image_prompts=[
            ImagePrompt(position="소제목2 아래", alt="차트", prompt="p",
                        file=str(png)),
            ImagePrompt(position="소제목1 아래", alt="없는파일", prompt="직접 촬영"),
        ],
    )
    out = DraftWriter(tmp_path)._render_paste_html(draft)
    body = out.split('<div id="copy-body">')[1]
    assert 'src="data:image/png;base64,' in body      # 파일 있는 건 임베드
    assert "[이미지" in body                            # 파일 없는 건 자리표시자

    # 두 번째 소제목 뒤에 이미지가 오는지(자리 정확도)
    i_h2 = body.index("둘째")
    i_img = body.index('src="data:image/png')
    assert i_img > i_h2


def test_missing_image_file_degrades_to_placeholder(tmp_path):
    from nbpipe.models import ImagePrompt, PostDraft
    from nbpipe.output.draft_writer import DraftWriter
    draft = PostDraft(
        niche=Niche.ECONOMY, primary_keyword="금리", title="t",
        body_markdown="## 첫째\n\n가.\n",
        image_prompts=[ImagePrompt(position="소제목1 아래", alt="x", prompt="y",
                                   file="없는경로/nope.png")],
    )
    out = DraftWriter(tmp_path)._render_paste_html(draft)
    assert "data:image" not in out     # 없는 파일로 깨진 <img> 를 만들지 않는다
    assert "[이미지" in out
