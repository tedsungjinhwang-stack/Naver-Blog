"""컴플라이언스 체커.

경제/투자/부업/부동산 니치는 표시광고법·자본시장법(유사투자자문/투자권유)·
부동산광고 규제와 맞닿아 있다. 자동 생성 본문이 문제 소지 문구를 담지
않았는지 자가 점검한다.

⚠️ 법률 자문이 아니며, 완전한 규제 준수를 보장하지 않는다. 발행 전 사람의
최종 확인이 필요하다. 리스트는 knowledge/hompan.md 리서치로 보강한다.
"""
from __future__ import annotations

import re
from typing import Any

from nbpipe.models import CheckResult, ComplianceReport, Niche

# (정규식, 라벨, 심각도) — block = 발행 전 반드시 수정 권고
_COMMON_BLOCK = [
    (r"수익\s*(을|를)?\s*보장", "수익 보장 표현(과장/허위광고 소지)"),
    (r"원금\s*보장", "원금 보장 표현(금융상품 오인 소지)"),
    (r"100\s*%\s*(수익|성공|보장|환급)", "100% 단정 표현"),
    (r"무조건\s*(오른다|수익|성공|대박)", "무조건 단정 표현"),
]

_INVESTING_BLOCK = [
    (r"(확정|보장)\s*수익", "확정/보장 수익 표현(자본시장법 소지)"),
    (r"목표\s*수익률\s*\d", "목표 수익률 제시(유사투자자문 소지)"),
    (r"목표가\s*\d", "목표가 제시(투자자문 소지)"),
    (r"손실\s*(금|액)?\s*전액\s*환불", "손실 전액 환불(불법금융광고)"),
    (r"(급등|폭등)\s*(확실|보장|예정)", "급등 단정 표현"),
    (r"(종목\s*)?리딩", "종목 리딩(유사투자자문·자본시장법 위반 소지)"),
    (r"지금\s*(당장\s*)?(매수|사세요|사라)", "직접적 매수 권유"),
    (r"묻지마\s*(매수|투자)", "묻지마 투자 조장"),
]
_INVESTING_WARN = [
    (r"추천\s*종목", "추천 종목(투자권유로 해석될 수 있음)"),
    (r"강력\s*추천", "강력 추천(권유성 표현)"),
    (r"단타|스캘핑", "단기매매 조장 표현(맥락 확인 필요)"),
]

_REALESTATE_BLOCK = [
    (r"(무조건|확실히)\s*오른다", "가격 상승 단정"),
    (r"(분양|시세)?\s*차익\s*보장", "시세차익 보장 표현"),
    (r"확정\s*프리미엄", "확정 프리미엄(과장광고)"),
    (r"떴다방", "불법 분양 관련 표현"),
]
_REALESTATE_WARN = [
    (r"대박\s*(매물|단지|입지)", "과장 표현(대박)"),
    (r"(단지\s*내\s*)?최저가", "‘최저가’ 주장(실거래가 근거 없으면 표시광고법 위반)"),
    (r"(압도적|최고)\s*조망권", "‘조망권 최고’ 등 근거 없는 주관적 최상급"),
    (r"급매\s*확정", "‘급매 확정’(미끼매물 소지)"),
    (r"지금\s*안\s*사면\s*후회", "불안 조장/권유성 표현"),
]

_SIDEJOB_BLOCK = [
    (r"하루\s*\d+\s*만\s*원\s*보장", "수익 보장(부업 사기성 표현)"),
    (r"누구나\s*(월\s*)?\d+\s*(만|백)", "누구나 고수익 단정"),
    (r"목표\s*수익률\s*\d", "목표 수익률 제시(불법금융광고 소지)"),
    (r"손실\s*(금|액)?\s*전액\s*환불", "손실 전액 환불(불법금융광고)"),
    (r"돈\s*복사", "돈 복사(사기성 표현)"),
]

