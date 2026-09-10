"""제안서에 넣을 화면 캡처를 만듭니다.

    python scripts/capture_figures.py [출력폴더]

세 장만 뽑습니다. 제안서 분량이 3페이지라 그림이 늘어나면 본문이 밀립니다.
    fig1  실행 화면 전체      — '개념이 아니라 동작한다'를 한 장으로 보임
    fig2  관측 달력          — 5년 주기와 12.3일 간격의 대비가 눈으로 보이는 곳
    fig3  판독 결과 + 교차검증 — 시계열에 광학(NDVI)이 겹쳐 있는 화면

캡처 전에 에이전트 버튼처럼 심사와 무관한 요소는 숨깁니다.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright  # noqa: E402

URL = "https://ecoscope-nie.vercel.app/"
VIEW = {"width": 1560, "height": 1000}
SCALE = 2                      # 인쇄용이라 2배로 뜹니다


def hide_chrome(page) -> None:
    page.evaluate("""() => {
      for (const s of ['#agent-launcher', '#agent-panel', '#drawer']) {
        const el = document.querySelector(s);
        if (el) el.style.display = 'none';
      }
    }""")


def pick(page, name: str) -> None:
    """이름으로 습지를 고릅니다. 없으면 첫 성립 습지."""
    page.evaluate("""(nm) => {
      const S = window.ECOSCOPE.S;
      const hit = S.points.find(p => p.name && p.name.includes(nm))
               || S.years.find(y => y.has_open_water);
      window.ECOSCOPE.select(hit.wid);
    }""", name)
    page.wait_for_timeout(900)


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "figures")
    out.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        b = pw.chromium.launch()
        page = b.new_page(viewport=VIEW, device_scale_factor=SCALE)
        page.goto(URL, wait_until="networkidle", timeout=90_000)
        page.wait_for_function("window.ECOSCOPE && window.ECOSCOPE.S.years.length > 0",
                               timeout=60_000)
        page.wait_for_timeout(1500)
        hide_chrome(page)

        # fig1 — 실행 화면 전체(상단 지표 + 좌측 목록 + 달력)
        page.screenshot(path=out / "fig1_screen.png")
        print("fig1 실행 화면")

        # 상단 헤더가 sticky 라 요소 캡처에 겹쳐 들어옵니다. fig1 은 이미 찍었으니 감춥니다.
        page.evaluate("() => { const t=document.querySelector('.top'); if(t) t.style.display='none'; }")

        # fig2 — 관측 달력. 카드째로 잡아 범례와 설명까지 들어가게 합니다.
        # 스크롤 칸을 그대로 두면 마지막 행이 반쯤 잘리므로, 행 간격을 재서
        # 딱 떨어지는 높이로 맞춥니다.
        page.evaluate("""(rows) => {
          const svg = document.querySelector('#calendar svg');
          const ys = [...svg.querySelectorAll('text')]
            .map(t => +t.getAttribute('y')).filter(Number.isFinite).sort((a,b)=>a-b);
          const uniq = [...new Set(ys)];
          let pitch = 0;
          for (let i = 1; i < uniq.length; i++) {
            const d = uniq[i] - uniq[i-1];
            if (d > 4) { pitch = d; break; }
          }
          const top = uniq.find(y => y > 20) ?? 40;
          const wrap = document.querySelector('.calendar-wrap');
          // pitch 의 절반을 빼 마지막 행이 걸치지 않게 합니다.
          wrap.style.maxHeight = (top + pitch * rows - pitch * 0.45) + 'px';
          wrap.style.overflow = 'hidden';
        }""", 18)
        page.wait_for_timeout(400)
        card = page.query_selector(".calendar-wrap")
        card.evaluate("el => el.closest('.card').scrollIntoView()")
        page.wait_for_timeout(300)
        page.query_selector(".calendar-wrap").evaluate("el => el.closest('.card')")
        cal_card = page.query_selector("#calendar")
        cal_card.evaluate("el => el.closest('.card').setAttribute('data-fig','1')")
        page.query_selector("[data-fig='1']").screenshot(path=out / "fig2_calendar.png")
        print("fig2 관측 달력")

        # fig3 — 판독 결과 + 광학 교차검증. 광학이 실린 습지를 고릅니다.
        page.evaluate("""() => {
          const S = window.ECOSCOPE.S;
          const withOpt = S.years.find(y => y.year === S.year && y.has_open_water
                                         && y.optical && y.optical.length > 20);
          if (withOpt) window.ECOSCOPE.select(withOpt.wid);
        }""")
        page.wait_for_timeout(1200)
        # 행 전체를 잡으면 좌우 카드 높이 차이만큼 빈 공간이 남습니다. 시계열 카드만.
        card = page.query_selector(".card.grow")
        card.screenshot(path=out / "fig3_timeseries.png")
        print("fig3 판독 결과 · 교차검증")

        for f in sorted(out.glob("fig*.png")):
            print(f"   {f.name}  {f.stat().st_size/1024:.0f} KB")
        b.close()


if __name__ == "__main__":
    main()
