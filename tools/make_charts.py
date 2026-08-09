#!/usr/bin/env python3
"""블로그 본문에 넣을 '직접 만든' 차트 생성기.

남의 이미지를 가져다 쓰면 저작권 리스크 + 유사문서 감점이 있으므로,
공개된 수치를 근거로 우리가 직접 그린다. 실제 발행 시에는 각자
최신 수치를 확인해 CONFIG 값을 갱신할 것.

사용:  python3 tools/make_charts.py [출력디렉터리]
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager as fm  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

# --- 한글 폰트 ---
_CANDIDATES = ["NanumGothic", "NanumBarunGothic", "Noto Sans CJK KR", "Malgun Gothic"]
_available = {f.name for f in fm.fontManager.ttflist}
for _name in _CANDIDATES:
    if _name in _available:
        plt.rcParams["font.family"] = _name
        break
plt.rcParams["axes.unicode_minus"] = False

# --- 색 (네이버 그린 계열 + 차분한 톤) ---
C_UP = "#e0503f"      # 상승/고점
C_DOWN = "#2f6fdb"    # 하락/지지
C_TEXT = "#222222"
C_MUTED = "#8b95a1"
C_GRID = "#e5e8eb"
C_BAND = "#f4f6f8"

# --- 발행 시점에 맞춰 갱신할 값 ---
CFG = {
    "low": 2417,          # 이번 대세 상승의 시작 저점(2024년 저점권)
    "high": 9385,         # 2026-06-19 사상 최고가
    "current": 6259,      # 최근 종가(2026-08-07, 발행 시 갱신)
    "semi_share": 50,     # 삼성전자+SK하이닉스 지수 시총 비중(%) — '절반 이상'
    # 하락 경로에 찍을 '실제 확인된 종가'만 넣는다. 없는 날짜를 지어내지 말 것.
    "path": [
        ("6/19", 9385),
        ("7/13", 6881),
        ("7/23", 7097),
        ("8/7", 6259),
    ],
}


def fib_levels(low: float, high: float) -> dict[str, float]:
    span = high - low
    return {
        "0.382": high - span * 0.382,
        "0.5": high - span * 0.5,
        "0.618": high - span * 0.618,
    }


def chart_retracement(out: Path) -> Path:
    """실제 하락 경로 + 되돌림 레벨 밴드.

    가격 시계열 전체가 아니라 '확인된 종가 몇 개'만 이어 붙인 것이므로
    그 사실을 각주에 밝힌다. 없는 날짜를 지어내지 않는다.
    """
    low, high = CFG["low"], CFG["high"]
    lv = fib_levels(low, high)
    path = CFG["path"]
    labels = [d for d, _ in path]
    vals = [v for _, v in path]

    top = high + 450
    bottom = lv["0.618"] - 450
    fig, ax = plt.subplots(figsize=(8.6, 5.8), dpi=200)
    ax.set_ylim(bottom, top)
    ax.set_xlim(-0.55, len(vals) - 1 + 2.1)   # 오른쪽에 레벨 라벨 자리

    # 되돌림 밴드(아래로 갈수록 진하게) — 어디까지 왔는지 한눈에
    bands = [
        (lv["0.382"], top, "#ffffff"),
        (lv["0.5"], lv["0.382"], "#f7f9fa"),
        (lv["0.618"], lv["0.5"], "#eef2f6"),
        (bottom, lv["0.618"], "#fdecea"),
    ]
    for y0, y1, c in bands:
        ax.axhspan(y0, y1, color=c, zorder=0)

    # 되돌림 레벨선 + 오른쪽 라벨
    for y, name, color, bold in [
        (lv["0.382"], "0.382", C_MUTED, False),
        (lv["0.5"], "0.5", C_MUTED, False),
        (lv["0.618"], "0.618", C_DOWN, True),
    ]:
        ax.axhline(y, color=color, lw=1.6 if bold else 1.2,
                   ls="-" if bold else ":", zorder=2)
        ax.text(len(vals) - 1 + 0.18, y, f"{name} 되돌림  {y:,.0f}",
                color=color, fontsize=11.5, va="center",
                fontweight="bold" if bold else "normal", zorder=4,
                bbox=dict(facecolor="white", edgecolor="none", pad=2.5))

    # 고점선
    ax.axhline(high, color=C_UP, lw=1.6, zorder=2)
    ax.text(len(vals) - 1 + 0.18, high, f"고점  {high:,}", color=C_UP,
            fontsize=11.5, va="center", fontweight="bold", zorder=4,
            bbox=dict(facecolor="white", edgecolor="none", pad=2.5))

    # 실제 종가 경로
    xs = list(range(len(vals)))
    ax.plot(xs, vals, color=C_TEXT, lw=2.4, marker="o", ms=7,
            markerfacecolor="white", markeredgewidth=2.2, zorder=5)
    for x, (d, v) in zip(xs, path):
        va, dy = ("bottom", 130) if x in (0, len(vals) - 2) else ("top", -150)
        ax.text(x, v + dy, f"{v:,}", ha="center", va=va, fontsize=11.5,
                fontweight="bold", color=C_TEXT, zorder=6)

    # 현재에서 0.618 까지 남은 거리
    cur = vals[-1]
    remain = (lv["0.618"] / cur - 1) * 100
    ax.annotate("", xy=(len(vals) - 1, lv["0.618"]), xytext=(len(vals) - 1, cur),
                arrowprops=dict(arrowstyle="->", color=C_DOWN, lw=2), zorder=6)
    ax.text(len(vals) - 1 - 0.12, (cur + lv["0.618"]) / 2,
            f"{remain:.0f}%", color=C_DOWN, fontsize=13, fontweight="bold",
            ha="right", va="center", zorder=6)

    drop = (cur / high - 1) * 100
    ax.set_title(f"코스피, 고점 대비 {drop:.0f}% · 0.618 되돌림은 {lv['0.618']:,.0f}",
                 fontsize=16.5, fontweight="bold", color=C_TEXT, pad=16)
    ax.set_xticks(xs)
    ax.set_xticklabels(labels, fontsize=11.5, color=C_MUTED)
    ax.set_yticks([])
    for s_ in ("top", "right", "left"):
        ax.spines[s_].set_visible(False)
    ax.spines["bottom"].set_color(C_GRID)
    ax.tick_params(axis="x", length=0)
    ax.text(0.5, -0.135,
            "※ 확인된 주요 시점 종가만 이은 그래프(일별 전체 시세 아님). "
            "되돌림은 저점 {:,} 기준 계산값.".format(low),
            transform=ax.transAxes, ha="center", fontsize=9, color=C_MUTED)

    p = out / "kospi_retracement.png"
    fig.savefig(p, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return p


def chart_concentration(out: Path) -> Path:
    """삼성전자+SK하이닉스 지수 쏠림 도넛."""
    share = CFG["semi_share"]
    fig, ax = plt.subplots(figsize=(7.2, 6.2), dpi=200)

    wedges, _ = ax.pie(
        [share, 100 - share],
        startangle=90,
        colors=["#e0503f", "#dfe3e8"],
        wedgeprops=dict(width=0.42, edgecolor="white", linewidth=3),
    )
    ax.text(0, 0.12, f"{share}%+", ha="center", va="center",
            fontsize=34, fontweight="bold", color="#e0503f")
    ax.text(0, -0.22, "단 2종목", ha="center", va="center",
            fontsize=15, color=C_TEXT)

    ax.set_title("코스피 시가총액, 단 두 종목이 절반 이상", fontsize=17,
                 fontweight="bold", color=C_TEXT, pad=18)
    ax.legend(
        wedges,
        ["삼성전자 + SK하이닉스", "나머지 전 종목"],
        loc="lower center", bbox_to_anchor=(0.5, -0.1),
        frameon=False, fontsize=12.5, ncol=1, labelspacing=0.5,
    )
    ax.text(0.5, -0.185,
            "지수를 산다는 건 사실상 반도체 비중 절반짜리 바구니를 사는 것",
            transform=ax.transAxes, ha="center", fontsize=11, color=C_MUTED)
    p = out / "kospi_concentration.png"
    fig.savefig(p, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return p


def chart_affiliate_breakeven(out: Path) -> Path:
    """객단가별로 목표 수익을 만들려면 몇 건을 팔아야 하는지."""
    target = 200_000          # 목표 월 수익(원)
    rate = 0.15               # 제휴 수수료율
    prices = [10_000, 30_000, 50_000, 100_000]
    counts = [math.ceil(target / (p * rate)) for p in prices]

    fig, ax = plt.subplots(figsize=(8, 5.2), dpi=200)
    labels = [f"{p // 10000}만원" for p in prices]
    bars = ax.bar(labels, counts, color=["#e0503f", "#ef8a7d", "#7aa7e8", "#2f6fdb"],
                  width=0.58, zorder=3)
    for b, c in zip(bars, counts):
        ax.text(b.get_x() + b.get_width() / 2, c + max(counts) * 0.03,
                f"{c:,}건", ha="center", fontsize=13, fontweight="bold",
                color=C_TEXT)

    ax.set_title(f"월 {target // 10000}만원 만들려면 몇 개 팔아야 하나",
                 fontsize=17, fontweight="bold", color=C_TEXT, pad=18)
    ax.text(0.5, 1.01, f"제휴 수수료 {rate:.0%} 가정 · 객단가별 필요 판매 건수",
            transform=ax.transAxes, ha="center", va="bottom",
            fontsize=11, color=C_MUTED)
    ax.set_ylim(0, max(counts) * 1.18)
    ax.set_yticks([])
    ax.grid(axis="y", color=C_GRID, zorder=0)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(C_GRID)
    ax.tick_params(axis="x", labelsize=12.5, colors=C_TEXT, length=0)
    ax.text(0.5, -0.115, "객단가 · ※ 수수료율은 상품·브랜드마다 다르므로 발행 시점 기준 확인 필요",
            transform=ax.transAxes, ha="center", fontsize=9, color=C_MUTED)

    p = out / "affiliate_breakeven.png"
    fig.savefig(p, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return p


def chart_double_bottom(out: Path) -> Path:
    """쌍바닥(W) 개념도 — 1차 저점·넥라인·2차 저점·확정 지점."""
    # 개념 설명용 모식도. 실제 주가 데이터가 아니라는 점을 각주로 밝힌다.
    xs = [0, 1.0, 1.9, 2.6, 3.4, 4.2, 5.1, 6.0, 6.9, 7.8, 8.7]
    ys = [9.6, 8.2, 6.6, 5.1, 4.55, 6.3, 6.55, 5.3, 4.75, 6.6, 8.1]

    fig, ax = plt.subplots(figsize=(8.4, 5.4), dpi=200)
    ax.plot(xs, ys, color="#2f6fdb", lw=2.6, zorder=3, solid_capstyle="round")

    neck = 6.55
    ax.axhline(neck, color=C_MUTED, lw=1.4, ls="--", zorder=2)
    ax.text(0.08, neck + 0.16, "넥라인 (중간 반등 고점)", color=C_MUTED, fontsize=11)

    floor = 4.55
    ax.axhspan(floor - 0.45, floor + 0.45, color="#fdecea", zorder=0)
    ax.text(0.08, floor - 0.95, "지지 구간 (예: 5,000 부근)", color=C_UP, fontsize=11)

    def mark(x, y, label, dy=0.45, color=C_TEXT):
        ax.plot([x], [y], "o", color=color, ms=8, zorder=4)
        ax.text(x, y + dy, label, ha="center", fontsize=11.5,
                fontweight="bold", color=color, zorder=4)

    mark(3.4, 4.55, "1차 저점", dy=-0.75, color=C_UP)
    mark(6.9, 4.75, "2차 저점", dy=-0.75, color=C_UP)
    # 돌파 지점 표시는 선 위에 두되, 설명 텍스트는 선과 겹치지 않는 빈 곳에 둔다
    ax.plot([8.25], [7.35], "o", color="#0d8a43", ms=8, zorder=4)
    ax.text(6.45, 8.55, "넥라인 돌파 = 쌍바닥 확정", fontsize=12,
            fontweight="bold", color="#0d8a43", ha="center", zorder=4)
    ax.annotate("", xy=(8.15, 7.5), xytext=(7.15, 8.4),
                arrowprops=dict(arrowstyle="->", color="#0d8a43", lw=1.6), zorder=4)

    ax.set_title("쌍바닥(W)은 넥라인을 뚫어야 완성됨", fontsize=17,
                 fontweight="bold", color=C_TEXT, pad=16)
    ax.text(0.5, 1.01,
            "2차 저점이 나왔다고 끝이 아니라, 중간 반등 고점을 넘어야 확정",
            transform=ax.transAxes, ha="center", va="bottom",
            fontsize=11, color=C_MUTED)
    ax.set_xlim(-0.2, 9.2)
    ax.set_ylim(3.1, 10.4)
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    ax.text(0.5, -0.06, "※ 패턴 설명을 위한 개념도이며 실제 주가 데이터가 아님.",
            transform=ax.transAxes, ha="center", fontsize=9, color=C_MUTED)

    p = out / "double_bottom.png"
    fig.savefig(p, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return p


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "output/images")
    out.mkdir(parents=True, exist_ok=True)
    for p in (chart_retracement(out), chart_concentration(out),
              chart_affiliate_breakeven(out), chart_double_bottom(out)):
        print(f"생성: {p}")


if __name__ == "__main__":
    main()
