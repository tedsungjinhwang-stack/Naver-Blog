#!/usr/bin/env python3
"""라이선스 안전한 무료 이미지를 수동으로 더 받고 싶을 때 쓰는 CLI.

평소에는 `nbpipe ingest` 가 니치·주제에 맞춰 자동 수집하므로 이 도구는
"특정 검색어로 몇 장 더" 필요할 때만 쓰면 된다. 실제 수집 로직과
라이선스 정책은 nbpipe.media 를 그대로 사용한다.

사용:
  python3 tools/fetch_images.py "stock market chart" -n 3
  python3 tools/fetch_images.py "coins money" -n 2 --license cc0,pdm
  python3 tools/fetch_images.py "seoul apartment" -n 3 --source pexels
  python3 tools/fetch_images.py --niche 부동산 --keywords 청약 특별공급 -n 2
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nbpipe.media.images import ImageFetcher, write_credits  # noqa: E402
from nbpipe.media.queries import queries_for  # noqa: E402
from nbpipe.models import Niche  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="라이선스 안전한 무료 이미지 수집")
    ap.add_argument("query", nargs="?", help="검색어(영문이 결과가 많음)")
    ap.add_argument("--niche", help="query 대신 니치로 검색어 자동 결정 (경제/투자/부업/부동산)")
    ap.add_argument("--keywords", nargs="*", default=[], help="--niche 와 함께 쓸 글 키워드")
    ap.add_argument("-n", "--count", type=int, default=3, help="가져올 장수")
    ap.add_argument("-o", "--out", default="output/images", help="저장 디렉터리")
    ap.add_argument("--source", default="openverse",
                    choices=["openverse", "pexels", "unsplash"], help="이미지 소스")
    ap.add_argument("--license", default=None,
                    help="openverse 전용. 예: cc0,pdm (출처표기 의무 없는 것만)")
    ap.add_argument("--allow-sharealike", action="store_true",
                    help="BY-SA(동일조건변경허락)도 포함. 기본은 제외")
    args = ap.parse_args()

    if args.niche:
        queries = queries_for(Niche.from_str(args.niche), args.keywords,
                              limit=max(3, args.count + 1))
        stem = Niche.from_str(args.niche).value
    elif args.query:
        queries = [args.query]
        stem = "img"
    else:
        ap.error("query 또는 --niche 중 하나는 필요합니다.")

    print(f"검색어: {', '.join(queries)}")
    dest = Path(args.out)
    fetcher = ImageFetcher(args.source, license_filter=args.license,
                           allow_sharealike=args.allow_sharealike)
    try:
        images = fetcher.collect(queries, dest, args.count, stem_prefix=stem)
    except Exception as e:
        print(f"검색 실패({args.source}): {e}", file=sys.stderr)
        return 1
    if not images:
        print("조건에 맞는 이미지를 찾지 못했습니다. 검색어나 라이선스를 바꿔보세요.")
        return 1

    for im in images:
        flag = "출처표기 필요" if im.needs_attribution else "표기 의무 없음"
        print(f"  저장: {im.file}  [{im.license_code.upper()} · {flag}]")
    write_credits(images, dest)
    need = sum(1 for im in images if im.needs_attribution)
    print(f"\n총 {len(images)}장 저장 → {dest}")
    print(f"출처 표기 필요: {need}장 (CREDITS.md 확인)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
