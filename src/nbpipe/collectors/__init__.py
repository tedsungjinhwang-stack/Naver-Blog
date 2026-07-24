"""키워드 수집기 모음."""
from nbpipe.collectors.base import Collector
from nbpipe.collectors.google_trends import GoogleTrendsCollector
from nbpipe.collectors.naver_autocomplete import NaverAutocompleteCollector
from nbpipe.collectors.naver_datalab import NaverDataLabCollector
from nbpipe.collectors.naver_related import NaverRelatedCollector
from nbpipe.collectors.seed_topics import SeedTopicsCollector

# 수집기 레지스트리: config.collectors 의 토글 키와 1:1 대응
DISCOVERY_COLLECTORS: dict[str, type[Collector]] = {
    "seed_topics": SeedTopicsCollector,
    "naver_autocomplete": NaverAutocompleteCollector,
    "naver_related": NaverRelatedCollector,
    "google_trends": GoogleTrendsCollector,
}

__all__ = [
    "Collector",
    "SeedTopicsCollector",
    "NaverAutocompleteCollector",
    "NaverRelatedCollector",
    "NaverDataLabCollector",
    "GoogleTrendsCollector",
    "DISCOVERY_COLLECTORS",
]
