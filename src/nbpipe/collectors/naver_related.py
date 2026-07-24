"""네이버 연관검색어 수집기.

⚠️ 네이버는 2026-04-30 '연관검색어' 서비스를 종료(AI 브리핑으로 대체)했다.
따라서 이 수집기는 기본 off 이며, 남겨둔 이유는 (1) 구버전 지면이 남아있는
일부 케이스, (2) 향후 스마트블록 세부주제 크롤러로 대체할 자리표시자 목적이다.
공식 API 가 아니므로 best-effort: 못 찾으면 조용히 [] 반환한다.
"""
from __future__ import annotations

from nbpipe.collectors.base import Collector
from nbpipe.models import Keyword, Niche

try:
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover
    BeautifulSoup = None  # type: ignore

_SEARCH_URL = "https://search.naver.com/search.naver"

# 연관검색어가 등장하는 대표 선택자 후보들(네이버 마크업 변경 대비 다중 시도).
_SELECTORS = [
    ".related_srch .keyword",
    ".lst_related_srch .item .keyword",
    ".related_srch a.keyword",
    "div.related_srch li a",
    "._related_keyword_list a",
]


class NaverRelatedCollector(Collector):
    name = "naver_related"

    def available(self) -> bool:
        return BeautifulSoup is not None

    def _query_one(self, query: str) -> list[str]:
        if BeautifulSoup is None:
            return []
        try:
            html = self._get_text(_SEARCH_URL, params={"query": query})
        except Exception:
            return []

        soup = BeautifulSoup(html, "html.parser")
        found: list[str] = []
        for sel in _SELECTORS:
            for node in soup.select(sel):
                text = node.get_text(strip=True)
                if text:
                    found.append(text)
            if found:
                break
        # 중복 제거(순서 유지)
        seen: set[str] = set()
        uniq: list[str] = []
        for t in found:
            if t.lower() not in seen:
                seen.add(t.lower())
                uniq.append(t)
        return uniq

    def collect(self, seeds: list[str], niche: Niche) -> list[Keyword]:
        if not self.available():
            return []
        seen: dict[str, Keyword] = {}
        for seed in (s.strip() for s in seeds if s.strip()):
            for rank, term in enumerate(self._query_one(seed)):
                key = term.lower()
                if key not in seen:
                    seen[key] = Keyword(
                        term=term, source=self.name, rank=rank,
                        meta={"seed": seed},
                    )
            self._sleep()
        return list(seen.values())
