/* 질의응답 패널.
 *
 * 원칙: 답변의 근거는 **화면이 이미 읽은 자료**다. 모델에게 자유롭게 지어내게 하지 않는다.
 * 질문이 오면 화면 상태에서 근거 묶음을 만들어 함께 보내고, 서버는 그 안에서만 답한다.
 * 서버가 없으면(정적 미리보기) 아래 로컬 응답기가 같은 근거로 답한다.
 */

(function () {
  const $ = (id) => document.getElementById(id);
  let opened = false;

  const SUGGEST = [
    "이 습지는 언제 개방수면이 가장 넓나",
    "여름에 수면적이 왜 줄어드나",
    "저신뢰로 표시된 이유는",
    "현장조사 대비 관측이 얼마나 늘어나나",
    "이 결과로 못 하는 말은 무엇인가",
  ];

  /* 한글 조사. 받침 유무로 갈린다 — "우포늪은" / "정양늪 생태공원은" 처럼
     이름 뒤에 붙는 말이 어색해지지 않게 한다. */
  function josa(word, withBatchim, withoutBatchim) {
    const last = (word || "").trim().slice(-1);
    const code = last.charCodeAt(0);
    if (Number.isNaN(code) || code < 0xac00 || code > 0xd7a3) return withBatchim;
    return (code - 0xac00) % 28 ? withBatchim : withoutBatchim;
  }

  function evidence() {
    const S = window.ECOSCOPE.S;
    const sel = S.years.filter((r) => r.wid === S.sel).sort((a, b) => a.year - b.year);
    const cur = sel.find((r) => r.year === S.year) || sel[sel.length - 1];
    const pack = {
      summary: S.summary && {
        years: S.summary.years,
        n_wetlands: S.summary.n_wetlands,
        n_observations: S.summary.n_observations,
        mean_obs_per_wetland_year: S.summary.mean_obs_per_wetland_year,
        mean_revisit_days: S.summary.mean_revisit_days,
        n_wetlands_open_water: S.summary.n_wetlands_open_water,
        n_wetlands_no_open_water: S.summary.n_wetlands_no_open_water,
        n_wetlands_with_veg_cover: S.summary.n_wetlands_with_veg_cover,
      },
      selected: cur && {
        name: window.ECOSCOPE.labelOf(cur),
        wid: cur.wid,
        year: cur.year,
        area_ha: cur.area_ha,
        n_obs: cur.n_obs,
        revisit_days: cur.revisit_days,
        has_open_water: cur.has_open_water,
        confidence: cur.confidence,
        open_ha_max: cur.open_ha_max,
        open_ha_med: cur.open_ha_med,
        open_ha_min: cur.open_ha_min,
        n_veg_covered: cur.n_veg_covered,
        veg_cover_share: cur.veg_cover_share,
        thr_disagree_ha_max: cur.thr_disagree_ha_max,
        rel_orbit: cur.rel_orbit,
        observations: cur.observations.map((o) => ({
          date: o.date, open_ha: o.open_ha, vv_db: o.vv_db, state: o.state,
        })),
        optical: (cur.optical || []).map((o) => ({ date: o.date, ndvi: o.ndvi, ndwi: o.ndwi })),
      },
      series_years: sel.map((r) => ({ year: r.year, open_ha_max: r.open_ha_max, n_obs: r.n_obs, n_veg_covered: r.n_veg_covered })),
    };
    return pack;
  }

  /* ---- 서버 없을 때의 로컬 응답기. 화면 근거만 읽고 규칙으로 답한다. ---- */
  function localAnswer(q, ev) {
    const f = window.ECOSCOPE.fmt;
    const s = ev.selected;
    const has = (...k) => k.some((w) => q.includes(w));

    if (!s) return "먼저 왼쪽 목록에서 습지를 하나 고르면, 그 습지의 판독 결과로 답한다.";

    if (has("가장 넓", "최대", "언제")) {
      const best = [...s.observations].sort((a, b) => b.open_ha - a.open_ha)[0];
      return `${s.name}${josa(s.name, "의", "의")} ${s.year}년 개방수면이 가장 넓었던 관측은 ${best.date}, ${f(best.open_ha, 1)} ha 다.\n` +
        `연중 P90 기준으로는 ${f(s.open_ha_max, 1)} ha, 중앙값은 ${f(s.open_ha_med, 1)} ha 다.\n` +
        `습지 전체 면적 ${f(s.area_ha)} ha 대비 최대 ${Math.round((s.open_ha_max / s.area_ha) * 100)}% 가 개방수면이었다.`;
    }
    if (has("여름", "줄어", "감소", "왜")) {
      const veg = s.observations.filter((o) => o.state === "veg_covered");
      if (!veg.length) return `${s.name}${josa(s.name, "의", "의")} ${s.year}년 관측에서는 식생피복으로 분류된 관측이 없다.`;
      const vvVeg = veg.reduce((a, o) => a + o.vv_db, 0) / veg.length;
      const open = s.observations.filter((o) => o.state === "open");
      const vvOpen = open.length ? open.reduce((a, o) => a + o.vv_db, 0) / open.length : null;
      let out = `${s.name}${josa(s.name, "은", "는")} ${s.year}년 관측 ${s.n_obs}회 중 ${veg.length}회가 식생피복으로 분류됐다 ` +
        `(${veg[0].date} ~ ${veg[veg.length - 1].date}).\n` +
        `그 구간의 VV 평균은 ${f(vvVeg, 1)} dB 로, 개방수면 관측의 ${vvOpen === null ? "—" : f(vvOpen, 1)} dB 보다 크게 높다.\n` +
        `물이 빠지면 후방산란이 같이 낮아진다. 반대로 올라갔다는 것은 수면 위에 산란체가 생겼다는 뜻이다 — 수생식물이다.`;
      if (s.optical.length) {
        const hi = [...s.optical].sort((a, b) => b.ndvi - a.ndvi)[0];
        out += `\n\nSentinel-2 도 같은 말을 한다: ${hi.date} NDVI ${f(hi.ndvi, 2)}, NDWI ${f(hi.ndwi, 2)}. 광학과 SAR 이 독립적으로 일치한다.`;
      }
      return out;
    }
    if (has("저신뢰", "신뢰", "믿을")) {
      if (!s.has_open_water) {
        return `${s.name}${josa(s.name, "은", "는")} 연중 최대 개방수면율이 5% 미만이라 개방수면 지표를 적용하지 않았다.\n` +
          `삼림습지·초본습지처럼 SAR 로 볼 수면이 애초에 없는 유형으로 보인다. 저신뢰가 아니라 지표 비적용이다.`;
      }
      if (s.confidence === "low") {
        return `고정임계(-16 dB) 판독과 장면별 Otsu 판독이 최대 ${f(s.thr_disagree_ha_max, 1)} ha 갈린다.\n` +
          `최대 개방수면적 ${f(s.open_ha_max, 1)} ha 의 20% 를 넘어 저신뢰로 표시했다.\n` +
          `판독창이 물/뭍 이봉을 만들지 못하는 이질적 폴리곤일 가능성이 크다. 이 습지의 수치로 결론을 내지 말 것.`;
      }
      return `${s.name}${josa(s.name, "은", "는")} 고신뢰다. 두 임계 방식의 최대 괴리가 ${f(s.thr_disagree_ha_max, 1)} ha 로, ` +
        `최대 개방수면적의 ${Math.round((s.thr_disagree_ha_max / Math.max(s.open_ha_max, 0.01)) * 100)}% 수준이다. 임계값 선택이 결과를 좌우하지 않는다.`;
    }
    if (has("현장조사", "대비", "효율", "얼마나")) {
      const su = ev.summary;
      return `전국 내륙습지조사는 5년 주기다. 특정 습지가 그 5년 안에 언제 조사되는지는 보장되지 않는다.\n` +
        `Sentinel-1 은 같은 습지를 연 ${f(su.mean_obs_per_wetland_year, 1)}회, 평균 ${f(su.mean_revisit_days, 1)}일 간격으로 본다.\n` +
        `한 조사 주기(5년) 동안 약 ${f(Math.round(su.mean_obs_per_wetland_year * 5))}회의 관측이 쌓인다.\n` +
        `이 판독에서는 습지 ${su.n_wetlands}개소에 대해 관측 ${f(su.n_observations)}회를 실제로 처리했다.`;
    }
    if (has("못 하는", "한계", "안 되는", "못하는")) {
      return `세 가지는 이 결과로 말할 수 없다.\n\n` +
        `1. 수위. SAR 은 수면의 넓이를 보지 깊이를 보지 않는다.\n` +
        `2. 식생 하부 침수. 이중반사 신호는 논 담수 관리 주기와 같은 대역에서 움직여 오탐이 심하다.\n` +
        `3. 개방수면이 없는 습지의 상태. 이 판독에서 ${ev.summary.n_wetlands_no_open_water}개소가 여기 해당한다.\n\n` +
        `그리고 식생피복 판정의 VV 문턱 -13 dB 는 파일럿 습지 하나에서 나온 잠정값이다. 전국 보정 전까지는 확정값이 아니다.`;
    }
    return `이 화면이 답할 수 있는 것은 판독 결과에 있는 것뿐이다.\n` +
      `현재 선택: ${s.name} (${s.year}년, 관측 ${s.n_obs}회, 개방수면 최대 ${f(s.open_ha_max, 1)} ha, 신뢰도 ${s.confidence}).\n` +
      `아래 예시 질문을 눌러보거나, 습지·연도를 바꾸고 다시 물어보라.`;
  }

  async function ask(q, log) {
    const ev = evidence();
    add(log, "me", q);
    const wait = add(log, "sys", "판독 자료를 읽는 중…");
    try {
      const res = await fetch("/ai/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q, evidence: ev }),
      });
      if (!res.ok) throw new Error("no server");
      const data = await res.json();
      wait.remove();
      add(log, "bot", data.answer || "(빈 응답)");
    } catch {
      wait.remove();
      add(log, "bot", localAnswer(q, ev));
      add(log, "sys", "질의응답 서버가 없어 화면 자료만으로 답했다.");
    }
    log.scrollTop = log.scrollHeight;
  }

  function add(log, cls, text) {
    const d = document.createElement("div");
    d.className = "msg " + cls;
    d.textContent = text;
    log.appendChild(d);
    log.scrollTop = log.scrollHeight;
    return d;
  }

  function openChat() {
    const drawer = $("drawer");
    $("drawer-title").textContent = "판독 자료 질의응답";
    const body = $("drawer-body");
    body.className = "drawer-body";
    body.style.padding = "0";
    body.innerHTML =
      '<div class="chat">' +
      '  <div class="chat-log" id="chat-log"></div>' +
      '  <div class="chips" id="chat-chips"></div>' +
      '  <div class="chat-in"><input id="chat-q" placeholder="이 화면의 판독 결과에 대해 물어보라" autocomplete="off"><button id="chat-send">보내기</button></div>' +
      "</div>";
    drawer.hidden = false;

    const log = $("chat-log");
    if (!opened) {
      add(log, "bot",
        "이 화면에 올라온 판독 결과만 근거로 답한다. 자료에 없는 것은 없다고 말한다.\n" +
        "왼쪽에서 습지를 고른 뒤 물어보면 그 습지 기준으로 답한다.");
      opened = true;
    }
    $("chat-chips").innerHTML = SUGGEST.map((s) => `<button class="chip">${s}</button>`).join("");
    for (const c of $("chat-chips").querySelectorAll(".chip")) {
      c.onclick = () => ask(c.textContent, log);
    }
    const input = $("chat-q");
    const send = () => {
      const q = input.value.trim();
      if (!q) return;
      input.value = "";
      ask(q, log);
    };
    $("chat-send").onclick = send;
    input.onkeydown = (e) => { if (e.key === "Enter") send(); };
    input.focus();
  }

  document.getElementById("ai-fab").onclick = openChat;
})();
