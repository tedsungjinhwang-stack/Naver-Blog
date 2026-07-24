"""PostDraft → 검토용 Markdown + 미리보기 HTML + 네이버 붙여넣기용 텍스트 출력.

발행은 사람이 직접 한다. 따라서 산출물은 세 가지:
  1) *.md        — 메타/SEO리포트/이미지가이드/발행체크리스트까지 포함한 검토용 문서
  2) *.html      — 브라우저에서 미리보기 가능한 정갈한 본문 HTML
  3) *.naver.txt — 네이버 스마트에디터에 그대로 붙여넣는 평문(마크다운 기호 제거,
                   [소제목]·[표]·[이미지] 자리 표시). 스마트에디터가 마크다운/HTML
                   import을 지원하지 않으므로 실제 붙여넣기는 이 파일을 쓴다.
"""
from __future__ import annotations

import html
import re
from datetime import datetime
from pathlib import Path

from nbpipe.models import CheckResult, PostDraft


def _md_to_html_body(markdown: str) -> str:
    """아주 가벼운 마크다운→HTML 변환(제목/목록/문단만). 외부 의존성 없이."""
    lines = markdown.splitlines()
    out: list[str] = []
    in_list = False

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            close_list()
            continue
        h = re.match(r"^(#{1,4})\s+(.*)$", line)
        if h:
            close_list()
            level = min(len(h.group(1)) + 1, 4)  # #→h2 로 (본문 최상위는 h2)
            out.append(f"<h{level}>{html.escape(h.group(2).strip())}</h{level}>")
            continue
        li = re.match(r"^[-*]\s+(.*)$", line)
        if li:
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{_inline(li.group(1))}</li>")
            continue
        close_list()
        out.append(f"<p>{_inline(line.strip())}</p>")
    close_list()
    return "\n".join(out)


def _inline(text: str) -> str:
    text = html.escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    # 이탤릭: 진짜 마크다운 강조만. 각주/곱셈용 별표(예: "30만원* 기준", "이자 * 원금")는
    # 감싸지 않도록, 별표가 단어문자/공백에 붙어있으면 매칭에서 제외한다.
    text = re.sub(r"(?<![\w*])\*(?!\s)([^*]+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", text)
    return text


_CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮"


def _circ(n: int) -> str:
    return _CIRCLED[n - 1] if 1 <= n <= len(_CIRCLED) else f"({n})"


def _strip_md(text: str) -> str:
    """네이버 붙여넣기용: 마크다운 강조/코드/링크 기호를 텍스트만 남기고 제거."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)          # **굵게**
    text = re.sub(r"(?<![\w*])\*(?!\s)([^*]+?)(?<!\s)\*(?![\w*])", r"\1", text)  # *기울임*
    text = re.sub(r"`([^`]+)`", r"\1", text)               # `코드`
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)   # [텍스트](url)
    return text


_HTML_TEMPLATE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
  body {{ font-family: -apple-system, 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif;
          max-width: 720px; margin: 40px auto; padding: 0 16px; line-height: 1.8;
          color: #222; }}
  h1 {{ font-size: 1.7rem; line-height: 1.4; }}
  h2 {{ font-size: 1.3rem; margin-top: 2em; border-left: 4px solid #03c75a;
        padding-left: 10px; }}
  h3 {{ font-size: 1.1rem; margin-top: 1.5em; }}
  .imgph {{ background:#f2f4f6; border:1px dashed #b0b8c1; border-radius:8px;
           padding:14px; color:#4e5968; font-size:.92rem; margin:16px 0; }}
  .tags {{ margin-top:2.5em; color:#1f6feb; font-size:.95rem; }}
  em {{ color:#4e5968; }}
</style>
</head>
<body>
<h1>{title}</h1>
{body}
<p class="tags">{tags}</p>
</body>
</html>
"""


