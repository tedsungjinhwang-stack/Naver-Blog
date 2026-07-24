"""네이버 DataLab 검색어 트렌드 수집기 / 보정기.

공식 오픈API(openapi.naver.com/v1/datalab/search). NAVER_CLIENT_ID/SECRET 필요.

DataLab 은 '상대 검색량 비율(0~100)'만 제공하며, 그 비율은 **한 요청 안의
키워드들끼리만** 정규화되어 비교 가능하다. 따라서 여러 배치에 걸쳐 많은
키워드를 비교하려면 매 배치에 공통 '앵커 키워드'를 넣어 앵커=100 기준으로
재정규화한다(anchor normalization).

역할:
  - collect(): 시드 자체의 상대 검색량 부여(발굴보다는 보정 성격)
  - score_terms(): 임의 후보 키워드 목록에 앵커 정규화 검색량을 매김 → 선정 가중치
"""
from __future__ import annotations

from datetime import date, timedelta
from statistics import mean
from typing import Any

from nbpipe.collectors.base import Collector
from nbpipe.models import Keyword, Niche

_DATALAB_URL = "https://openapi.naver.com/v1/datalab/search"
_MAX_GROUPS = 5  # API 요청당 최대 키워드 그룹 수


class NaverDataLabCollector(Collector):
    name = "naver_datalab"

    def available(self) -> bool:
        return bool(self.secrets and getattr(self.secrets, "has_naver", False))

    def _headers(self) -> dict[str, str]:
        return {
            "X-Naver-Client-Id": self.secrets.naver_client_id,
            "X-Naver-Client-Secret": self.secrets.naver_client_secret,
            "Content-Type": "application/json",
        }

    def _period(self) -> tuple[str, str]:
        end = date.today() - timedelta(days=1)
        start = end - timedelta(days=90)
        return start.isoformat(), end.isoformat()

    def _request_ratios(self, terms: list[str]) -> dict[str, float]:
        """<=5개 키워드의 기간 평균 ratio 를 반환(요청 내부 정규화 값).

        groupName 은 짧은 색인명(g0..)으로 두고, 응답의 원본 키워드(res['keywords'][0])
        로 매핑한다. (groupName 을 term 으로 쓰면 길이 제한으로 잘려 매칭이 깨진다.)
        """
        if not terms:
            return {}
        start, end = self._period()
        batch = terms[:_MAX_GROUPS]
        groups = [{"groupName": f"g{i}", "keywords": [t]} for i, t in enumerate(batch)]
        payload = {
            "startDate": start,
            "endDate": end,
            "timeUnit": "week",
            "keywordGroups": groups,
        }
        try:
            resp = self.session.post(
                _DATALAB_URL, json=payload, headers=self._headers(),
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            return {}

        results = data.get("results", []) or []
        out: dict[str, float] = {}
        for i, res in enumerate(results):
            # 원본 키워드로 키를 잡는다(응답 keywords[0] > 순서 매핑 > title 순).
            kws = res.get("keywords") or []
            term = kws[0] if kws else (batch[i] if i < len(batch) else res.get("title"))
            points = [p.get("ratio", 0.0) for p in res.get("data", []) or []]
            out[term] = mean(points) if points else 0.0
        return out

    def score_terms(
        self, terms: list[str], anchor: str | None = None
    ) -> dict[str, float]:
        """앵커 정규화된 상대 검색량(앵커=100)을 반환."""
        terms = [t for t in dict.fromkeys(t.strip() for t in terms) if t]
        if not terms:
            return {}
        anchor = anchor or terms[0]
        others = [t for t in terms if t != anchor]

        normalized: dict[str, float] = {}
        # 앵커 단독 기준값 확보를 위해 앵커를 매 배치에 포함
        for i in range(0, max(1, len(others)), _MAX_GROUPS - 1):
            batch = [anchor, *others[i : i + (_MAX_GROUPS - 1)]]
            ratios = self._request_ratios(batch)
            anchor_val = ratios.get(anchor, 0.0)
            self._sleep()
            if anchor_val <= 0:
                # 앵커 데이터가 없으면 요청 내부 최댓값으로 대체 정규화
                base = max(ratios.values(), default=0.0) or 1.0
            else:
                base = anchor_val
            for term, val in ratios.items():
                if term == anchor:
                    continue
                normalized[term] = round(val / base * 100.0, 2)
        normalized[anchor] = 100.0
        return normalized

    def enrich(self, keywords: list[Keyword], anchor: str | None = None) -> None:
        """후보 키워드들에 상대 검색량을 in-place 로 부여."""
        if not self.available() or not keywords:
            return
        terms = [k.term for k in keywords]
        scores = self.score_terms(terms, anchor=anchor)
        for k in keywords:
            vol = scores.get(k.term)
            if vol is not None:
                k.search_volume = int(vol)
                k.meta["datalab_ratio"] = vol

    def collect(self, seeds: list[str], niche: Niche) -> list[Keyword]:
        if not self.available():
            return []
        seeds = [s.strip() for s in seeds if s.strip()]
        scores = self.score_terms(seeds)
        out: list[Keyword] = []
        for i, term in enumerate(seeds):
            out.append(
                Keyword(
                    term=term,
                    source=self.name,
                    rank=i,
                    search_volume=int(scores.get(term, 0)),
                    meta={"datalab_ratio": scores.get(term, 0.0)},
                )
            )
        return out
