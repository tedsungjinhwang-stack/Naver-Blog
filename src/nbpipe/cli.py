"""nbpipe 커맨드라인 인터페이스.

예)
  nbpipe doctor
  nbpipe keywords 경제 --topic 기준금리 --topic 물가
  nbpipe plan 투자 --count 3
  nbpipe brief 부동산 --topic 청약 --count 2   # 작성 브리핑 생성
  # → 브리핑 가이드대로 본문 작성 후
  nbpipe ingest output/briefs/realestate_01_청약_brief.md   # 검수→초안 출력
  nbpipe history
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from nbpipe import __version__
from nbpipe.config import load_config
from nbpipe.models import Intent, Niche


def _p(msg: str = "") -> None:
    print(msg)


def _niche(arg: str) -> Niche:
    try:
        return Niche.from_str(arg)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc))


def _intent(arg: str) -> Intent:
    try:
        return Intent.from_str(arg)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc))


# ---------------- doctor ----------------
def cmd_doctor(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    _p("== nbpipe doctor ==")
    _p(f"버전: {__version__}")
    _p(f"루트: {cfg.root}")
    _p(f"출력 경로: {cfg.output_dir}")
    _p("본문 작성: 세션의 Claude(또는 사람)가 직접 작성 → LLM API 키 불필요")
    _p("")
    _p("[비밀키 (선택)]")
    _p(f"  NAVER DataLab 키  : {'✅ 설정됨' if cfg.secrets.has_naver else '⚪ 없음 (DataLab 수집 skip)'}")
    _p("")
    _p("[선택 의존성]")
    for mod, why in [("bs4", "HTML 파싱"),
                     ("pytrends", "구글 트렌드"), ("yaml", "설정")]:
        try:
            __import__(mod)
            _p(f"  {mod:10s}: ✅ ({why})")
        except ImportError:
            _p(f"  {mod:10s}: ❌ 미설치 ({why})")
    _p("")
    _p("[수집기 토글]")
    for k, v in cfg.collectors.items():
        if isinstance(v, bool):
            _p(f"  {k:20s}: {'on' if v else 'off'}")
    return 0


# ---------------- keywords ----------------
def cmd_keywords(args: argparse.Namespace) -> int:
    from nbpipe.niche_config import load_niche_config
    from nbpipe.pipeline import Pipeline

    cfg = load_config(args.config)
    pipe = Pipeline(cfg)
    niche_cfg = load_niche_config(args.niche, cfg.root)
    seeds = args.topic or niche_cfg.seed_topics
    if not seeds:
        _p(f"[오류] 시드 주제가 없습니다. --topic 으로 지정하거나 "
           f"niches/{args.niche.value}.yaml 를 채우세요.")
        return 1

    _p(f"[{args.niche.korean}] 시드: {', '.join(seeds)}")
    keywords = pipe.collect_keywords(seeds, args.niche)
    ranked = pipe.selector.select(
        keywords, args.niche,
        include_tokens=niche_cfg.include_tokens,
        exclude_terms=niche_cfg.exclude_terms,
    )
    _p(f"\n수집·선정된 키워드 {len(ranked)}개:")
    for i, m in enumerate(ranked, 1):
        vol = f" vol={m.search_volume}" if m.search_volume else ""
        _p(f"  {i:2d}. {m.term}  (score={m.score}, 소스={sorted(m.sources)}{vol})")
    pipe.close()
    return 0


# ---------------- plan ----------------
def cmd_plan(args: argparse.Namespace) -> int:
    from nbpipe.pipeline import Pipeline

    cfg = load_config(args.config)
    pipe = Pipeline(cfg)
    try:
        plans = pipe.build_plans(
            args.niche, seeds=args.topic, count=args.count, intent=args.intent,
        )
    except ValueError as exc:
        _p(f"[오류] {exc}")
        return 1
    _p(f"[{args.niche.korean}] 글감 {len(plans)}개:")
    for i, plan in enumerate(plans, 1):
        _p(f"\n  #{i} 핵심 키워드: {plan.primary_keyword}")
        _p(f"     보조 키워드: {', '.join(plan.secondary_keywords)}")
        if plan.angle:
            _p(f"     앵글: {plan.angle}")
        _p(f"     근거: {plan.rationale}")
    pipe.close()
    return 0


# ---------------- brief ----------------
def cmd_brief(args: argparse.Namespace) -> int:
    from nbpipe.pipeline import Pipeline

    cfg = load_config(args.config)
    pipe = Pipeline(cfg)
    try:
        briefs = pipe.make_brief(
            args.niche, seeds=args.topic, count=args.count, intent=args.intent,
        )
    except ValueError as exc:
        _p(f"[오류] {exc}")
        return 1
    _p(f"[{args.niche.korean}] 작성 브리핑 {len(briefs)}개 생성:")
    for i, (plan, path) in enumerate(briefs, 1):
        _p(f"  #{i} {plan.primary_keyword} ({plan.intent.korean}) → {path}")
    _p("\n브리핑 파일의 가이드를 따라 본문을 작성한 뒤:")
    _p("  nbpipe ingest <브리핑파일>")
    pipe.close()
    return 0


# ---------------- ingest ----------------
def cmd_ingest(args: argparse.Namespace) -> int:
    from nbpipe.pipeline import Pipeline

    cfg = load_config(args.config)
    pipe = Pipeline(cfg)
    try:
        res = pipe.ingest(args.file)
    except (ValueError, FileNotFoundError) as exc:
        _p(f"[오류] {exc}")
        pipe.close()
        return 1
    d = res.draft
    _p(f"── {d.title}")
    _p(f"   니치/유형: {d.niche.korean}/{d.intent.korean} | 핵심 키워드: {d.primary_keyword}")
    _p(f"   글자수: {d.char_count():,}자")
    if d.seo:
        _p(f"   SEO 점수: {d.seo.score}/100 ({'통과' if d.seo.passed else '보완필요'})")
        for c in d.seo.failures():
            _p(f"     ⚠️ {c.label}: {c.value} (기준 {c.target})")
    if d.compliance and not d.compliance.passed:
        _p("   ⛔ 컴플라이언스 확인필요:")
        for c in d.compliance.blocks():
            _p(f"     - {c.label}: {c.value}")
    for f in res.files:
        _p(f"   📄 {f}")
    pipe.close()
    _p("\n※ 검토·수정 후 네이버 에디터에 직접 붙여넣어 발행하세요.")
    return 0


# ---------------- history ----------------
def cmd_history(args: argparse.Namespace) -> int:
    from nbpipe.store import RunStore

    cfg = load_config(args.config)
    db = cfg.root / "data" / "nbpipe.sqlite3"
    if not db.exists():
        _p("아직 실행 기록이 없습니다.")
        return 0
    store = RunStore(db)
    rows = store.recent(args.limit)
    if not rows:
        _p("기록이 없습니다.")
    for r in rows:
        _p(f"[{r['created_at'][:19]}] {r['niche']:10s} | "
           f"{r['primary_keyword']:20s} | SEO {r['seo_score']:3d} | {r['title']}")
    store.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nbpipe",
        description="네이버 블로그 자동 초안 파이프라인 (홈판/C-Rank/DIA 최적화). "
                    "발행은 하지 않으며, 검토용 초안만 생성합니다.",
    )
    parser.add_argument("--version", action="version", version=f"nbpipe {__version__}")
    parser.add_argument("--config", default=None, help="설정 파일 경로")
    sub = parser.add_subparsers(dest="command", required=True)

    p_doc = sub.add_parser("doctor", help="설정/키/의존성 상태 점검")
    p_doc.set_defaults(func=cmd_doctor)

    p_kw = sub.add_parser("keywords", help="키워드 수집·선정 결과 확인")
    p_kw.add_argument("niche", type=_niche, help="경제|투자|부업|부동산 (또는 영문 키)")
    p_kw.add_argument("--topic", action="append", help="시드 주제(여러 번 지정 가능)")
    p_kw.set_defaults(func=cmd_keywords)

    p_plan = sub.add_parser("plan", help="글감(키워드 기획안) 생성")
    p_plan.add_argument("niche", type=_niche)
    p_plan.add_argument("--topic", action="append", help="시드 주제")
    p_plan.add_argument("--count", type=int, default=1, help="글감 개수")
    p_plan.add_argument("--intent", type=_intent, default=Intent.HOMEFEED,
                        help="homefeed(홈판, 기본) | search(검색형)")
    p_plan.set_defaults(func=cmd_plan)

    p_brief = sub.add_parser("brief", help="작성 브리핑 생성(수집→선정→브리핑 파일)")
    p_brief.add_argument("niche", type=_niche)
    p_brief.add_argument("--topic", action="append", help="시드 주제")
    p_brief.add_argument("--count", type=int, default=1, help="브리핑 개수")
    p_brief.add_argument("--intent", type=_intent, default=Intent.HOMEFEED,
                         help="homefeed(홈판, 기본) | search(검색형)")
    p_brief.set_defaults(func=cmd_brief)

    p_ing = sub.add_parser("ingest", help="작성한 글(front-matter+본문) 검수→초안 출력")
    p_ing.add_argument("file", help="작성 파일 경로(.md)")
    p_ing.set_defaults(func=cmd_ingest)

    p_hist = sub.add_parser("history", help="최근 실행 기록")
    p_hist.add_argument("--limit", type=int, default=20)
    p_hist.set_defaults(func=cmd_history)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    try:
        return args.func(args)
    except KeyboardInterrupt:
        _p("\n중단됨.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
