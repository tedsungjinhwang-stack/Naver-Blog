"""시드 주제 수집기.

사용자가 지정한 주제(니치 yaml 의 seed_topics 또는 CLI 인자)를 그대로
키워드 후보로 변환한다. 가장 신뢰도 높은 소스(source_weight=1.0).
"""
from __future__ import annotations

from nbpipe.collectors.base import Collector
from nbpipe.models import Keyword, Niche


class SeedTopicsCollector(Collector):
    name = "seed_topics"

    def collect(self, seeds: list[str], niche: Niche) -> list[Keyword]:
        out: list[Keyword] = []
        for i, term in enumerate(seeds):
            term = term.strip()
            if not term:
                continue
            out.append(
                Keyword(
                    term=term,
                    source=self.name,
                    rank=i,
                    meta={"niche": niche.value, "seed": True},
                )
            )
        return out
