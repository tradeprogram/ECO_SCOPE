"""검증 결과 그림을 만듭니다 — 제안서용.

    python scripts/make_validation_figure.py [출력폴더]

화면 캡처와 같은 글꼴·색을 쓰도록 HTML 을 짜서 Playwright 로 렌더합니다.
matplotlib 로 그리면 나머지 그림(UI 캡처)과 인상이 달라집니다.

두 칸으로 나눕니다. 이 제안의 핵심 주장이 '검증된 것과 검증되지 않은 것을
함께 낸다'이므로, 그림도 그 구조를 그대로 가집니다.
    왼쪽  수면 유무 판정 — 두 센서 분할표와 일치율 (검증된 것)
    오른쪽 습지별 면적 결정계수 분포 (검증되지 않은 것)

수치는 web/data/validation.json 에서 직접 읽습니다. 손으로 옮겨 적지 않습니다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
V = json.loads((ROOT / "web/data/validation.json").read_text(encoding="utf-8"))

OPEN = V["by_state"]["open"]
ALL = V["overall"]
AREA = V["area_level_vs_variation"]
R2 = sorted(m["r2"] for m in V["by_wetland"].values() if m.get("r2") is not None)

# 결정계수 분포를 0.1 폭으로 묶습니다.
BINS = [0] * 10
for x in R2:
    BINS[min(9, int(x * 10))] += 1
BMAX = max(BINS)


def cell(v: int, muted: bool = False) -> str:
    cls = "z" if v == 0 else ("hi" if v > 100 else "")
    return f'<td class="{cls}">{v:,}</td>'


HTML = f"""
<meta charset="utf-8">
<style>
  :root {{
    --ink:#1a201c; --ink-2:#48524c; --muted:#79837c;
    --line:#dde3df; --line-2:#eceff0;
    --green:#12603b; --green-2:#1f7a4d; --green-bg:#eef5f0;
    --water:#2b6491; --water-bg:#e9f0f6; --warn:#a63c26;
  }}
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{
    font-family:'맑은 고딕','Malgun Gothic',sans-serif;
    color:var(--ink); background:#fff; padding:18px 20px;
    width:1180px; font-variant-numeric:tabular-nums;
  }}
  .wrap {{ display:grid; grid-template-columns:1fr 1fr; gap:26px; }}
  .panel {{ border:1px solid var(--line); border-radius:6px; padding:16px 18px; }}
  h2 {{ font-size:15px; letter-spacing:-.01em; margin-bottom:2px; }}
  .sub {{ font-size:11.5px; color:var(--muted); margin-bottom:14px; }}

  table.cm {{ border-collapse:collapse; width:100%; }}
  table.cm th, table.cm td {{
    border:1px solid var(--line); padding:9px 6px; text-align:center; font-size:13px;
  }}
  table.cm th {{ background:#fafbfa; color:var(--ink-2); font-size:11.5px; font-weight:600; }}
  table.cm td {{ font-size:17px; font-weight:700; }}
  table.cm td.hi {{ background:var(--water-bg); color:var(--water); }}
  table.cm td.z  {{ color:#c4ccc7; font-weight:400; }}
  .corner {{ background:#fff !important; border:none !important; }}

  .big {{ display:flex; align-items:baseline; gap:9px; margin-top:14px; }}
  .big b {{ font-size:30px; color:var(--water); letter-spacing:-.02em; }}
  .big span {{ font-size:11.5px; color:var(--muted); }}

  .bars {{ display:flex; align-items:flex-end; gap:7px; height:132px; margin:6px 0 4px; }}
  .bar {{ flex:1; display:flex; flex-direction:column; justify-content:flex-end; align-items:center; }}
  .bar i {{ width:100%; background:var(--green-2); border-radius:2px 2px 0 0; display:block; }}
  .bar i.pale {{ background:#cfe0d6; }}
  .bar em {{ font-style:normal; font-size:10px; color:var(--muted); margin-top:5px; }}
  .bar u {{ text-decoration:none; font-size:10.5px; color:var(--ink-2); margin-bottom:3px; }}
  .axis {{ display:flex; justify-content:space-between; font-size:10px; color:var(--muted);
           border-top:1px solid var(--line-2); padding-top:5px; }}
  .note {{ font-size:11px; color:var(--muted); margin-top:12px; line-height:1.55; }}
  .warn {{ color:var(--warn); }}
</style>
<div class="wrap">

  <div class="panel">
    <h2>검증된 것 — 수면 유무 판정</h2>
    <div class="sub">습지 {V['n_wetlands_validated']}개소 · 짝지은 관측 {ALL['n']:,}건 · 시간차 ±{V.get('max_offset_days',3)}일</div>
    <table class="cm">
      <tr>
        <th class="corner"></th>
        <th colspan="2">Sentinel-2 광학</th>
      </tr>
      <tr>
        <th class="corner"></th><th>수면 있음</th><th>수면 없음</th>
      </tr>
      <tr>
        <th>레이더<br>수면 있음</th>
        {cell(ALL['presence_table']['둘다_수면'])}
        {cell(ALL['presence_table']['SAR만'])}
      </tr>
      <tr>
        <th>레이더<br>수면 없음</th>
        {cell(ALL['presence_table']['광학만'])}
        {cell(ALL['presence_table']['둘다_없음'])}
      </tr>
    </table>
    <div class="big"><b>{OPEN['presence_agreement']}</b>
      <span>개방수면 구간 일치율 (n={OPEN['n']:,})</span></div>
    <div class="note">원리가 다른 두 센서가 독립적으로 같은 판정을 내렸습니다.
      시간차를 벌려도 흔들리지 않습니다 — 0일 {V['by_offset']['0일']['presence_agreement']},
      1일 {V['by_offset']['1일']['presence_agreement']},
      2~3일 {V['by_offset']['2~3일']['presence_agreement']}.</div>
  </div>

  <div class="panel">
    <h2>검증되지 않은 것 — 개방수면 면적</h2>
    <div class="sub">습지별 결정계수(R²) 분포 · {AREA['n_wetlands']}개소</div>
    <div class="bars">
      {''.join(
        f'<div class="bar"><u>{n if n else ""}</u>'
        f'<i class="{"" if i < 5 else "pale"}" style="height:{max(2, round(n / BMAX * 108))}px"></i>'
        f'<em>{i/10:.1f}</em></div>'
        for i, n in enumerate(BINS))}
    </div>
    <div class="axis"><span>0.0 — 시간 변동을 전혀 설명하지 못함</span><span>1.0</span></div>
    <div class="big"><b class="warn">{AREA['wetland_r2_median']}</b>
      <span>중앙값 · R² 0.5 이상은 {AREA['wetland_r2_ge_05']}개소뿐</span></div>
    <div class="note">면적의 <b>수준</b>은 치우침이 없으나(평균비 {AREA['level_ratio_median']}),
      <b>시간 변동</b>은 따라가지 못합니다. 그래서 면적을 측정값으로 제시하지 않고
      습지 안의 상대 지수로만 표시합니다.</div>
  </div>

</div>
"""


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "figures")
    out.mkdir(parents=True, exist_ok=True)
    tmp = out / "_validation.html"
    tmp.write_text(HTML, encoding="utf-8")

    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": 1180, "height": 460}, device_scale_factor=2)
        pg.goto(tmp.resolve().as_uri())
        pg.wait_for_timeout(600)
        el = pg.query_selector(".wrap")
        el.screenshot(path=out / "fig4_validation.png")
        b.close()
    tmp.unlink()
    f = out / "fig4_validation.png"
    print(f"작성: {f}  {f.stat().st_size/1024:.0f} KB")
    print(f"  일치율 {OPEN['presence_agreement']} (n={OPEN['n']:,}) · R² 중앙 {AREA['wetland_r2_median']}")


if __name__ == "__main__":
    main()
