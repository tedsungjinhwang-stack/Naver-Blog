"""구글 트렌드 수집기 (pytrends).

관련검색어(rising/top)로 급상승 이슈성 키워드를 발굴한다. pytrends 는
비공식 라이브러리라 rate-limit/차단이 잦다 → 실패 시 조용히 [] 반환.
`pip install pytrends` 필요. geo=KR, hl=ko.
"""
from __future__ import annotations

from nbpipe.collectors.base import Collector
from nbpipe.models import Keyword, Niche


class GoogleTrendsCollector(Collector):
    name = "google_trends"

    def available(self) -> bool:
        try:
            import pytrends  # noqa: F401
            return True
        except ImportError:
            return False

    def collect(self, seeds: list[str], niche: Niche) -> list[Keyword]:
        if not self.available():
            return []
        try:
            from pytrends.request import TrendReq
        except ImportError:
            return []

        try:
            pytrends = TrendReq(hl="ko-KR", tz=540, timeout=(self.timeout, self.timeout))
        except Exception:
            return []

        seen: dict[str, Keyword] = {}
        for seed in (s.strip() for s in seeds if s.strip()):
            try:
                pytrends.build_payload([seed], geo="KR", timeframe="today 3-m")
                related = pytrends.related_queries()
            except Exception:
                self._sleep()
                continue

            block = related.get(seed) or {}
            for kind in ("rising", "top"):
                df = block.get(kind)
                if df is None or getattr(df, "empty", True):
                    continue
                for _, row in df.iterrows():
                    term = str(row.get("query", "")).strip()
                    if not term:
                        continue
                    key = term.lower()
                    value = row.get("value")
                    if key not in seen:
                        seen[key] = Keyword(
                            term=term,
                            source=self.name,
                            search_volume=int(value) if kind == "top" and value else None,
                            meta={"seed": seed, "kind": kind, "value": value},
                        )
                    elif kind == "top" and value and seen[key].search_volume is None:
                        # rising 으로 먼저 등록됐던 항목에 top 의 실제 수치를 보강
                        seen[key].search_volume = int(value)
            self._sleep()
        return list(seen.values())
