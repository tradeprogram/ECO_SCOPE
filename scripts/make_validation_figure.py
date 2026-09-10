"""검증 결과 그림 (논문 서식).

    python scripts/make_validation_figure.py [출력폴더]

서식은 `하수범_연구/논문figure_v4` 의 그림들에서 그대로 가져왔습니다.
    크기    3934 x 1745 px = 6.557 x 2.908 inch @ 600 dpi (2패널 기준)
    글꼴    HCR Batang (함초롬바탕), 없으면 Noto Serif KR
    색      4단 모노톤 램프 + 벽돌색 강조 1개
    축      좌·하 축선만, 격자 없음, 범례 테두리 없음
    제목    (a) … (b) … 형식으로 패널 위 가운데

두 패널로 나눕니다. 이 제안의 핵심 주장이 '검증된 것과 검증되지 않은 것을 함께
낸다'이므로 그림도 그 구조를 그대로 가집니다.
    (a) 수면 유무 판정 오차행렬 — 검증된 것
    (b) 습지별 개방수면적 결정계수 분포 — 검증되지 않은 것

수치는 web/data/validation.json 에서 직접 읽습니다. 손으로 옮겨 적으면 자료를
다시 돌렸을 때 그림만 옛 숫자로 남습니다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

import matplotlib as mpl  # noqa: E402
mpl.use("Agg")
import matplotlib.font_manager as fm  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

# ── 논문 서식 ────────────────────────────────────────────────────────────────
DPI = 600
FIGSIZE = (3934 / DPI, 1745 / DPI)      # 참고 그림(fig05)과 동일 픽셀

INK = "#1e2a33"     # 가장 진한 단계
MID = "#7d8b96"
LIGHT = "#aebac4"
PALE = "#d5dce1"
ACCENT = "#b5442e"  # 강조는 한 곳에만

_have = {f.name for f in fm.fontManager.ttflist}
SERIF = next((n for n in ("HCR Batang", "Noto Serif KR", "Batang") if n in _have), "serif")

mpl.rcParams.update({
    "font.family": SERIF,
    "axes.unicode_minus": False,        # 한글 글꼴에서 마이너스가 깨집니다
    "font.size": 7.5,
    "axes.titlesize": 10,
    "axes.labelsize": 9,
    "xtick.labelsize": 7.5,
    "ytick.labelsize": 7.5,
    "legend.fontsize": 7.5,
    "axes.edgecolor": "#222222",
    "axes.linewidth": 0.8,
    "xtick.major.width": 0.8,
    "ytick.major.width": 0.8,
    "figure.dpi": DPI,
    "savefig.dpi": DPI,
})


def load():
    v = json.loads((ROOT / "web/data/validation.json").read_text(encoding="utf-8"))
    r2 = sorted(m["r2"] for m in v["by_wetland"].values() if m.get("r2") is not None)
    return v, r2


def panel_matrix(ax, v):
    """(a) 오차행렬. 원격탐사 정확도 평가의 표준 표기입니다."""
    t = v["overall"]["presence_table"]
    m = np.array([[t["둘다_수면"], t["SAR만"]],
                  [t["광학만"], t["둘다_없음"]]], dtype=float)

    # 값이 998 하나에 쏠려 있어 선형 명암은 나머지가 전부 하얘집니다. 순위로 칠합니다.
    shade = np.zeros_like(m)
    order = np.argsort(m, axis=None)
    for rank, idx in enumerate(order):
        shade.flat[idx] = rank / (m.size - 1)
    ramp = mpl.colors.LinearSegmentedColormap.from_list("mono", ["#ffffff", PALE, MID, INK])

    ax.imshow(shade, cmap=ramp, vmin=0, vmax=1, aspect="auto")
    for i in range(2):
        for j in range(2):
            # 값이 0 인 칸도 칸으로 보여야 표로 읽힙니다. 테두리를 그립니다.
            ax.add_patch(mpl.patches.Rectangle(
                (j - 0.5, i - 0.5), 1, 1, fill=False, edgecolor="#8a949c", lw=0.7))
            ax.text(j, i, f"{int(m[i, j]):,}", ha="center", va="center",
                    fontsize=12, fontweight="bold",
                    color="white" if shade[i, j] > 0.66 else INK)

    # 열 제목은 축 대신 직접 씁니다. 축을 위로 올리면 패널 제목과 부딪힙니다.
    for j, lab in enumerate(["수면 있음", "수면 없음"]):
        ax.text(j, -0.68, lab, ha="center", va="center", fontsize=7.5)
    ax.text(0.5, -0.95, "Sentinel-2 광학", ha="center", va="center", fontsize=8.5)

    ax.set_xticks([]); ax.set_yticks([0, 1])
    ax.set_yticklabels(["수면 있음", "수면 없음"])
    ax.set_ylabel("Sentinel-1 레이더", labelpad=8, fontsize=8.5)
    ax.set_xlim(-0.5, 1.5); ax.set_ylim(1.5, -1.15)
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.tick_params(length=0)

    ax.set_title("(a) 수면 유무 판정의 오차행렬", pad=10)
    return (
            f"습지 {v['n_wetlands_validated']}개소 · 짝지은 관측 {v['overall']['n']:,}건 "
            f"(시간차 ±{v.get('max_offset_days', 3)}일)" + chr(10) +
            f"전체 일치율 {v['overall']['presence_agreement']} · "
            f"개방수면 구간 {v['by_state']['open']['presence_agreement']} "
            f"(n={v['by_state']['open']['n']:,})")


def panel_r2(ax, v, r2):
    """(b) 결정계수 분포. 검증되지 않은 쪽을 같은 무게로 보입니다."""
    bins = np.zeros(10, dtype=int)
    for x in r2:
        bins[min(9, int(x * 10))] += 1
    xs = np.arange(10)
    colors = [INK if i < 5 else PALE for i in range(10)]
    ax.bar(xs, bins, width=0.82, color=colors, edgecolor=INK, linewidth=0.5)
    for x, n in zip(xs, bins):
        if n:
            ax.text(x, n + max(bins) * 0.03, str(n), ha="center", va="bottom", fontsize=7)

    a = v["area_level_vs_variation"]
    med = a["wetland_r2_median"]
    xm = med * 10 - 0.5
    ax.axvline(xm, color=ACCENT, lw=1.0, ls=(0, (4, 2)), zorder=3)
    ax.annotate(f"중앙값 {med}", xy=(xm, max(bins) * 0.62),
                xytext=(xm + 0.55, max(bins) * 0.62),
                color=ACCENT, fontsize=7.5, va="center",
                arrowprops=dict(arrowstyle="-", color=ACCENT, lw=0.7))

    ax.set_xticks(xs)
    ax.set_xticklabels([f"{i/10:.1f}" for i in xs])
    ax.set_xlabel("습지별 결정계수 (R²)", labelpad=4, fontsize=8.5)
    ax.set_ylabel("습지 수", labelpad=4, fontsize=8.5)
    ax.set_ylim(0, max(bins) * 1.22)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_title("(b) 습지별 개방수면적 결정계수 분포", pad=10)
    return (
            f"{a['n_wetlands']}개소 중 R² 0.5 이상은 {a['wetland_r2_ge_05']}개소" + chr(10) +
            f"수준은 치우침 없으나(평균비 {a['level_ratio_median']})" + chr(10) +
            f"시간 변동은 따라가지 못함")


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "figures")
    out.mkdir(parents=True, exist_ok=True)
    v, r2 = load()

    fig, axes = plt.subplots(1, 2, figsize=FIGSIZE)
    fig.subplots_adjust(left=0.135, right=0.975, top=0.87, bottom=0.34, wspace=0.32)
    caps = [panel_matrix(axes[0], v), panel_r2(axes[1], v, r2)]
    # 설명문은 figure 좌표로 같은 높이에 답니다. 패널 좌표로 달면 축 높이가 달라
    # 두 줄의 시작선이 어긋납니다.
    for ax, cap in zip(axes, caps):
        x = ax.get_position().x0 + ax.get_position().width / 2
        fig.text(x, 0.175, cap, ha="center", va="top",
                 fontsize=7.5, color="#333333", linespacing=1.7)

    for ext in ("png", "pdf"):
        fig.savefig(out / f"fig4_validation.{ext}", dpi=DPI,
                    facecolor="white", bbox_inches=None)
    plt.close(fig)

    from PIL import Image
    im = Image.open(out / "fig4_validation.png")
    print(f"작성: {out/'fig4_validation.png'}")
    print(f"  {im.width}x{im.height} px @ {DPI} dpi · 글꼴 {SERIF}")
    print(f"  일치율 {v['by_state']['open']['presence_agreement']} "
          f"(n={v['by_state']['open']['n']:,}) · R² 중앙 {v['area_level_vs_variation']['wetland_r2_median']}")


if __name__ == "__main__":
    main()
