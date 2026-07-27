"""설정 로딩.

우선순위: 환경변수(.env) > config/config.yaml > 내장 기본값.
비밀키(ANTHROPIC_API_KEY 등)는 오직 환경변수에서만 읽는다.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "PyYAML 이 필요합니다. `pip install -r requirements.txt` 를 실행하세요."
    ) from exc

try:
    from dotenv import load_dotenv
except ImportError:  # dotenv 는 선택 — 없으면 조용히 skip
    def load_dotenv(*_a: Any, **_k: Any) -> bool:  # type: ignore
        return False


# 저장소 루트: src/nbpipe/config.py → 부모 3단계
ROOT = Path(__file__).resolve().parents[2]

_DEFAULTS: dict[str, Any] = {
    "collectors": {
        "seed_topics": True,
        "naver_autocomplete": True,
        "naver_related": False,   # 네이버 연관검색어 2026-04-30 종료 → 기본 off
        "naver_datalab": False,
        "google_trends": False,
        "request_delay_sec": 0.7,
        "timeout_sec": 8,
        "autocomplete_depth": 1,
    },
    "keyword_selection": {
        "max_keywords_per_topic": 12,
        "source_weight": {
            "seed_topics": 1.0,
            "naver_datalab": 1.0,
            "naver_autocomplete": 0.9,
            "naver_related": 0.85,
            "google_trends": 0.7,
        },
        "cross_source_bonus": 0.25,
    },
    "seo": {
        "title_len_min": 12,
        "title_len_max": 30,          # 모바일 잘림 방지(리서치: 25자 이내 권장)
        "body_char_min": 1700,        # 검색형 하한. 홈피드형은 2,000자+ 권장(intent별 상향)
        "min_headings": 3,            # 소제목 2~4개 + 목차
        "min_images": 6,              # 리서치: 6~13장(검색형 최소 3~5장)
        "tags_min": 5,
        "tags_max": 10,
        "primary_keyword_min_count": 3,
        "primary_keyword_max_count": 6,   # 6회 초과 시 스터핑 경고
        "pass_score": 70,
    },
    "output": {
        "dir": "./output",
        # markdown=검토용, html=미리보기, naver_text=평문(.naver.txt),
        # paste_html=서식 유지 붙여넣기용(.paste.html)
        "formats": ["markdown", "html", "naver_text", "paste_html"],
        "write_run_log": True,
    },
    # 작성 어투 규칙(빈 값이면 prompts.DEFAULT_VOICE_RULE 사용)
    "writing": {
        "voice_rule": "",
    },
    # 이미지 자동 수집 (ingest 시 라이선스 안전한 스톡 이미지를 함께 받아둔다)
    "images": {
        "enabled": True,
        "source": "openverse",   # openverse(키 불필요) / pexels / unsplash
        "per_post": 2,           # 스톡 장수. 나머지는 직접 제작/촬영으로 채운다
        "license": None,         # 예: "cc0,pdm" (출처표기 의무 없는 것만)
        "allow_sharealike": False,
        "dir": "",               # 비우면 <output_dir>/images
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


@dataclass
class Secrets:
    anthropic_api_key: str | None = None
    naver_client_id: str | None = None
    naver_client_secret: str | None = None

    @property
    def has_anthropic(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def has_naver(self) -> bool:
        return bool(self.naver_client_id and self.naver_client_secret)


@dataclass
class Config:
    data: dict[str, Any] = field(default_factory=dict)
    secrets: Secrets = field(default_factory=Secrets)
    root: Path = ROOT

    # --- 섹션 접근자 ---
    @property
    def collectors(self) -> dict[str, Any]:
        return self.data["collectors"]

    @property
    def keyword_selection(self) -> dict[str, Any]:
        return self.data["keyword_selection"]

    @property
    def seo(self) -> dict[str, Any]:
        return self.data["seo"]

    @property
    def output(self) -> dict[str, Any]:
        return self.data["output"]

    @property
    def writing(self) -> dict[str, Any]:
        return self.data.get("writing", {})

    @property
    def images(self) -> dict[str, Any]:
        return self.data.get("images", {})

    @property
    def images_dir(self) -> Path:
        raw = (self.images.get("dir") or "").strip()
        if raw:
            p = Path(raw).expanduser()
            return p if p.is_absolute() else (self.root / p)
        return self.output_dir / "images"

    @property
    def output_dir(self) -> Path:
        env = os.environ.get("NBPIPE_OUTPUT_DIR")
        raw = env or self.output.get("dir", "./output")
        p = Path(raw)
        return p if p.is_absolute() else (self.root / p)

    def get(self, *path: str, default: Any = None) -> Any:
        cur: Any = self.data
        for key in path:
            if not isinstance(cur, dict) or key not in cur:
                return default
            cur = cur[key]
        return cur


def load_config(config_path: str | Path | None = None) -> Config:
    """설정 + 비밀키를 로드한다.

    config_path 미지정 시 config/config.yaml → 없으면 config/config.example.yaml.
    """
    load_dotenv(ROOT / ".env")

    if config_path is None:
        candidate = ROOT / "config" / "config.yaml"
        if not candidate.exists():
            candidate = ROOT / "config" / "config.example.yaml"
        config_path = candidate
    config_path = Path(config_path)

    user_cfg: dict[str, Any] = {}
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as fh:
            user_cfg = yaml.safe_load(fh) or {}

    merged = _deep_merge(_DEFAULTS, user_cfg)

    secrets = Secrets(
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
        naver_client_id=os.environ.get("NAVER_CLIENT_ID"),
        naver_client_secret=os.environ.get("NAVER_CLIENT_SECRET"),
    )
    return Config(data=merged, secrets=secrets)