class DraftWriter:
    def __init__(self, output_dir: str | Path) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _basename(self, draft: PostDraft) -> str:
        date = datetime.now().strftime("%Y%m%d")
        return f"{date}_{draft.niche.value}_{draft.slug()}"

    # --- Markdown(검토용) ---
    def _render_markdown(self, draft: PostDraft) -> str:
        L: list[str] = []
        L.append(f"# [{draft.niche.korean}] {draft.title}")
        L.append("")
        L.append("> ⚠️ 자동 생성 초안입니다. **검토·수정 후** 네이버 에디터에 직접 붙여넣어 발행하세요.")
        L.append("")

        # 메타
        L.append("## 📌 발행 메타")
        L.append("")
        L.append(f"- **핵심 키워드**: {draft.primary_keyword}")
        L.append(f"- **목표 유형**: {draft.intent.korean} "
                 f"(권장 발행 시간: {draft.intent.publish_window()})")
        if draft.title_candidates:
            L.append("- **제목 후보**:")
            for t in draft.title_candidates:
                L.append(f"    - {t}")
        L.append(f"- **태그({len(draft.tags)})**: {' '.join('#'+t for t in draft.tags)}")
        L.append(f"- **글자수(공백제외)**: {draft.char_count():,}자")
        if draft.seo:
            L.append(f"- **SEO 점수**: {draft.seo.score}/100 "
                     f"({'통과' if draft.seo.passed else '보완필요'})")
        if draft.compliance:
            L.append(f"- **컴플라이언스**: "
                     f"{'문제없음' if draft.compliance.passed else '⚠️ 확인필요'}")
        if draft.meta.get("model"):
            L.append(f"- **생성모델**: {draft.meta['model']}")
        L.append("")

        # 요약/도입
        if draft.summary:
            L.append("## ✍️ 요약(도입부)")
            L.append("")
            L.append(draft.summary)
            L.append("")

        # 본문
        L.append("## 📄 본문")
        L.append("")
        L.append(draft.body_markdown.strip())
        L.append("")

        # 이미지 가이드
        if draft.image_prompts:
            L.append("## 🖼️ 이미지 삽입 가이드")
            L.append("")
            for i, im in enumerate(draft.image_prompts, 1):
                L.append(f"{i}. **[{im.position}]** {im.prompt}")
                if im.alt:
                    L.append(f"    - 대체텍스트(alt): `{im.alt}`")
                if im.caption:
                    L.append(f"    - 캡션: {im.caption}")
            L.append("")

        # SEO 리포트
        if draft.seo:
            L.append("## 🔎 SEO 리포트")
            L.append("")
            L.extend(self._render_checks(draft.seo.checks))
            L.append("")

        # 컴플라이언스 리포트
        if draft.compliance and draft.compliance.checks:
            L.append("## ⚖️ 컴플라이언스 체크")
            L.append("")
            L.extend(self._render_checks(draft.compliance.checks))
            L.append("")

        # 발행 체크리스트
        L.append("## ✅ 네이버 발행 체크리스트")
        L.append("")
        for item in _PUBLISH_CHECKLIST:
            L.append(f"- [ ] {item}")
        L.append("")
        return "\n".join(L)

    def _render_checks(self, checks: list[CheckResult]) -> list[str]:
        out: list[str] = []
        for c in checks:
            mark = "✅" if c.passed else ("⛔" if c.severity == "block" else "⚠️")
            line = f"- {mark} **{c.label}**"
            if c.value is not None:
                line += f" — 값: `{c.value}`"
            if c.target is not None:
                line += f" / 기준: `{c.target}`"
            out.append(line)
            if c.detail:
                out.append(f"    - {c.detail}")
        return out

    # --- HTML(붙여넣기용) ---
    def _render_html(self, draft: PostDraft) -> str:
        body_parts: list[str] = []
        if draft.summary:
            body_parts.append(f"<p>{_inline(draft.summary)}</p>")
        body_parts.append(_md_to_html_body(draft.body_markdown))
        # 이미지 자리표시자를 안내 박스로
        for im in draft.image_prompts:
            body_parts.append(
                f'<div class="imgph">🖼️ [{html.escape(im.position)}] '
                f"{html.escape(im.prompt)}"
                + (f" · alt: {html.escape(im.alt)}" if im.alt else "")
                + "</div>"
            )
        tags = " ".join("#" + html.escape(t) for t in draft.tags)
        return _HTML_TEMPLATE.format(
            title=html.escape(draft.title),
            body="\n".join(body_parts),
            tags=tags,
        )

    # --- 네이버 텍스트(붙여넣기용) ---
    def _body_to_naver(self, markdown: str) -> tuple[list[str], list[int]]:
        """본문 마크다운 → 네이버용 평문 줄 목록 + [소제목] 줄의 인덱스 목록."""
        lines = markdown.splitlines()
        out: list[str] = []
        heading_idxs: list[int] = []
        i, n = 0, len(lines)
        while i < n:
            s = lines[i].strip()
            if not s:
                out.append("")
                i += 1
                continue
            h = re.match(r"^#{1,4}\s+(.*)$", s)
            if h:
                heading_idxs.append(len(out))
                out.append(f"[소제목] {_strip_md(h.group(1).strip())}")
                i += 1
                continue
            # 표: 연속된 | ... | 줄을 묶어서 처리
            if re.match(r"^\|.*\|$", s):
                rows: list[str] = []
                while i < n and re.match(r"^\|.*\|$", lines[i].strip()):
                    rows.append(lines[i].strip())
                    i += 1
                out.append("[표] (스마트에디터 '표' 기능으로 재구성)")
                for r in rows:
                    cells = [c.strip() for c in r.strip().strip("|").split("|")]
                    if cells and all(re.match(r"^:?-{2,}:?$", c) for c in cells):
                        continue  # |---|---| 구분선
                    out.append("  " + " | ".join(_strip_md(c) for c in cells))
                continue
            cl = re.match(r"^[-*]\s+\[[ xX]\]\s+(.*)$", s)
            if cl:
                out.append("☐ " + _strip_md(cl.group(1)))
                i += 1
                continue
            b = re.match(r"^[-*]\s+(.*)$", s)
            if b:
                out.append("· " + _strip_md(b.group(1)))
                i += 1
                continue
            nm = re.match(r"^(\d+)\.\s+(.*)$", s)
            if nm:
                out.append(f"{nm.group(1)}. " + _strip_md(nm.group(2)))
                i += 1
                continue
            if re.match(r"^(-{3,}|_{3,}|\*{3,})$", s):  # 수평선
                i += 1
                continue
            if s.startswith(">"):
                out.append(_strip_md(s.lstrip(">").strip()))
                i += 1
                continue
            out.append(_strip_md(s))
            i += 1
        return out, heading_idxs

    def _render_naver_text(self, draft: PostDraft) -> str:
        body, heading_idxs = self._body_to_naver(draft.body_markdown.strip())

        # 이미지 마커 배치(위치 문자열 최대한 해석, 못 하면 맨 뒤 목록)
        intro_marks: list[str] = []
        after: dict[int, list[str]] = {}
        tail_marks: list[str] = []
        for idx, im in enumerate(draft.image_prompts, 1):
            mark = f"[이미지{_circ(idx)}] {im.alt or im.prompt}"
            pos = im.position or ""
            msub = re.search(r"소제목\s*(\d+)", pos)
            if msub and 1 <= int(msub.group(1)) <= len(heading_idxs):
                after.setdefault(heading_idxs[int(msub.group(1)) - 1], []).append(mark)
            elif "도입" in pos:
                intro_marks.append(mark)
            elif ("마무리" in pos or "끝" in pos) and heading_idxs:
                after.setdefault(max(heading_idxs[-1] - 1, 0), []).append(mark)
            else:
                tail_marks.append(f"{mark}  (위치: {pos})" if pos else mark)

        body_out: list[str] = []
        for i, line in enumerate(body):
            body_out.append(line)
            for mk in after.get(i, []):
                body_out.append(mk)

        P: list[str] = []
        P.append("※ 네이버 스마트에디터 붙여넣기용")
        P.append("   1) 아래 본문을 그대로 복사해 붙여넣기")
        P.append("   2) [소제목] 줄은 툴바에서 '제목' 스타일 지정 (대괄호 표기는 지우기)")
        P.append("   3) [이미지] 자리엔 사진 업로드, [표]는 '표' 기능으로 재구성")
        P.append("   4) 맨 아래 태그는 발행 시 태그란에 입력")
        P.append("─" * 24)
        P.append("")
        P.append(f"[제목] {_strip_md(draft.title)}")
        P.append("")
        if draft.summary:
            P.append(_strip_md(draft.summary.strip()))
        P.extend(intro_marks)
        P.append("")
        P.extend(body_out)
        P.append("")
        if tail_marks:
            P.append("[이미지 위치(본문 흐름에 맞게 배치)]")
            P.extend(tail_marks)
            P.append("")
        P.append("[태그] " + " ".join("#" + t for t in draft.tags))
        # 과도한 연속 빈 줄 정리
        text = "\n".join(P)
        return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"

    def write(self, draft: PostDraft, formats: list[str] | None = None) -> list[Path]:
        formats = formats or ["markdown", "html", "naver_text"]
        base = self._basename(draft)
        written: list[Path] = []

        if "markdown" in formats:
            p = self.output_dir / f"{base}.md"
            p.write_text(self._render_markdown(draft), encoding="utf-8")
            written.append(p)
        if "html" in formats:
            p = self.output_dir / f"{base}.html"
            p.write_text(self._render_html(draft), encoding="utf-8")
            written.append(p)
        if "naver_text" in formats or "txt" in formats:
            p = self.output_dir / f"{base}.naver.txt"
            p.write_text(self._render_naver_text(draft), encoding="utf-8")
            written.append(p)
        return written


_PUBLISH_CHECKLIST = [
    "제목에 핵심 키워드가 앞쪽(15자 이내)에 자연스럽게 포함되었는가",
    "본문 첫 문단에 핵심 키워드 1회 이상 등장하는가",
    "소제목(목차)으로 글이 시각적으로 구획되어 있는가",
    "이미지 5장 이상 + 직접 촬영/제작 이미지 위주인가 (펌 이미지 지양)",
    "표/인용/영상 등 체류시간을 높이는 요소가 있는가",
    "태그는 핵심+연관 위주 5~10개, 무관한 태그 남발 금지",
    "타 글/타 블로그와 문장이 유사하지 않은가 (유사문서 감점 회피)",
    "정보의 출처·근거를 제시했는가 (전문성=C-Rank)",
    "주제(카테고리)를 한 우물로 유지했는가",
    "발행 후 공감/댓글/서로이웃 등 초기 반응을 확보했는가",
]
