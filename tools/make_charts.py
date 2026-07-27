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
    "current": 7097,      # 최근 종가(발행 시 갱신)
    "current_label": "현재 7,097\n(7/23)",
    "semi_share": 50,     # 삼성전자+SK하이닉스 지수 시총 비중(%) — '절반 이상'
}


def fib_levels(low: float, high: float) -> dict[str, float]:
    span = high - low
    return {
        "0.382": high - span * 0.382,
        "0.5": high - span * 0.5,
        "0.618": high - span * 0.618,
    }


def chart_retracement(out: Path) -> Path:
    """0.618 되돌림 레벨 도표 (가격 시계열이 아닌 '계산 결과 레벨' 시각화)."""
    low, high, cur = CFG["low"], CFG["high"], CFG["current"]
    lv = fib_levels(low, high)

    bottom = lv["0.618"] - 320          # 저점(2,417)까지 그리면 여백만 커져서 잘라낸다
    fig, ax = plt.subplots(figsize=(8, 6.0), dpi=200)
    ax.set_xlim(0, 10)
    ax.set_ylim(bottom, high + 500)

    # 되돌림 진행 구간 음영
    ax.add_patch(Rectangle((0, lv["0.618"]), 10, high - lv["0.618"],
                           facecolor=C_BAND, edgecolor="none", zorder=0))

    def level(y, label, note, color, lw=2.0, ls="-", bold=False, dy=110):
        ax.axhline(y, color=color, lw=lw, ls=ls, zorder=3)
        w = "bold" if bold else "normal"
        ax.text(0.15, y + dy, label, color=color, fontsize=11.5, fontweight=w, zorder=4)
        ax.text(9.85, y + dy, note, color=color, fontsize=11.5, ha="right",
                fontweight=w, zorder=4)

    level(high, "고점 (2026-06-19)", f"{high:,}", C_UP, lw=2.4, bold=True)
    level(cur, "현재", f"{cur:,}", C_TEXT, lw=1.8, ls="--")
    # 현재(7,097)와 0.382(6,723)가 가까워 라벨을 아래쪽으로 내려 겹침 방지
    level(lv["0.382"], "0.382 되돌림", f"{lv['0.382']:,.0f}", C_MUTED,
          lw=1.4, ls=":", dy=-260)
    level(lv["0.5"], "0.5 되돌림", f"{lv['0.5']:,.0f}", C_MUTED, lw=1.4, ls=":")
    level(lv["0.618"], "0.618 되돌림", f"{lv['0.618']:,.0f}", C_DOWN, lw=2.4, bold=True)

    # 고점→현재 낙폭
    drop = (cur / high - 1) * 100
    ax.annotate("", xy=(1.6, cur), xytext=(1.6, high),
                arrowprops=dict(arrowstyle="->", color=C_UP, lw=1.8), zorder=5)
    ax.text(1.85, (cur + high) / 2, f"{drop:.0f}%", color=C_UP,
            fontsize=13.5, fontweight="bold", va="center", zorder=5)

    # 현재→0.618 남은 거리
    remain = (lv["0.618"] / cur - 1) * 100
    ax.annotate("", xy=(8.4, lv["0.618"]), xytext=(8.4, cur),
                arrowprops=dict(arrowstyle="->", color=C_DOWN, lw=1.8), zorder=5)
    ax.text(8.15, (cur + lv["0.618"]) / 2, f"{remain:.0f}%", color=C_DOWN,
            fontsize=13.5, fontweight="bold", va="center", ha="right", zorder=5)

    ax.set_title("코스피 0.618 되돌림 자리 계산", fontsize=17, fontweight="bold",
                 color=C_TEXT, pad=18)
    ax.text(0.5, 1.008,
            f"되돌림 = 고점 - 0.618 x (고점 - 저점),  상승 시작 저점 {low:,} 기준",
            transform=ax.transAxes, ha="center", va="bottom",
            fontsize=11, color=C_MUTED)
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    ax.text(0.5, -0.035,
            "※ 가격 시계열이 아니라 되돌림 레벨을 표시한 계산 도표. 수치는 발행 시점 기준 확인 필요.",
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


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "output/images")
    out.mkdir(parents=True, exist_ok=True)
    for p in (chart_retracement(out), chart_concentration(out),
              chart_affiliate_breakeven(out)):
        print(f"생성: {p}")


if __name__ == "__main__":
    main()
