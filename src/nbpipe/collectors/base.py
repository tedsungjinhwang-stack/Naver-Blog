"""수집기 공통 베이스."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any

import requests

from nbpipe.models import Keyword, Niche

# 네이버는 봇 UA 를 차단하므로 일반 브라우저처럼 보이게 한다.
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}


class Collector(ABC):
    """키워드 수집기 인터페이스."""

    name: str = "base"

    def __init__(self, config: Any, secrets: Any | None = None) -> None:
        self.config = config
        self.secrets = secrets
        cc = getattr(config, "collectors", {}) or {}
        self.timeout: float = cc.get("timeout_sec", 8)
        self.delay: float = cc.get("request_delay_sec", 0.7)
        self._session: requests.Session | None = None

    # --- 하위 클래스가 구현 ---
    @abstractmethod
    def collect(self, seeds: list[str], niche: Niche) -> list[Keyword]:
        """seeds(사용자 주제)를 시작점으로 키워드 후보를 반환."""

    # --- 공통 유틸 ---
    def available(self) -> bool:
        """의존성/키가 갖춰져 실행 가능한지."""
        return True

    @property
    def session(self) -> requests.Session:
        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update(DEFAULT_HEADERS)
        return self._session

    def _sleep(self) -> None:
        if self.delay and self.delay > 0:
            time.sleep(self.delay)

    def _get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        resp = self.session.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def _get_text(self, url: str, params: dict[str, Any] | None = None) -> str:
        resp = self.session.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.text
