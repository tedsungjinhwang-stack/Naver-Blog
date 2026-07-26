#!/usr/bin/env python3
"""라이선스가 명확한 무료 이미지 검색·다운로드 + 출처 표기 자동 생성.

지원 소스 (기본은 API 키 불필요):
  - openverse : CC0/PDM/BY 등 라이선스별 필터 가능. 키 불필요.
  - pexels    : Pexels License(상업적 이용 무료). PEXELS_API_KEY 있으면 사용.
  - unsplash  : Unsplash License. UNSPLASH_ACCESS_KEY 필요.

라이선스 정책(중요):
  네이버 블로그에 애드포스트 등 수익화를 붙이면 '상업적 이용'에 해당한다.
  따라서 NC(비영리 전용)는 제외한다. 또한 크롭·리사이즈가 필요하므로
  ND(변경금지)도 제외한다. 기본값은 상업적 이용 + 변경 허용 조합만 가져온다.

사용:
  python3 tools/fetch_images.py "stock market chart" -n 3
  python3 tools/fetch_images.py "동전 돈" -n 2 --license cc0     # 출처표기 의무 없는 것만
  python3 tools/fetch_images.py "seoul apartment" -n 3 --source pexels
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests

UA = "nbpipe-image-fetcher/1.0 (personal blog research)"
TIMEOUT = 30

# 출처 표기가 필요 없는 라이선스(퍼블릭 도메인 계열)
_NO_ATTRIBUTION = {"cc0", "pdm", "pexels", "unsplash"}
# 기본 허용: 상업적 이용 + 변경 허용 + 동일조건 부담 없음
_ALLOWED_CC = {"cc0", "pdm", "by"}
# BY-SA는 2차적 저작물에 동일 라이선스를 요구해 블로그에선 해석이 번거롭다.
# --allow-sharealike 를 준 경우에만 포함한다.
_SHAREALIKE = {"by-sa"}


def _slug(text: str, limit: int = 40) -> str:
    s = re.sub(r"[^\w가-힣]+", "_", text.strip().lower()).strip("_")
    return (s[:limit] or "image")


class Photo:
    def __init__(self, *, title, url, page_url, creator, creator_url,
                 license_code, license_url, source):
        self.title = title or "untitled"
        self.url = url
        self.page_url = page_url or ""
        self.creator = creator or ""
        self.creator_url = creator_url or ""
        self.license_code = (license_code or "").lower()
        self.license_url = license_url or ""
        self.source = source

    @property
    def needs_attribution(self) -> bool:
        return self.license_code not in _NO_ATTRIBUTION

    def credit_line(self) -> str:
        """블로그 하단에 붙일 출처 문구."""
        if not self.needs_attribution:
            return (f"{self.title} — {self.source} "
                    f"({self.license_code.upper()}, 출처 표기 의무 없음)")
        who = self.creator or "Unknown"
        parts = [f'"{self.title}"']
        parts.append(f"by {who}")
        if self.page_url:
            parts.append(f"({self.page_url})")
        parts.append(f"/ {self.license_code.upper()}")
        if self.license_url:
            parts.append(self.license_url)
        return " ".join(parts)


def search_openverse(query: str, count: int, license_filter: str | None,
                     allow_sa: bool = False) -> list[Photo]:
    params = {
        "q": query,
        "page_size": max(count * 3, 10),  # 필터링 여유분
        "mature": "false",
    }
    if license_filter:
        params["license"] = license_filter
    else:
        # 상업적 이용 + 변경 허용
        params["license_type"] = "commercial,modification"
    r = requests.get("https://api.openverse.org/v1/images/", params=params,
                     headers={"User-Agent": UA}, timeout=TIMEOUT)
    r.raise_for_status()
    out: list[Photo] = []
    for it in r.json().get("results", []):
        code = (it.get("license") or "").lower()
        allowed = _ALLOWED_CC | (_SHAREALIKE if allow_sa else set())
        if code not in allowed:
            continue
        if not it.get("url"):
            continue
        out.append(Photo(
            title=it.get("title"),
            url=it["url"],
            page_url=it.get("foreign_landing_url"),
            creator=it.get("creator"),
            creator_url=it.get("creator_url"),
            license_code=code,
            license_url=it.get("license_url"),
            source=it.get("provider") or "openverse",
        ))
        if len(out) >= count:
            break
    return out


def search_pexels(query: str, count: int) -> list[Photo]:
    headers = {"User-Agent": UA}
    key = os.getenv("PEXELS_API_KEY")
    if key:
        headers["Authorization"] = key
    r = requests.get("https://api.pexels.com/v1/search",
                     params={"query": query, "per_page": count},
                     headers=headers, timeout=TIMEOUT)
    if r.status_code == 401:
        raise RuntimeError("Pexels 인증 실패 — PEXELS_API_KEY 를 설정하세요.")
    r.raise_for_status()
    out = []
    for p in r.json().get("photos", []):
        src = p.get("src", {})
        out.append(Photo(
            title=p.get("alt") or query,
            url=src.get("large2x") or src.get("large") or src.get("original"),
            page_url=p.get("url"),
            creator=p.get("photographer"),
            creator_url=p.get("photographer_url"),
            license_code="pexels",
            license_url="https://www.pexels.com/license/",
            source="pexels",
        ))
    return out


def search_unsplash(query: str, count: int) -> list[Photo]:
    key = os.getenv("UNSPLASH_ACCESS_KEY")
    if not key:
        raise RuntimeError("UNSPLASH_ACCESS_KEY 가 없습니다.")
    r = requests.get("https://api.unsplash.com/search/photos",
                     params={"query": query, "per_page": count},
                     headers={"User-Agent": UA,
                              "Authorization": f"Client-ID {key}"},
                     timeout=TIMEOUT)
    r.raise_for_status()
    out = []
    for p in r.json().get("results", []):
        out.append(Photo(
            title=p.get("description") or p.get("alt_description") or query,
            url=(p.get("urls") or {}).get("regular"),
            page_url=(p.get("links") or {}).get("html"),
            creator=((p.get("user") or {}).get("name")),
            creator_url=((p.get("user") or {}).get("links") or {}).get("html"),
            license_code="unsplash",
            license_url="https://unsplash.com/license",
            source="unsplash",
        ))
    return out


_SEARCHERS = {
    "openverse": lambda q, n, lic, sa: search_openverse(q, n, lic, sa),
    "pexels": lambda q, n, lic, sa: search_pexels(q, n),
    "unsplash": lambda q, n, lic, sa: search_unsplash(q, n),
}


def download(photo: Photo, dest: Path, stem: str) -> Path | None:
    try:
        r = requests.get(photo.url, headers={"User-Agent": UA},
                         timeout=TIMEOUT, stream=True)
        r.raise_for_status()
    except Exception as e:  # 네트워크/403 등은 건너뛴다
        print(f"  ! 다운로드 실패: {e}", file=sys.stderr)
        return None
    ext = Path(urlparse(photo.url).path).suffix.lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
        ctype = r.headers.get("content-type", "")
        ext = ".png" if "png" in ctype else ".jpg"
    p = dest / f"{stem}{ext}"
    with open(p, "wb") as f:
        for chunk in r.iter_content(65536):
            f.write(chunk)
    return p


def main() -> int:
    ap = argparse.ArgumentParser(description="라이선스 안전한 무료 이미지 수집")
    ap.add_argument("query", help="검색어(영문이 결과가 많음)")
    ap.add_argument("-n", "--count", type=int, default=3, help="가져올 장수")
    ap.add_argument("-o", "--out", default="output/images", help="저장 디렉터리")
    ap.add_argument("--source", default="openverse",
                    choices=sorted(_SEARCHERS), help="이미지 소스")
    ap.add_argument("--license", default=None,
                    help="openverse 전용. 예: cc0,pdm (출처표기 의무 없는 것만)")
    ap.add_argument("--allow-sharealike", action="store_true",
                    help="BY-SA(동일조건변경허락)도 포함. 기본은 제외")
    args = ap.parse_args()

    dest = Path(args.out)
    dest.mkdir(parents=True, exist_ok=True)

    try:
        photos = _SEARCHERS[args.source](args.query, args.count, args.license,
                                         args.allow_sharealike)
    except Exception as e:
        print(f"검색 실패({args.source}): {e}", file=sys.stderr)
        return 1
    if not photos:
        print("조건에 맞는 이미지를 찾지 못했습니다. 검색어나 라이선스를 바꿔보세요.")
        return 1

    base = _slug(args.query)
    saved: list[tuple[Path, Photo]] = []
    for i, ph in enumerate(photos, 1):
        p = download(ph, dest, f"{base}_{i:02d}")
        if p:
            saved.append((p, ph))
            flag = "출처표기 필요" if ph.needs_attribution else "표기 의무 없음"
            print(f"  저장: {p.name}  [{ph.license_code.upper()} · {flag}]")

    if not saved:
        return 1

    # 출처 표기 파일(누적)
    credits = dest / "CREDITS.md"
    lines: list[str] = []
    if not credits.exists():
        lines.append("# 이미지 출처\n")
        lines.append("> 블로그 본문 하단에 아래 문구를 붙여 출처를 밝힌다.\n")
        lines.append("> CC0/PDM/Pexels/Unsplash 는 표기 의무가 없으나 기록은 남긴다.\n")
    lines.append(f"\n## 검색어: {args.query} ({args.source})\n")
    for p, ph in saved:
        lines.append(f"- `{p.name}` — {ph.credit_line()}")
    with open(credits, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    # 기계 판독용 메타
    meta_path = dest / "credits.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else []
    for p, ph in saved:
        meta.append({
            "file": p.name, "title": ph.title, "creator": ph.creator,
            "license": ph.license_code, "license_url": ph.license_url,
            "source": ph.source, "page_url": ph.page_url,
            "needs_attribution": ph.needs_attribution,
        })
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                         encoding="utf-8")

    need = [ph for _, ph in saved if ph.needs_attribution]
    print(f"\n총 {len(saved)}장 저장 → {dest}")
    print(f"출처 표기 필요: {len(need)}장 (CREDITS.md 확인)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
