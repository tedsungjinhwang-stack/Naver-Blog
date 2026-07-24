"""여러 소스의 키워드를 병합·스코어링하고, 글감(TopicPlan)을 만든다.

스코어 = Σ(소스가중치 × 순위감쇠)
       + 교차소스 보너스 × (등장 소스 수 - 1)
       + 검색량 가중(있을 때)
       + 니치 관련 토큰 보너스
그리고 니치 제외어/최근 사용 키워드/길이 필터를 적용한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from nbpipe.models import Keyword, Niche, TopicPlan

_TOKEN_RE = re.compile(r"[가-힣a-zA-Z0-9]+")


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if len(t) >= 2]


def _rank_decay(rank: int | None) -> float:
    if rank is None:
        return 0.7
    return 1.0 / (1.0 + 0.08 * max(0, rank))


@dataclass
class MergedKeyword:
    term: str
    sources: set[str] = field(default_factory=set)
    best_rank: int | None = None
    search_volume: int | None = None
    score: float = 0.0
    meta: dict[str, Any] = field(default_factory=dict)


def merge_keywords(keywords: Iterable[Keyword]) -> dict[str, MergedKeyword]:
    """정규화 term 기준으로 병합."""
    merged: dict[str, MergedKeyword] = {}
    for kw in keywords:
        key = kw.normalized()
        if not key:
            continue
        m = merged.get(key)
        if m is None:
            m = MergedKeyword(term=kw.term.strip())
            merged[key] = m
        m.sources.add(kw.source)
        if kw.rank is not None:
            m.best_rank = kw.rank if m.best_rank is None else min(m.best_rank, kw.rank)
        if kw.search_volume is not None:
            m.search_volume = max(m.search_volume or 0, kw.search_volume)
    return merged


class KeywordSelector:
    def __init__(self, config: Any) -> None:
        self.config = config
        ks = getattr(config, "keyword_selection", {}) or {}
        self.source_weight: dict[str, float] = ks.get("source_weight", {})
        self.cross_bonus: float = ks.get("cross_source_bonus", 0.25)
        self.volume_weight: float = ks.get("volume_weight", 0.5)
        self.niche_bonus: float = ks.get("niche_bonus", 0.4)
        self.max_keywords: int = ks.get("max_keywords_per_topic", 12)

    def score(
        self,
        merged: dict[str, MergedKeyword],
        raw: list[Keyword],
        niche_tokens: set[str],
    ) -> list[MergedKeyword]:
        # 소스별 순위감쇠 가중치를 term 별로 누적
        by_term_source_rank: dict[str, dict[str, int | None]] = {}
        for kw in raw:
            key = kw.normalized()
            slot = by_term_source_rank.setdefault(key, {})
            if kw.source not in slot or (
                kw.rank is not None
                and (slot[kw.source] is None or kw.rank < slot[kw.source])
            ):
                slot[kw.source] = kw.rank

        for key, m in merged.items():
            s = 0.0
            for source, rank in by_term_source_rank.get(key, {}).items():
                s += self.source_weight.get(source, 0.5) * _rank_decay(rank)
            # 교차 소스 보너스
            s += self.cross_bonus * (len(m.sources) - 1)
            # 검색량 가중(0~100 스케일 가정)
            if m.search_volume:
                s += self.volume_weight * min(m.search_volume, 200) / 100.0
            # 니치 관련 토큰 보너스
            if niche_tokens & set(_tokens(m.term)):
                s += self.niche_bonus
            m.score = round(s, 4)
        return sorted(merged.values(), key=lambda x: x.score, reverse=True)

    def select(
        self,
        keywords: list[Keyword],
        niche: Niche,
        *,
        include_tokens: Iterable[str] = (),
        exclude_terms: Iterable[str] = (),
        recent_terms: Iterable[str] = (),
        limit: int | None = None,
    ) -> list[MergedKeyword]:
        exclude = {e.strip().lower() for e in exclude_terms if e.strip()}
        recent = {r.strip().lower() for r in recent_terms if r.strip()}
        # include_tokens 도 term 과 동일하게 토큰화해야 교집합 매칭이 된다
        # (멀티워드 "미국 증시" 를 통째로 두면 term 토큰 {미국,증시,...} 과 절대 안 겹침)
        niche_tokens = set(_tokens(niche.korean))
        for tok in include_tokens:
            niche_tokens |= set(_tokens(tok))

        merged = merge_keywords(keywords)
        # 필터: 길이/제외어/최근 사용
        filtered: dict[str, MergedKeyword] = {}
        for key, m in merged.items():
            low = m.term.lower()
            if len(m.term.strip()) < 2:
                continue
            if len(m.term) > 40:
                continue
            if any(x in low for x in exclude):
                continue
            if low in recent:
                m.meta["recently_used"] = True  # 참고용, 제외
                continue
            filtered[key] = m

        ranked = self.score(filtered, keywords, niche_tokens)
        lim = limit if limit is not None else self.max_keywords
        return ranked[:lim]

    def build_topic_plans(
        self,
        ranked: list[MergedKeyword],
        niche: Niche,
        *,
        count: int,
        seeds: list[str] | None = None,
        secondary_per_plan: int = 5,
    ) -> list[TopicPlan]:
        """상위 키워드를 primary 로, 토큰이 겹치는 키워드를 secondary 로 묶어 글감 생성."""
        plans: list[TopicPlan] = []
        used_as_primary: set[str] = set()
        pool = list(ranked)

        for m in pool:
            if len(plans) >= count:
                break
            key = m.term.lower()
            if key in used_as_primary:
                continue
            used_as_primary.add(key)

            primary_tokens = set(_tokens(m.term))
            secondaries: list[str] = []
            for other in pool:
                if other.term.lower() == key:
                    continue
                if len(secondaries) >= secondary_per_plan:
                    break
                if primary_tokens & set(_tokens(other.term)):
                    secondaries.append(other.term)
            # 부족하면 상위 키워드로 채움
            if len(secondaries) < secondary_per_plan:
                for other in pool:
                    if len(secondaries) >= secondary_per_plan:
                        break
                    if other.term.lower() == key or other.term in secondaries:
                        continue
                    secondaries.append(other.term)

            plans.append(
                TopicPlan(
                    niche=niche,
                    primary_keyword=m.term,
                    secondary_keywords=secondaries,
                    seed_topic=(seeds[0] if seeds else None),
                    rationale=(
                        f"score={m.score}, sources={sorted(m.sources)}, "
                        f"vol={m.search_volume}"
                    ),
                    keywords=[
                        Keyword(term=m.term, source="+".join(sorted(m.sources)),
                                score=m.score, search_volume=m.search_volume)
                    ],
                )
            )
        return plans
