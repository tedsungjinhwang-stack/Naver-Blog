"""PostDraft → 검토용 Markdown + 미리보기 HTML + 네이버 붙여넣기용 텍스트 출력.

발행은 사람이 직접 한다. 따라서 산출물은 세 가지:
  1) *.md        — 메타/SEO리포트/이미지가이드/발행체크리스트까지 포함한 검토용 문서
  2) *.html      — 브라우저에서 미리보기 가능한 정갈한 본문 HTML
  3) *.naver.txt — 네이버 스마트에디터에 그대로 붙여넣는 평문(마크다운 기호 제거,
                   [소제목]·[표]·[이미지] 자리 표시). 스마트에디터가 마크다운/HTML
                   import을 지원하지 않으므로 실제 붙여넣기는 이 파일을 쓴다.
"""
from __future__ import annotations

import base64
import html
import re
from datetime import datetime
from pathlib import Path

from nbpipe.models import CheckResult, PostDraft


def _split_by_heading(markdown: str) -> list[str]:
    """본문을 소제목(## …) 단위로 쪼갠다.

    반환[0] 은 첫 소제목 이전(도입부), 이후 각 원소는 '소제목 + 그 아래 본문'.
    이미지 자리('소제목N 아래')를 정확히 끼워 넣기 위해 필요하다.
    """
    lines = markdown.splitlines()
    sections: list[list[str]] = [[]]
    for ln in lines:
        if re.match(r"^#{2,4}\s+", ln.strip()):
            sections.append([ln])
        else:
            sections[-1].append(ln)
    return ["\n".join(sec).strip() for sec in sections]


def _is_table_row(s: str) -> bool:
    return bool(re.match(r"^\|.*\|$", s.strip()))


def _is_table_divider(s: str) -> bool:
    cells = [c.strip() for c in s.strip().strip("|").split("|")]
    return bool(cells) and all(re.match(r"^:?-{2,}:?$", c) for c in cells)


def _md_to_html_body(markdown: str) -> str:
    """가벼운 마크다운→HTML 변환(제목/목록/표/문단). 외부 의존성 없이.

    표는 스마트에디터가 붙여넣기로 받아주는 핵심 요소라 반드시 <table>로 변환한다.
    """
    lines = markdown.splitlines()
    out: list[str] = []
    in_list = False
    i, n = 0, len(lines)

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    while i < n:
        line = lines[i].rstrip()
        if not line.strip():
            close_list()
            i += 1
            continue

        # 표: 연속된 | ... | 줄 묶음
        if _is_table_row(line):
            close_list()
            rows: list[list[str]] = []
            while i < n and _is_table_row(lines[i]):
                raw = lines[i].strip()
                if not _is_table_divider(raw):
                    rows.append([c.strip()
                                 for c in raw.strip("|").split("|")])
                i += 1
            if rows:
                out.append("<table>")
                head, body = rows[0], rows[1:]
                out.append("<thead><tr>"
                           + "".join(f"<th>{_inline(c)}</th>" for c in head)
                           + "</tr></thead>")
                if body:
                    out.append("<tbody>")
                    for r in body:
                        out.append("<tr>"
                                   + "".join(f"<td>{_inline(c)}</td>" for c in r)
                                   + "</tr>")
                    out.append("</tbody>")
                out.append("</table>")
            continue

        h = re.match(r"^(#{1,4})\s+(.*)$", line)
        if h:
            close_list()
            level = min(len(h.group(1)) + 1, 4)  # #→h2 로 (본문 최상위는 h2)
            out.append(f"<h{level}>{_inline(h.group(2).strip())}</h{level}>")
            i += 1
            continue

        # 체크리스트는 붙여넣었을 때 네모가 보이도록 문자로 바꾼다
        cl = re.match(r"^[-*]\s+\[[ xX]\]\s+(.*)$", line)
        if cl:
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>☐ {_inline(cl.group(1))}</li>")
            i += 1
            continue

        li = re.match(r"^[-*]\s+(.*)$", line)
        if li:
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{_inline(li.group(1))}</li>")
            i += 1
            continue

        ol = re.match(r"^\d+\.\s+(.*)$", line)
        if ol:
            # 번호는 붙여넣기 후에도 유지되도록 본문에 그대로 남긴다
            close_list()
            out.append(f"<p>{_inline(line.strip())}</p>")
            i += 1
            continue

        close_list()
        out.append(f"<p>{_inline(line.strip())}</p>")
        i += 1
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


