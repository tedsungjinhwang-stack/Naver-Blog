"""니치별 설정(niches/*.yaml) 로더.

각 니치 파일은 시드 주제, 관련 토큰(선정 보너스), 제외어, 콘텐츠 앵글을 담는다.
사용자는 niches/<niche>.yaml 의 seed_topics 를 자유롭게 바꿔 자기 주제를 넣는다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from nbpipe.models import Niche


@dataclass
class NicheConfig:
    niche: Niche
    seed_topics: list[str] = field(default_factory=list)
    include_tokens: list[str] = field(default_factory=list)
    exclude_terms: list[str] = field(default_factory=list)
    angles: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, niche: Niche, data: dict[str, Any]) -> "NicheConfig":
        return cls(
            niche=niche,
            seed_topics=[str(s) for s in (data.get("seed_topics") or [])],
            include_tokens=[str(s) for s in (data.get("include_tokens") or [])],
            exclude_terms=[str(s) for s in (data.get("exclude_terms") or [])],
            angles=[str(s) for s in (data.get("angles") or [])],
        )


def load_niche_config(niche: Niche, root: Path) -> NicheConfig:
    path = Path(root) / "niches" / f"{niche.value}.yaml"
    if not path.exists():
        return NicheConfig(niche=niche)
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return NicheConfig.from_dict(niche, data)
