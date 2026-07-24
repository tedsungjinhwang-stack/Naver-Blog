from nbpipe.models import Intent, Niche, PostDraft


def test_niche_from_str_aliases():
    assert Niche.from_str("경제") is Niche.ECONOMY
    assert Niche.from_str("주식") is Niche.INVESTING
    assert Niche.from_str("investing") is Niche.INVESTING
    assert Niche.from_str("부동산") is Niche.REALESTATE
    assert Niche.REALESTATE.korean == "부동산"


def test_niche_from_str_invalid():
    import pytest
    with pytest.raises(ValueError):
        Niche.from_str("연예")


def test_intent_from_str_and_window():
    assert Intent.from_str("홈판") is Intent.HOMEFEED
    assert Intent.from_str("search") is Intent.SEARCH
    assert "저녁" in Intent.HOMEFEED.publish_window()
    assert "오전" in Intent.SEARCH.publish_window()


def test_postdraft_char_count_and_slug():
    d = PostDraft(
        niche=Niche.ECONOMY, primary_keyword="기준 금리",
        title="t", body_markdown="가 나 다\n라마바",
    )
    assert d.char_count() == 6  # 공백/개행 제외
    assert d.slug().startswith("기준")
    assert " " not in d.slug()
