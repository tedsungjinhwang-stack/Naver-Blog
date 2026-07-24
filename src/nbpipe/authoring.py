"""세션/수동 작성 경로.

Claude API 없이도 파이프라인을 쓸 수 있도록, 사람이(또는 이 세션의 Claude가)
직접 쓴 글을 파이프라인에 넣어 SEO·컴플라이언스 검수 + 초안 출력으로 이어준다.

작성 파일 포맷: YAML front-matter + Markdown 본문
--------------------------------------------------
    ---
    niche: economy            # 경제|투자|부업|부동산 (또는 영문 키)
    intent: homefeed          # homefeed|search (선택, 기본 homefeed)
    primary_keyword: 기준금리
    secondary_keywords: [금리 인하, 대출 금리]
    title: 기준금리 인하, 내 대출 이자 얼마나 줄까
    tags: [기준금리, 금리, 대출, 예금, 경제]
    summary: |
      기준금리가 내리면 뭐가 달라질까요? ...
    image_prompts:
      - position: 도입부 아래
        alt: 기준금리 추이 그래프
        prompt: 한국은행 기준금리 추이 캡처
    ---
    ## 첫 소제목
    본문...
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from nbpipe.models import ImagePrompt, Intent, Niche, PostDraft, TopicPlan

_FRONT_RE = re.compile(r"^\s*---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)
_H_RE = re.compile(r"^#{2,4}\s+(.+)$", re.MULTILINE)
_H1_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)


def split_front_matter(text: str) -> tuple[dict[str, Any], str]:
    """front-matter(dict) 와 본문(str) 으로 분리. front-matter 없으면 ({}, 전체)."""
    m = _FRONT_RE.match(text)
    if not m:
        return {}, text
    meta = yaml.safe_load(m.group(1)) or {}
    if not isinstance(meta, dict):
        meta = {}
    return meta, m.group(2)


def parse_authored_post(path: str | Path) -> PostDraft:
    """작성 파일 → PostDraft. 검수/출력 단계로 넘길 수 있게 채운다."""
    text = Path(path).read_text(encoding="utf-8")
    meta, body = split_front_matter(text)

    if not meta.get("niche"):
        raise ValueError("front-matter 에 'niche' 가 필요합니다 (경제|투자|부업|부동산).")
    niche = Niche.from_str(str(meta["niche"]))

    primary = str(meta.get("primary_keyword") or "").strip()
    if not primary:
        raise ValueError("front-matter 에 'primary_keyword' 가 필요합니다.")

    intent = Intent.from_str(str(meta.get("intent", "homefeed")))

    # 제목: front-matter > 본문 첫 # 헤딩 > 핵심 키워드
    title = str(meta.get("title") or "").strip()
    if not title:
        h1 = _H1_RE.search(body)
        title = h1.group(1).strip() if h1 else primary

    # 소제목: front-matter > 본문 ## 헤딩 자동추출
    subtitles = [str(s) for s in (meta.get("subtitles") or [])]
    if not subtitles:
        subtitles = [h.strip() for h in _H_RE.findall(body)]

    image_prompts = [
        ImagePrompt(
            position=str(im.get("position", "")),
            alt=str(im.get("alt", "")),
            prompt=str(im.get("prompt", "")),
            caption=str(im.get("caption", "")),
        )
        for im in (meta.get("image_prompts") or [])
        if isinstance(im, dict)
    ]

    secondary = [str(s) for s in (meta.get("secondary_keywords") or [])]

    return PostDraft(
        niche=niche,
        primary_keyword=primary,
        title=title,
        intent=intent,
        subtitles=subtitles,
        body_markdown=body.strip(),
        tags=[str(t).lstrip("#").strip() for t in (meta.get("tags") or []) if str(t).strip()],
        image_prompts=image_prompts,
        summary=str(meta.get("summary") or "").strip(),
        meta={
            "source": "authored",
            "secondary_keywords": secondary,
            "author": meta.get("author", "session"),
        },
    )


def render_brief(plan: TopicPlan, seo_cfg: dict[str, Any], style_ref: str = "") -> str:
    """세션/사람이 글을 쓸 수 있게 '작성 브리핑 + 채우기 템플릿'을 만든다.

    style_ref: knowledge/style_reference.md(레퍼런스 톤앤매너 가이드) 내용을 넣으면
    브리핑 상단 가이드에 함께 주입된다. 반환 문자열을 파일로 저장 → 본문만 채우면
    곧바로 ingest 가능.
    """
    from nbpipe.generation.prompts import build_system_prompt  # 지연 import(순환 방지)

    body_min = seo_cfg.get("body_char_min", 1700)
    if plan.intent == Intent.HOMEFEED:
        body_min = max(body_min, 2000)

    rules = build_system_prompt(plan.niche, seo_cfg, plan.intent)
    if style_ref.strip():
        rules = rules + "\n\n[레퍼런스 톤앤매너 가이드]\n" + style_ref.strip()
    fm = {
        "niche": plan.niche.value,
        "intent": plan.intent.value,
        "primary_keyword": plan.primary_keyword,
        "secondary_keywords": plan.secondary_keywords,
        "title": "",
        "tags": [],
        "summary": "",
        "image_prompts": [
            {"position": "도입부 아래", "alt": "", "prompt": ""},
        ],
    }
    front = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).strip()

    guide = "\n".join(f"# {ln}" for ln in rules.splitlines())
    return (
        f"{guide}\n"
        f"#\n# ↑ 작성 가이드(주석). 아래 front-matter 의 빈 칸(title/tags/summary/image_prompts)을\n"
        f"#   채우고, '## 소제목' 아래에 본문을 {body_min:,}자 이상 작성하세요.\n"
        f"#   완성 후:  nbpipe ingest <이 파일>\n\n"
        f"---\n{front}\n---\n\n"
        f"## (소제목1)\n\n\n## (소제목2)\n\n\n## (소제목3)\n\n"
    )