_PASTE_TEMPLATE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>{title} — 붙여넣기</title>
<style>
  body {{ font-family: -apple-system, 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif;
          max-width: 860px; margin: 32px auto; padding: 0 16px; color: #191f28;
          background: #f7f8fa; }}
  .panel {{ background:#fff; border:1px solid #e5e8eb; border-radius:12px;
            padding:18px 20px; margin-bottom:16px; }}
  .meta {{ color:#6b7684; font-size:.9rem; margin:6px 0 0; }}
  .steps {{ margin:10px 0 0; padding-left:20px; color:#333d4b; line-height:1.9;
            font-size:.94rem; }}
  .warn {{ background:#fff7e6; border:1px solid #ffd591; border-radius:8px;
           padding:10px 12px; margin-top:12px; color:#873800; font-size:.9rem; }}
  button {{ font-size:.95rem; font-weight:700; color:#fff; background:#03c75a;
            border:0; border-radius:8px; padding:10px 16px; cursor:pointer;
            margin-right:8px; }}
  button:hover {{ filter:brightness(.94); }}
  button.sub {{ background:#4e5968; }}
  .field {{ display:flex; align-items:center; gap:10px; flex-wrap:wrap;
            margin-top:10px; }}
  .field code {{ background:#f2f4f6; padding:6px 10px; border-radius:6px;
                 font-size:.92rem; }}
  /* 복사 영역: 장식 금지. 여기 스타일은 붙여넣을 때 네이버로 딸려간다. */
  #copy-body {{ background:#fff; border:1px solid #e5e8eb; border-radius:12px;
                padding:24px; }}
  #copy-body h2 {{ font-size:1.25rem; margin:1.6em 0 .6em; }}
  #copy-body h3 {{ font-size:1.08rem; margin:1.3em 0 .5em; }}
  #copy-body p  {{ margin:.7em 0; line-height:1.85; }}
  #copy-body ul {{ margin:.7em 0; padding-left:22px; line-height:1.85; }}
  #copy-body table {{ border-collapse:collapse; margin:1em 0; width:100%; }}
  #copy-body th, #copy-body td {{ border:1px solid #d1d6db; padding:8px 10px;
                                  text-align:left; font-size:.95rem; }}
  #copy-body th {{ background:#f2f4f6; }}
  #copy-body img {{ max-width:100%; height:auto; display:block; margin:14px 0; }}
  #copy-body .cap {{ color:#6b7684; font-size:.9rem; margin:-6px 0 14px; }}
  .ok {{ color:#03a54a; font-weight:700; margin-left:6px; }}
  .gitem {{ margin:16px 0 20px; }}
  .glabel {{ font-weight:700; font-size:.95rem; margin-bottom:6px; }}
  .glabel span {{ font-weight:400; color:#6b7684; margin-left:6px; }}
  .gitem img {{ max-width:100%; border:1px solid #e5e8eb; border-radius:8px;
                display:block; }}
  .gfile {{ color:#8b95a1; font-size:.85rem; margin-top:5px; }}
</style>
</head>
<body>

<div class="panel">
  <strong style="font-size:1.05rem;">{title}</strong>
  <p class="meta">{niche} · {intent} · {chars}자 · SEO {seo}</p>
  <ol class="steps">
    <li><b>제목 복사</b> → 네이버 에디터 제목칸에 붙여넣기</li>
    <li><b>본문 복사</b> → 본문에 붙여넣기 (소제목·굵기·표가 서식째로 들어감)</li>
    <li>[사진X]·[이미지N] 자리에 사진을 올리고 그 표시줄은 삭제<br>        (네이버는 붙여넣은 이미지를 막으므로 에디터의 사진 버튼으로 업로드)</li>
    <li><b>태그 복사</b> → 태그칸에 붙여넣기</li>
  </ol>
  <div class="field">
    <button onclick="copyText(document.getElementById('t').textContent, this)">제목 복사</button>
    <code id="t">{title}</code>
  </div>
  <div class="field">
    <button onclick="copyRich(document.getElementById('copy-body'), this)">본문 복사 (서식 유지)</button>
    <button class="sub" onclick="copyText(document.getElementById('copy-body').innerText, this)">평문으로 복사</button>
  </div>
  <div class="field">
    <button class="sub" onclick="copyText(document.getElementById('g').textContent, this)">태그 복사</button>
    <code id="g">{tags}</code>
  </div>
  <div class="warn">발행 전 확인 · {credit_note}</div>
</div>

<div id="copy-body">
{body}
</div>

{gallery}

<script>
function flash(btn, msg) {{
  var s = document.createElement('span');
  s.className = 'ok'; s.textContent = msg;
  btn.parentNode.insertBefore(s, btn.nextSibling);
  setTimeout(function () {{ s.remove(); }}, 1600);
}}
// 서식 유지 복사: file:// 에서는 navigator.clipboard 를 못 쓰므로
// DOM 선택 + execCommand 를 기본 경로로 둔다.
function copyRich(el, btn) {{
  var range = document.createRange();
  range.selectNodeContents(el);
  var sel = window.getSelection();
  sel.removeAllRanges(); sel.addRange(range);
  var ok = false;
  try {{ ok = document.execCommand('copy'); }} catch (e) {{ ok = false; }}
  sel.removeAllRanges();
  flash(btn, ok ? '복사됨' : '복사 실패 — 직접 선택해 Ctrl+C');
}}
function copyText(text, btn) {{
  var ta = document.createElement('textarea');
  ta.value = text;
  ta.style.position = 'fixed'; ta.style.opacity = '0';
  document.body.appendChild(ta);
  ta.select();
  var ok = false;
  try {{ ok = document.execCommand('copy'); }} catch (e) {{ ok = false; }}
  ta.remove();
  flash(btn, ok ? '복사됨' : '복사 실패');
}}
</script>
</body>
</html>
"""


class DraftWriter:
    def __init__(self, output_dir: str | Path,
                 public_base_url: str = "") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        # 공개 https 이미지 베이스 URL(있으면 본문에 <img> 로 직접 삽입)
        self.public_base_url = public_base_url

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

        # 자동 수집한 스톡 이미지
        if draft.stock_images:
            need = [im for im in draft.stock_images if im.needs_attribution]
            L.append("## 📷 자동 수집 이미지 (라이선스 확인됨)")
            L.append("")
            for im in draft.stock_images:
                mark = "출처 표기 필요" if im.needs_attribution else "표기 의무 없음"
                L.append(f"- `{im.file}` — {im.license_code.upper()} · {mark}")
                L.append(f"    - 경로: `{im.path}`")
                L.append(f"    - 검색어: {im.query}")
                if im.needs_attribution:
                    L.append(f"    - 출처 문구: {im.credit_line()}")
            if need:
                L.append("")
                L.append(f"> ⚠️ {len(need)}장은 본문 하단에 출처 문구를 반드시 넣어야 합니다.")
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

        # 자동 수집 이미지는 '이미 파일이 있는' 것이므로 [사진A/B…]로 구분 표기한다.
        # (직접 만들어야 하는 자리는 [이미지①②…] 로 남는다.)
        # 첫 장은 대표 이미지로 도입부에, 나머지는 본문 중간 배치 안내로.
        for si, im in enumerate(draft.stock_images):
            letter = chr(ord("A") + si) if si < 26 else str(si + 1)
            label = f"[사진{letter}] {im.file}"
            if im.needs_attribution:
                label += "  (출처 표기 필요)"
            if si == 0:
                intro_marks.append(label + "  ← 대표 이미지")
            else:
                tail_marks.append(f"{label}  (본문 중간 적절한 위치)")

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
        P.append("   3) [사진X] = 수집 완료된 파일이니 그대로 업로드 "
                 "/ [이미지N] = 직접 만들거나 촬영할 자리")
        P.append("   4) [표]는 스마트에디터 '표' 기능으로 재구성")
        P.append("   5) 출처 표기가 필요한 사진은 하단 [이미지 출처] 문구를 본문에 포함")
        P.append("   6) 맨 아래 태그는 발행 시 태그란에 입력")
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
        # 출처 표기가 필요한 이미지는 본문 하단에 그대로 붙일 문구를 넣는다
        credited = [im for im in draft.stock_images if im.needs_attribution]
        if credited:
            P.append("[이미지 출처] (본문 맨 아래에 그대로 포함)")
            for im in credited:
                P.append(f"  {im.credit_line()}")
            P.append("")

        P.append("[태그] " + " ".join("#" + t for t in draft.tags))
        # 과도한 연속 빈 줄 정리
        text = "\n".join(P)
        return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"

    # --- 붙여넣기 전용 HTML(서식 유지 복사) ---
    def _data_uri(self, path_str: str) -> str | None:
        """이미지 파일 → base64 data URI.

        복사한 HTML에 이미지 데이터를 실어 보내려면 file:// 경로가 아니라
        data URI 여야 한다. 파일이 없으면 None.
        """
        if not path_str:
            return None
        p = Path(path_str)
        if not p.is_absolute():
            for base in (self.output_dir, self.output_dir.parent, Path.cwd()):
                cand = base / p
                if cand.exists():
                    p = cand
                    break
        if not p.exists() or not p.is_file():
            return None
        mime = {
            ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".gif": "image/gif", ".webp": "image/webp",
        }.get(p.suffix.lower())
        if not mime:
            return None
        try:
            raw = p.read_bytes()
        except OSError:
            return None
        return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"

    def _img_block(self, uri: str, alt: str, caption: str = "") -> str:
        cap = (f'<p class="cap">{html.escape(caption)}</p>' if caption else "")
        return (f'<p><img src="{uri}" alt="{html.escape(alt)}"></p>' + cap)

    def _placeholder_block(self, label: str) -> str:
        return f'<p>[{html.escape(label)}]</p>'

    def _slot_index(self, position: str, n_headings: int) -> int | None:
        """'소제목3 아래' → 3번째 소제목 뒤. 도입부/마무리도 해석."""
        pos = position or ""
        m = re.search(r"소제목\s*(\d+)", pos)
        if m:
            i = int(m.group(1))
            return i if 1 <= i <= n_headings else None
        if "도입" in pos or "상단" in pos:
            return 0
        if "마무리" in pos or "끝" in pos:
            return n_headings
        return None

    def _render_paste_html(self, draft: PostDraft) -> str:
        """스마트에디터에 '서식째로' 붙여넣기 위한 페이지.

        복사 영역(#copy-body)에는 장식 CSS를 걸지 않는다. 브라우저가 리치 복사할 때
        계산된 스타일을 인라인으로 실어 보내기 때문에, 색·테두리를 주면 네이버 본문에
        그대로 딸려 들어간다. 서식은 네이버 것을 쓰게 두고 구조만 넘긴다.
        """
        # 본문을 소제목 단위로 쪼갠 뒤, 각 이미지를 지정된 자리에 끼워 넣는다.
        sections = _split_by_heading(draft.body_markdown.strip())
        n_head = max(len(sections) - 1, 0)   # sections[0] 은 첫 소제목 이전 도입부

        # 복사 영역의 이미지 처리:
        #   - base64(data:) 는 스마트에디터가 '허용되지 않는 이미지'로 막는다.
        #   - 반면 공개 https 이미지는 웹페이지를 복사할 때처럼 URL로 가져갈 수 있다.
        # 따라서 public_base_url 이 설정돼 있으면 <img src="https://…"> 로 넣고,
        # 없으면 자리표시자만 두고 실제 이미지는 복사 영역 밖 '배치표'에 보여준다.
        base_url = (self.public_base_url or "").rstrip("/")
        slots: dict[int, list[str]] = {}
        gallery: list[tuple[str, str, str, str]] = []  # (라벨, 위치, 파일명, data URI)

        def add(slot: int | None, block: str, fallback_slot: int) -> None:
            slots.setdefault(fallback_slot if slot is None else slot, []).append(block)

        # 1) front-matter 이미지
        for i, im in enumerate(draft.image_prompts, 1):
            slot = self._slot_index(im.position, n_head)
            label = f"이미지{_circ(i)}"
            uri = self._data_uri(im.file)
            desc = im.alt or im.prompt
            if base_url and im.file:
                src = f"{base_url}/{Path(im.file).name}"
                add(slot, self._img_block(src, desc, im.caption), n_head)
            else:
                add(slot, self._placeholder_block(f"{label} {desc}"), n_head)
            if uri:
                gallery.append((label, im.position, Path(im.file).name, uri))

        # 2) 수집한 스톡 이미지: 첫 장은 도입부(대표), 나머지는 뒤쪽 소제목에 분산
        for si, im in enumerate(draft.stock_images):
            uri = self._data_uri(im.path or im.file)
            slot = 0 if si == 0 else min(si, n_head)
            letter = chr(ord("A") + si) if si < 26 else str(si + 1)
            label = f"사진{letter}"
            note = "  ← 대표 이미지" if si == 0 else ""
            if base_url and im.file:
                add(slot, self._img_block(f"{base_url}/{im.file}",
                                          im.title or im.query), n_head)
            else:
                add(slot, self._placeholder_block(f"{label} {im.file}{note}"), n_head)
            if uri:
                pos = "도입부" if si == 0 else f"소제목{slot} 아래"
                gallery.append((label, pos, im.file, uri))

        parts: list[str] = []
        if draft.summary:
            parts.append(f"<p>{_inline(draft.summary.strip())}</p>")
        for idx, sec in enumerate(sections):
            if sec.strip():
                parts.append(_md_to_html_body(sec))
            parts.extend(slots.get(idx, []))

        credited = [im for im in draft.stock_images if im.needs_attribution]
        if credited:
            parts.append("<p>[이미지 출처]</p>")
            for im in credited:
                parts.append(f"<p>{html.escape(im.credit_line())}</p>")

        body_html = "\n".join(parts)

        if gallery:
            g: list[str] = ['<div class="panel"><strong>이미지 배치표</strong>',
                            '<p class="meta">본문의 같은 이름 자리에 넣으세요. '
                            '에디터의 사진 버튼으로 파일을 올리거나, 아래 이미지를 '
                            '우클릭 → 이미지 복사 후 붙여넣으면 됩니다.</p>']
            for label, pos, fname, uri in gallery:
                g.append(
                    '<div class="gitem">'
                    f'<div class="glabel">[{html.escape(label)}] '
                    f'<span>{html.escape(pos)}</span></div>'
                    f'<img src="{uri}" alt="{html.escape(label)}">'
                    f'<div class="gfile">{html.escape(fname)}</div>'
                    '</div>')
            g.append("</div>")
            gallery_html = "\n".join(g)
        else:
            gallery_html = ""
        tags = " ".join("#" + t for t in draft.tags)
        need_n = len(credited)
        return _PASTE_TEMPLATE.format(
            title=html.escape(draft.title),
            body=body_html,
            gallery=gallery_html,
            tags=html.escape(tags),
            niche=html.escape(draft.niche.korean),
            intent=html.escape(draft.intent.korean),
            chars=f"{draft.char_count():,}",
            seo=(f"{draft.seo.score}/100" if draft.seo else "-"),
            credit_note=(f"출처 표기 필요 이미지 {need_n}장 — 본문 하단 문구 유지"
                         if need_n else "출처 표기 의무 있는 이미지 없음"),
        )

    def write(self, draft: PostDraft, formats: list[str] | None = None) -> list[Path]:
        formats = formats or ["markdown", "html", "naver_text", "paste_html"]
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
        if "paste_html" in formats:
            p = self.output_dir / f"{base}.paste.html"
            p.write_text(self._render_paste_html(draft), encoding="utf-8")
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