# 협찬/제휴 링크가 있으면 대가성 고지가 있어야 함(뒷광고 방지, 표시광고법)
_AFFILIATE_MARKERS = [
    "쿠팡파트너스", "쿠팡 파트너스", "파트너스 활동", "제휴 링크", "제휴링크",
    "어필리에이트", "affiliate",
]
# 대가성 고지로 인정할 표현(주의: affiliate 마커의 부분문자열을 넣지 말 것 — 자동통과 버그)
_DISCLOSURE_MARKERS = [
    "광고", "협찬", "수수료를 제공", "수수료를 받", "대가를 받", "유료 광고",
    "일정액의 수수료",
]

# 네이버 저품질 집중 모니터링 키워드(제목 남발 주의)
_SENSITIVE_KEYWORDS = ["주식", "대출", "보험", "병원", "다이어트"]

# 투자/부동산 글에는 면책 문구 권장
_DISCLAIMER_HINTS = [
    "투자 판단", "투자의 책임", "본인의 판단", "참고용", "권유가 아닙니다",
    "참고 자료", "정보 제공", "개인적 의견",
]


class ComplianceChecker:
    def __init__(self, config: Any | None = None) -> None:
        self.config = config

    def _scan(self, text: str, patterns, severity: str) -> list[CheckResult]:
        out: list[CheckResult] = []
        for pattern, label in patterns:
            m = re.search(pattern, text)
            if m:
                out.append(CheckResult(
                    key=f"pat:{pattern}",
                    label=label,
                    passed=False,
                    severity=severity,
                    detail=f"발견: “…{text[max(0, m.start()-10):m.end()+10].strip()}…”",
                    value=m.group(0),
                ))
        return out

    def check(self, text: str, niche: Niche) -> ComplianceReport:
        checks: list[CheckResult] = []
        checks += self._scan(text, _COMMON_BLOCK, "block")

        if niche == Niche.INVESTING:
            checks += self._scan(text, _INVESTING_BLOCK, "block")
            checks += self._scan(text, _INVESTING_WARN, "warn")
        elif niche == Niche.REALESTATE:
            checks += self._scan(text, _REALESTATE_BLOCK, "block")
            checks += self._scan(text, _REALESTATE_WARN, "warn")
        elif niche == Niche.SIDEJOB:
            checks += self._scan(text, _SIDEJOB_BLOCK, "block")
        # 경제(ECONOMY)는 공통 규칙만

        # 면책 문구 권장(투자/부동산)
        if niche in (Niche.INVESTING, Niche.REALESTATE):
            has_disclaimer = any(h in text for h in _DISCLAIMER_HINTS)
            checks.append(CheckResult(
                key="disclaimer",
                label="면책·정보제공 목적 문구",
                passed=has_disclaimer,
                severity="warn",
                detail=("면책 문구 확인됨" if has_disclaimer else
                        "‘투자/구매 판단과 책임은 본인에게’ 취지의 면책 문구 추가 권장"),
            ))

        # 광고/제휴 표시 의무(뒷광고 방지)
        has_affiliate = any(m in text for m in _AFFILIATE_MARKERS)
        if has_affiliate:
            has_disclosure = any(m in text for m in _DISCLOSURE_MARKERS)
            checks.append(CheckResult(
                key="affiliate_disclosure",
                label="광고/제휴 표시",
                passed=has_disclosure,
                severity="warn" if has_disclosure else "block",
                detail=("표시 확인됨" if has_disclosure else
                        "제휴/협찬 링크가 감지되었습니다. ‘광고’·‘제휴’ 등 대가성 고지가 필요합니다(표시광고법)."),
            ))

        # 저품질 집중 모니터링 키워드 안내(참고)
        sensitive = [k for k in _SENSITIVE_KEYWORDS if k in text]
        if sensitive:
            checks.append(CheckResult(
                key="sensitive_keywords",
                label="저품질 모니터링 키워드",
                passed=True,  # 차단 아님 — 참고/주의
                severity="info",
                value=", ".join(sensitive),
                detail="네이버가 집중 모니터링하는 키워드입니다. 제목 남발·과장 표현을 피하세요.",
            ))

        blocks = [c for c in checks if not c.passed and c.severity == "block"]
        passed = len(blocks) == 0
        return ComplianceReport(passed=passed, checks=checks)
