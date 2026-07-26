"""라이선스가 명확한 무료 이미지 검색·다운로드.

라이선스 정책(중요):
  네이버 블로그에 애드포스트 등 수익화를 붙이면 '상업적 이용'에 해당한다.
  따라서 NC(비영리 전용)는 제외한다. 크롭·리사이즈가 필요하므로 ND(변경금지)도
  제외한다. BY-SA는 2차적 저작물에 동일 라이선스를 요구해 해석이 번거로우므로
  기본 제외하고 옵션으로만 포함한다.
  → 기본 수집 대상: CC0 / PDM (표기 의무 없음), BY (표기 필수)

소스:
  openverse : API 키 불필요 (기본)
  pexels    : PEXELS_API_KEY 필요
  unsplash  : UNSPLASH_ACCESS_KEY 필요
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse

import requests

from nbpipe.models import FetchedImage, Niche

UA = "nbpipe-image-fetcher/1.0 (personal blog research)"
TIMEOUT = 30

_ALLOWED_CC = {"cc0", "pdm", "by"}
_SHAREALIKE = {"by-sa"}


def _slug(text: str, limit: int = 40) -> str:
    s = re.sub(r"[^\w가-힣]+", "_", (text or "").strip().lower()).strip("_")
    return s[:limit] or "image"


class ImageFetcher:
    """검색 → 다운로드 → 출처 기록."""

    def __init__(
        self,
        source: str = "openverse",
        *,
        license_filter: str | None = None,
        allow_sharealike: bool = False,
        timeout: int = TIMEOUT,
    ) -> None:
        self.source = source
        self.license_filter = license_filter
        self.allow_sharealike = allow_sharealike
        self.timeout = timeout

    # ---- 검색 ----
    def search(self, query: str, count: int) -> list[FetchedImage]:
        fn = {
            "openverse": self._search_openverse,
            "pexels": self._search_pexels,
            "unsplash": self._search_unsplash,
        }.get(self.source)
        if fn is None:
            raise ValueError(f"지원하지 않는 이미지 소스: {self.source}")
        return fn(query, count)

    def _search_openverse(self, query: str, count: int) -> list[FetchedImage]:
        params: dict[str, object] = {
            "q": query,
            "page_size": max(count * 4, 12),   # 라이선스 필터링 여유분
            "mature": "false",
        }
        if self.license_filter:
            params["license"] = self.license_filter
        else:
            params["license_type"] = "commercial,modification"
        r = requests.get("https://api.openverse.org/v1/images/", params=params,
                         headers={"User-Agent": UA}, timeout=self.timeout)
        r.raise_for_status()
        allowed = _ALLOWED_CC | (_SHAREALIKE if self.allow_sharealike else set())
        out: list[FetchedImage] = []
        for it in r.json().get("results", []):
            code = (it.get("license") or "").lower()
            if code not in allowed or not it.get("url"):
                continue
            out.append(FetchedImage(
                title=it.get("title") or query,
                url=it["url"],
                page_url=it.get("foreign_landing_url") or "",
                creator=it.get("creator") or "",
                license_code=code,
                license_url=it.get("license_url") or "",
                source=it.get("provider") or "openverse",
                query=query,
            ))
            if len(out) >= count:
                break
        return out

    def _search_pexels(self, query: str, count: int) -> list[FetchedImage]:
        key = os.getenv("PEXELS_API_KEY")
        if not key:
            raise RuntimeError("PEXELS_API_KEY 가 필요합니다 (.env 참고).")
        r = requests.get("https://api.pexels.com/v1/search",
                         params={"query": query, "per_page": count},
                         headers={"User-Agent": UA, "Authorization": key},
                         timeout=self.timeout)
        r.raise_for_status()
        out = []
        for p in r.json().get("photos", []):
            src = p.get("src", {})
            out.append(FetchedImage(
                title=p.get("alt") or query,
                url=src.get("large2x") or src.get("large") or src.get("original", ""),
                page_url=p.get("url") or "",
                creator=p.get("photographer") or "",
                license_code="pexels",
                license_url="https://www.pexels.com/license/",
                source="pexels",
                query=query,
            ))
        return out

    def _search_unsplash(self, query: str, count: int) -> list[FetchedImage]:
        key = os.getenv("UNSPLASH_ACCESS_KEY")
        if not key:
            raise RuntimeError("UNSPLASH_ACCESS_KEY 가 필요합니다 (.env 참고).")
        r = requests.get("https://api.unsplash.com/search/photos",
                         params={"query": query, "per_page": count},
                         headers={"User-Agent": UA,
                                  "Authorization": f"Client-ID {key}"},
                         timeout=self.timeout)
        r.raise_for_status()
        out = []
        for p in r.json().get("results", []):
            out.append(FetchedImage(
                title=p.get("description") or p.get("alt_description") or query,
                url=(p.get("urls") or {}).get("regular", ""),
                page_url=(p.get("links") or {}).get("html", ""),
                creator=((p.get("user") or {}).get("name")) or "",
                license_code="unsplash",
                license_url="https://unsplash.com/license",
                source="unsplash",
                query=query,
            ))
        return out

    # ---- 다운로드 ----
    def download(self, img: FetchedImage, dest: Path, stem: str) -> bool:
        try:
            r = requests.get(img.url, headers={"User-Agent": UA},
                             timeout=self.timeout, stream=True)
            r.raise_for_status()
        except Exception:
            return False   # 429/403 등은 조용히 건너뛴다(다음 후보로)
        ext = Path(urlparse(img.url).path).suffix.lower()
        if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
            ext = ".png" if "png" in r.headers.get("content-type", "") else ".jpg"
        dest.mkdir(parents=True, exist_ok=True)
        p = dest / f"{stem}{ext}"
        try:
            with open(p, "wb") as f:
                for chunk in r.iter_content(65536):
                    f.write(chunk)
        except Exception:
            return False
        img.file = p.name
        img.path = str(p)
        return True

    def collect(self, queries: list[str], dest: Path, want: int,
                stem_prefix: str = "img") -> list[FetchedImage]:
        """여러 검색어를 돌며 want 장이 찰 때까지 모은다."""
        got: list[FetchedImage] = []
        seen_urls: set[str] = set()
        for q in queries:
            if len(got) >= want:
                break
            try:
                candidates = self.search(q, want * 2)
            except Exception:
                continue
            for img in candidates:
                if len(got) >= want:
                    break
                if img.url in seen_urls:
                    continue
                seen_urls.add(img.url)
                stem = f"{stem_prefix}_{len(got) + 1:02d}_{_slug(q, 24)}"
                if self.download(img, dest, stem):
                    got.append(img)
        return got


def write_credits(images: list[FetchedImage], dest: Path) -> Path | None:
    """CREDITS.md(붙여넣을 출처 문구) + credits.json(메타) 누적 기록."""
    if not images:
        return None
    dest.mkdir(parents=True, exist_ok=True)
    credits = dest / "CREDITS.md"
    lines: list[str] = []
    if not credits.exists():
        lines += [
            "# 이미지 출처",
            "",
            "> BY 라이선스는 아래 문구를 본문 하단에 그대로 붙여 출처를 밝힌다.",
            "> CC0/PDM/Pexels/Unsplash 는 표기 의무가 없으나 기록은 남긴다.",
        ]
    lines.append("")
    for img in images:
        lines.append(f"- `{img.file}` — {img.credit_line()}")
    with open(credits, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    meta_path = dest / "credits.json"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        meta = []
    meta.extend(img.as_dict() for img in images)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    return credits


def fetch_for_draft(
    *,
    niche: Niche,
    keywords: list[str],
    dest: Path,
    count: int = 2,
    source: str = "openverse",
    license_filter: str | None = None,
    allow_sharealike: bool = False,
    stem_prefix: str = "img",
) -> list[FetchedImage]:
    """글 하나에 붙일 스톡 이미지를 수집한다. 실패해도 예외를 올리지 않는다."""
    from nbpipe.media.queries import queries_for

    if count <= 0:
        return []
    queries = queries_for(niche, keywords, limit=max(3, count + 1))
    fetcher = ImageFetcher(source, license_filter=license_filter,
                           allow_sharealike=allow_sharealike)
    try:
        images = fetcher.collect(queries, dest, count, stem_prefix=stem_prefix)
    except Exception:
        return []
    write_credits(images, dest)
    return images
