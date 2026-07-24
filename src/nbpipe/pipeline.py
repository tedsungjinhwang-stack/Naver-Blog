"""파이프라인 오케스트레이션.

수집(collect) → 선정(select) → 브리핑(brief) → [세션/사람 작성] → 인제스트
→ 검수(seo/compliance) → 출력(output) → 기록(store).

본문은 자동 API 로 생성하지 않는다. 파이프라인이 키워드/글감/작성 브리핑을
만들면, 이 세션의 Claude(또는 사람)가 직접 글을 쓰고 ingest 로 넣는다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from nbpipe.analysis import KeywordSelector
from nbpipe.analysis.keyword_selector import MergedKeyword
from nbpipe.collectors import DISCOVERY_COLLECTORS, NaverDataLabCollector
from nbpipe.config import Config
from nbpipe.models import Intent, Keyword, Niche, PostDraft, TopicPlan
from nbpipe.niche_config import NicheConfig, load_niche_config
from nbpipe.output import DraftWriter
from nbpipe.seo import ComplianceChecker, SeoScorer
from nbpipe.store import RunStore


@dataclass
class GenerationResult:
    plan: TopicPlan
    draft: PostDraft
    files: list[Path] = field(default_factory=list)
    run_id: int | None = None


class Pipeline:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.selector = KeywordSelector(config)
        self.scorer = SeoScorer(config)
        self.compliance = ComplianceChecker(config)
        self._store: RunStore | None = None

    # ---- 저장소 ----
    @property
    def store(self) -> RunStore | None:
        if not self.config.output.get("write_run_log", True):
            return None
        if self._store is None:
            db_path = self.config.root / "data" / "nbpipe.sqlite3"
            self._store = RunStore(db_path)
        return self._store

    # ---- 1) 수집 ----
    def collect_keywords(self, seeds: list[str], niche: Niche) -> list[Keyword]:
        toggles = self.config.collectors
        collected: list[Keyword] = []
        for key, cls in DISCOVERY_COLLECTORS.items():
            if not toggles.get(key, False):
                continue
            collector = cls(self.config, self.config.secrets)
            if not collector.available():
                continue
            try:
                collected.extend(collector.collect(seeds, niche))
            except Exception as exc:  # 한 소스 실패가 전체를 막지 않게
                print(f"[warn] 수집기 {key} 실패: {exc}")

        # DataLab 보정(있을 때): 후보에 상대 검색량 부여
        if toggles.get("naver_datalab", False):
            datalab = NaverDataLabCollector(self.config, self.config.secrets)
            if datalab.available() and collected:
                try:
                    anchor = seeds[0] if seeds else None
                    datalab.enrich(collected, anchor=anchor)
                except Exception as exc:
                    print(f"[warn] DataLab 보정 실패: {exc}")
        return collected

    # ---- 2) 선정 ----
    def build_plans(
        self,
        niche: Niche,
        *,
        seeds: list[str] | None = None,
        count: int = 1,
        intent: Intent = Intent.HOMEFEED,
        niche_cfg: NicheConfig | None = None,
    ) -> list[TopicPlan]:
        niche_cfg = niche_cfg or load_niche_config(niche, self.config.root)
        seeds = seeds or niche_cfg.seed_topics
        if not seeds:
            raise ValueError(
                f"'{niche.korean}' 니치의 시드 주제가 없습니다. "
                f"niches/{niche.value}.yaml 의 seed_topics 를 채우거나 --topic 으로 지정하세요."
            )

        keywords = self.collect_keywords(seeds, niche)
        # 시드 자체가 후보에 없으면(수집기 전부 off 등) 시드를 후보로 보강
        if not keywords:
            keywords = [Keyword(term=s, source="seed_topics", rank=i)
                        for i, s in enumerate(seeds)]

        recent = self.store.recent_keywords(niche.value) if self.store else []
        ranked: list[MergedKeyword] = self.selector.select(
            keywords, niche,
            include_tokens=niche_cfg.include_tokens,
            exclude_terms=niche_cfg.exclude_terms,
            recent_terms=recent,
        )
        plans = self.selector.build_topic_plans(
            ranked, niche, count=count, seeds=seeds,
        )
        # intent·앵글 배정(앵글은 있으면 순환)
        for i, plan in enumerate(plans):
            plan.intent = intent
            if niche_cfg.angles:
                plan.angle = niche_cfg.angles[i % len(niche_cfg.angles)]
        return plans

    # ---- 4) 검수 (생성/작성 공통) ----
    def finalize(self, draft: PostDraft) -> PostDraft:
        """SEO 점수 + 컴플라이언스 검사를 붙인다(자동생성·세션작성 공통)."""
        draft.seo = self.scorer.score(draft)
        text = f"{draft.title}\n{draft.summary}\n{draft.body_markdown}"
        draft.compliance = self.compliance.check(text, draft.niche)
        return draft

    def _style_ref(self, limit: int = 6000) -> str:
        """레퍼런스 톤앤매너 가이드(knowledge/style_reference.md)를 로드."""
        p = self.config.root / "knowledge" / "style_reference.md"
        if not p.exists():
            return ""
        try:
            return p.read_text(encoding="utf-8")[:limit]
        except Exception:
            return ""

    # ---- 3) 세션/수동 작성 경로 ----
    def make_brief(
        self,
        niche: Niche,
        *,
        seeds: list[str] | None = None,
        count: int = 1,
        intent: Intent = Intent.HOMEFEED,
    ) -> list[tuple[TopicPlan, Path]]:
        """글감별 '작성 브리핑' 파일을 output/briefs/ 에 만든다."""
        from nbpipe.authoring import render_brief

        plans = self.build_plans(niche, seeds=seeds, count=count, intent=intent)
        briefs_dir = self.config.output_dir / "briefs"
        briefs_dir.mkdir(parents=True, exist_ok=True)
        style_ref = self._style_ref()
        out: list[tuple[TopicPlan, Path]] = []
        for i, plan in enumerate(plans, 1):
            content = render_brief(plan, self.config.seo, style_ref=style_ref)
            slug = _slugify(plan.primary_keyword)
            path = briefs_dir / f"{niche.value}_{i:02d}_{slug}_brief.md"
            path.write_text(content, encoding="utf-8")
            out.append((plan, path))
        return out

    def ingest(self, path: str | Path) -> GenerationResult:
        """세션/사람이 쓴 작성 파일 → 검수 + 초안 출력."""
        from nbpipe.authoring import parse_authored_post

        draft = parse_authored_post(path)
        draft = self.finalize(draft)
        files, run_id = self.emit(draft)
        plan = TopicPlan(
            niche=draft.niche, primary_keyword=draft.primary_keyword,
            intent=draft.intent,
            secondary_keywords=draft.meta.get("secondary_keywords", []),
        )
        return GenerationResult(plan=plan, draft=draft, files=files, run_id=run_id)

    # ---- 5) 출력 + 6) 기록 ----
    def emit(self, draft: PostDraft) -> tuple[list[Path], int | None]:
        writer = DraftWriter(self.config.output_dir)
        files = writer.write(draft, self.config.output.get("formats"))
        run_id = None
        if self.store:
            run_id = self.store.record(
                niche=draft.niche.value,
                primary_keyword=draft.primary_keyword,
                title=draft.title,
                char_count=draft.char_count(),
                seo_score=draft.seo.score if draft.seo else 0,
                compliance_ok=draft.compliance.passed if draft.compliance else True,
                tags=draft.tags,
                files=[str(p) for p in files],
                meta={"source": draft.meta.get("source", "authored"),
                      "intent": draft.intent.value},
            )
        return files, run_id

    def close(self) -> None:
        if self._store is not None:
            self._store.close()
            self._store = None


def _slugify(text: str) -> str:
    import re
    base = re.sub(r"[^\w가-힣]+", "-", (text or "").strip())
    return re.sub(r"-+", "-", base).strip("-")[:40] or "post"
