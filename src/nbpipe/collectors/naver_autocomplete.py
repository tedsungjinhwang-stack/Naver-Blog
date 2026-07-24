"""네이버 검색 자동완성 수집기.

공개 자동완성 엔드포인트(ac.search.naver.com)를 사용한다. API 키 불필요.
자동완성은 실제 사용자가 많이 검색하는 '롱테일 키워드'를 그대로 반영하므로
홈판/검색노출용 키워드 발굴에 특히 유용하다.

응답 예시(JSON):
    {"query":["아이폰"],
     "items":[[["아이폰15", ...], ["아이폰15 프로", ...], ...]]}
"""
from __future__ import annotations

import re

from nbpipe.collectors.base import Collector
from nbpipe.models import Keyword, Niche

_AC_URL = "https://ac.search.naver.com/nx/ac"
_TAG_RE = re.compile(r"<[^>]+>")


def _clean(text: str) -> str:
    return _TAG_RE.sub("", text).strip()


class NaverAutocompleteCollector(Collector):
    name = "naver_autocomplete"

    def _query_one(self, query: str) -> list[str]:
        params = {
            "q": query,
            "con": "0",
            "frm": "nv",
            "ans": "2",
            "r_format": "json",
            "r_enc": "UTF-8",
            "r_unicode": "0",
            "t_koreng": "1",
            "q_enc": "UTF-8",
            "st": "100",
        }
        try:
            data = self._get_json(_AC_URL, params=params)
        except Exception:
            return []

        results: list[str] = []
        for group in data.get("items", []) or []:
            if not isinstance(group, list):
                continue
            for entry in group:
                term = None
                if isinstance(entry, list) and entry:
                    first = entry[0]
                    if isinstance(first, str):
                        term = first
                    elif isinstance(first, list) and first and isinstance(first[0], str):
                        term = first[0]
                elif isinstance(entry, str):
                    term = entry
                if term:
                    cleaned = _clean(term)
                    if cleaned:
                        results.append(cleaned)
        return results

    def collect(self, seeds: list[str], niche: Niche) -> list[Keyword]:
        depth = int(getattr(self.config, "collectors", {}).get("autocomplete_depth", 1))
        seen: dict[str, Keyword] = {}
        frontier = [s.strip() for s in seeds if s.strip()]

        # 0단계: 시드 자동완성
        level1: list[str] = []
        for seed in frontier:
            for rank, term in enumerate(self._query_one(seed)):
                key = term.lower()
                level1.append(term)
                if key not in seen:
                    seen[key] = Keyword(
                        term=term, source=self.name, rank=rank,
                        meta={"seed": seed, "depth": 0},
                    )
            self._sleep()

        # 1단계: 각 자동완성 결과를 다시 자동완성(선택)
        if depth >= 1:
            for base in level1[: 30]:  # 폭주 방지 상한
                for rank, term in enumerate(self._query_one(base)):
                    key = term.lower()
                    if key not in seen:
                        seen[key] = Keyword(
                            term=term, source=self.name, rank=rank + 10,
                            meta={"seed": base, "depth": 1},
                        )
                self._sleep()

        return list(seen.values())
