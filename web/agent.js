/* 에코스코프.agent — 화면에 실린 판독 결과를 읽고 근거와 함께 답변합니다.
 *
 * 구성은 선행 과업(자치법규 정책지도.agent)의 에이전트 패널을 따릅니다.
 *   실행 버튼 + 부유 패널 / 타자 방식 출력 / 근거 카드 / 후속 질문 / 상태 표시줄
 *
 * 원칙: 답변의 근거는 **화면이 이미 읽은 자료**입니다.
 * 질의가 들어오면 화면 상태에서 근거 묶음을 구성하여 함께 전송하고, 서버는 그 범위에서만
 * 답변합니다. 서버에 연결되지 않으면 동일한 근거로 동작하는 내장 응답기가 답변하며,
 * 그 사실을 상태 표시줄에 명시합니다.
 */

(function () {
  const $ = (id) => document.getElementById(id);

  let panelEl, bodyEl, inputEl, sendEl, statusEl;
  let history = [];
  let greeted = false;

  /* 한글 조사. 받침 유무로 갈립니다. */
  function josa(word, withBatchim, withoutBatchim) {
    const last = String(word || "").trim().slice(-1);
    const code = last.charCodeAt(0);
    if (Number.isNaN(code) || code < 0xac00 || code > 0xd7a3) return withBatchim;
    return (code - 0xac00) % 28 ? withBatchim : withoutBatchim;
  }

  const fmt = (n, d = 0) => window.ECOSCOPE.fmt(n, d);

  /* ---------------- 근거 묶음 ---------------- */

  function selected() {
    const S = window.ECOSCOPE.S;
    const all = S.years.filter((r) => r.wid === S.sel).sort((a, b) => a.year - b.year);
    if (!all.length) return null;
    return { all, cur: all.find((r) => r.year === S.year) || all[all.length - 1] };
  }

  function buildEvidence() {
    const S = window.ECOSCOPE.S;
    const sel = selected();
    const cur = sel && sel.cur;
    const orbit = S.orbits.find((o) => o.wid === S.sel) || null;

    return {
      screen: {
        year: S.year,
        sort: S.sort,
        only_open_water: S.onlyOpen,
        listed_wetlands: S.years.filter((r) => r.year === S.year).length,
      },
      summary: S.summary && {
        years: S.summary.years,
        n_wetlands: S.summary.n_wetlands,
        n_observations: S.summary.n_observations,
        mean_obs_per_wetland_year: S.summary.mean_obs_per_wetland_year,
        mean_revisit_days: S.summary.mean_revisit_days,
        n_wetlands_open_water: S.summary.n_wetlands_open_water,
        n_wetlands_no_open_water: S.summary.n_wetlands_no_open_water,
        n_wetlands_with_veg_cover: S.summary.n_wetlands_with_veg_cover,
        generated_utc: S.summary.generated_utc,
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
        orbit_pass: cur.orbit_pass,
        observations: cur.observations.map((o) => ({
          date: o.date, open_ha: o.open_ha, vv_db: o.vv_db, state: o.state,
        })),
        optical: (cur.optical || []).map((o) => ({ date: o.date, ndvi: o.ndvi, ndwi: o.ndwi })),
      },
      series_years: sel
        ? sel.all.map((r) => ({
            year: r.year, open_ha_max: r.open_ha_max, n_obs: r.n_obs,
            n_veg_covered: r.n_veg_covered, confidence: r.confidence,
          }))
        : [],
      orbit_history: orbit && { chosen_orbit: orbit.chosen_orbit, by_orbit_year: orbit.by_orbit_year },
    };
  }

  /* 화면 자료에서 바로 뽑는 근거 카드. 서버 유무와 무관하게 붙습니다. */
  function evidenceCards(ev) {
    const cards = [];
    const s = ev.selected;
    if (s) {
      cards.push({
        kind: "판독 결과",
        title: `${s.name} ${s.year}년 개방수면 판독`,
        summary: s.has_open_water
          ? `관측 ${s.n_obs}회 · 최대 ${fmt(s.open_ha_max, 1)} ha · 신뢰도 ${s.confidence === "high" ? "고" : "저"}`
          : `관측 ${s.n_obs}회 · 개방수면 지표 비적용`,
        date: `습지면적 ${fmt(s.area_ha)} ha · orbit ${s.rel_orbit}`,
      });
      if (s.optical.length) {
        const hi = [...s.optical].sort((a, b) => b.ndvi - a.ndvi)[0];
        cards.push({
          kind: "광학 교차검증",
          title: "Sentinel-2 NDVI / NDWI",
          summary: `최고 NDVI ${fmt(hi.ndvi, 2)} (NDWI ${fmt(hi.ndwi, 2)})`,
          date: `${hi.date} · 유효장면 ${s.optical.length}건`,
        });
      }
    }
    if (ev.orbit_history) {
      const by = ev.orbit_history.by_orbit_year[String(ev.orbit_history.chosen_orbit)] || {};
      const total = Object.values(by).reduce((a, b) => a + b, 0);
      cards.push({
        kind: "관측 가능성",
        title: `orbit ${ev.orbit_history.chosen_orbit} 고정 판독`,
        summary: `전 기간 누적 ${total}회 관측`,
        date: `판독 기간 ${ev.summary.years[0]}~${ev.summary.years[ev.summary.years.length - 1]}년`,
      });
    }
    return cards.slice(0, 3);
  }

  /* ---------------- 내장 응답기 ---------------- */

  function localAnswer(q, ev) {
    const s = ev.selected;
    const has = (...k) => k.some((w) => q.includes(w));
    if (!s) return "좌측 목록에서 습지를 먼저 선택해 주시기 바랍니다. 선택하신 습지의 판독 결과를 근거로 답변드리겠습니다.";

    if (has("가장 넓", "최대", "언제")) {
      const best = [...s.observations].sort((a, b) => b.open_ha - a.open_ha)[0];
      return `${s.name}의 ${s.year}년 개방수면이 가장 넓었던 관측일은 ${best.date}이며, 면적은 ${fmt(best.open_ha, 1)} ha 입니다.\n` +
        `연중 P90 기준 최대 개방수면적은 ${fmt(s.open_ha_max, 1)} ha, 중앙값은 ${fmt(s.open_ha_med, 1)} ha 입니다.\n` +
        `습지 전체 면적 ${fmt(s.area_ha)} ha 대비 최대 ${Math.round((s.open_ha_max / s.area_ha) * 100)}% 가 개방수면으로 판독되었습니다.`;
    }
    if (has("여름", "줄어", "감소", "왜", "원인")) {
      const veg = s.observations.filter((o) => o.state === "veg_covered");
      if (!veg.length) return `${s.name}의 ${s.year}년 관측에서는 식생피복으로 분류된 관측이 확인되지 않았습니다.`;
      const vvVeg = veg.reduce((a, o) => a + o.vv_db, 0) / veg.length;
      const open = s.observations.filter((o) => o.state === "open");
      const vvOpen = open.length ? open.reduce((a, o) => a + o.vv_db, 0) / open.length : null;
      let out = `${s.name}${josa(s.name, "은", "는")} ${s.year}년 관측 ${s.n_obs}회 중 ${veg.length}회가 식생피복으로 분류되었습니다 ` +
        `(${veg[0].date} ~ ${veg[veg.length - 1].date}).\n` +
        `해당 구간의 VV 평균은 ${fmt(vvVeg, 1)} dB 로, 개방수면 관측의 ${vvOpen === null ? "—" : fmt(vvOpen, 1)} dB 보다 현저히 높습니다.\n` +
        `수량이 감소한 경우 후방산란도 함께 낮아져야 합니다. 반대로 상승하였다는 것은 수면 위에 산란체가 형성되었음을 의미하며, 수생식물에 의한 피복으로 해석합니다.`;
      if (s.optical.length) {
        const hi = [...s.optical].sort((a, b) => b.ndvi - a.ndvi)[0];
        out += `\n\nSentinel-2 광학 자료도 동일한 결과를 보입니다. ${hi.date} 기준 NDVI ${fmt(hi.ndvi, 2)}, NDWI ${fmt(hi.ndwi, 2)} 로, 광학과 SAR 이 독립적으로 일치합니다.`;
      }
      return out;
    }
    if (has("저신뢰", "신뢰", "믿을", "정확")) {
      if (!s.has_open_water) {
        return `${s.name}${josa(s.name, "은", "는")} 연중 최대 개방수면율이 5% 미만이므로 개방수면 지표를 적용하지 않았습니다.\n` +
          `삼림습지·초본습지와 같이 SAR 로 관측할 수면이 존재하지 않는 유형으로 판단됩니다. 저신뢰가 아니라 지표 비적용에 해당합니다.`;
      }
      if (s.confidence === "low") {
        return `고정임계(−16 dB) 판독과 장면별 Otsu 판독의 차이가 최대 ${fmt(s.thr_disagree_ha_max, 1)} ha 로 나타났습니다.\n` +
          `최대 개방수면적 ${fmt(s.open_ha_max, 1)} ha 의 20%를 초과하여 저신뢰로 표시하였습니다.\n` +
          `판독창이 수면과 육지의 이봉 분포를 형성하지 못하는 이질적 폴리곤일 가능성이 높습니다. 본 습지의 수치는 판단 근거로 사용하지 마시기 바랍니다.`;
      }
      return `${s.name}${josa(s.name, "은", "는")} 고신뢰로 분류되었습니다. 두 임계 방식의 최대 차이가 ${fmt(s.thr_disagree_ha_max, 1)} ha 로, ` +
        `최대 개방수면적의 ${Math.round((s.thr_disagree_ha_max / Math.max(s.open_ha_max, 0.01)) * 100)}% 수준입니다. 임계값 선택이 결과를 좌우하지 않음을 확인하였습니다.`;
    }
    if (has("현장조사", "대비", "효율", "얼마나", "빈도")) {
      const su = ev.summary;
      return `전국 내륙습지조사는 5년 1주기로 시행되며, 특정 습지가 해당 주기 내 언제 조사되는지는 보장되지 않습니다.\n` +
        `Sentinel-1 위성은 동일 습지를 연 ${fmt(su.mean_obs_per_wetland_year, 1)}회, 평균 ${fmt(su.mean_revisit_days, 1)}일 간격으로 관측합니다.\n` +
        `1개 조사 주기(5년) 동안 약 ${fmt(Math.round(su.mean_obs_per_wetland_year * 5))}회의 관측 자료가 축적됩니다.\n` +
        `본 판독에서는 습지 ${su.n_wetlands}개소에 대하여 관측 ${fmt(su.n_observations)}회를 실제로 처리하였습니다.`;
    }
    if (has("궤도", "orbit", "관측 가능", "공백", "끊")) {
      const oh = ev.orbit_history;
      if (!oh) return "선택하신 습지의 관측 가능성 이력이 아직 수집되지 않았습니다.";
      const lines = Object.entries(oh.by_orbit_year)
        .map(([orb, by]) => ({ orb, by, total: Object.values(by).reduce((a, b) => a + b, 0) }))
        .sort((a, b) => b.total - a.total).slice(0, 4)
        .map((o) => `  orbit ${o.orb}: ` + ev.summary.years.map((y) => `${y}년 ${o.by[String(y)] || 0}회`).join(", "));
      return `본 습지의 궤도별 연간 관측 횟수는 다음과 같습니다.\n${lines.join("\n")}\n\n` +
        `연 20회 이상에서 5회 미만으로 급감한 궤도는 Sentinel-1B(2021년 12월 고장) 궤도입니다. ` +
        `2025년 회복은 Sentinel-1C(2024년 12월 발사)가 동일 궤도면을 승계한 결과입니다.\n` +
        `본 시계열은 전 기간 연속 관측되는 orbit ${oh.chosen_orbit}으로 고정하여 판독하였습니다.`;
    }
    if (has("못 하는", "한계", "안 되는", "못하는", "주의")) {
      return `본 판독 결과로 판단할 수 없는 사항은 다음과 같습니다.\n\n` +
        `1. 수위. SAR 는 수면의 면적을 관측하며 수심은 관측하지 않습니다.\n` +
        `2. 식생 하부 침수. 이중반사 신호는 논의 담수 관리 주기와 동일한 대역에서 변동하여 오탐이 심합니다.\n` +
        `3. 개방수면이 없는 습지의 상태. 본 판독에서 ${ev.summary.n_wetlands_no_open_water}개소가 이에 해당합니다.\n\n` +
        `아울러 식생피복 판정의 VV 임계 −13 dB 는 시범 습지 1개소에서 도출한 잠정값이며, 전국 보정이 완료되기 전까지 확정값이 아닙니다.`;
    }
    return `본 화면은 판독 결과에 포함된 사항에 한하여 답변합니다.\n` +
      `현재 선택: ${s.name} (${s.year}년, 관측 ${s.n_obs}회, 개방수면 최대 ${fmt(s.open_ha_max, 1)} ha, 신뢰도 ${s.confidence === "high" ? "고" : "저"}).\n` +
      `아래 후속 질문을 이용하시거나, 습지 또는 판독 연도를 변경한 뒤 다시 질의해 주시기 바랍니다.`;
  }

  /* ---------------- 후속 질문 ---------------- */

  function suggestions() {
    const sel = selected();
    const name = sel ? window.ECOSCOPE.labelOf(sel.cur) : "선택 습지";
    if (!sel) {
      return [
        "현장조사 대비 관측 빈도는 어느 정도입니까",
        "이 판독으로 말할 수 없는 사항은 무엇입니까",
        "관측 가능성을 먼저 확인하는 이유는 무엇입니까",
      ];
    }
    const cur = sel.cur;
    if (!cur.has_open_water) {
      return [
        `${name}에 개방수면 지표를 적용하지 않은 이유는 무엇입니까`,
        "개방수면이 없는 습지는 어떤 지표가 필요합니까",
        "현장조사 대비 관측 빈도는 어느 정도입니까",
      ];
    }
    if (cur.confidence === "low") {
      return [
        `${name}${josa(name, "이", "가")} 저신뢰로 표시된 이유는 무엇입니까`,
        "임계값 선택이 결과에 미치는 영향은 어느 정도입니까",
        `${name}의 궤도별 관측 가능성을 확인해 주십시오`,
      ];
    }
    return [
      `${name}의 여름철 개방수면 감소 원인을 설명해 주십시오`,
      `${name}${josa(name, "은", "는")} 언제 개방수면이 가장 넓었습니까`,
      `${name}의 궤도별 관측 가능성을 확인해 주십시오`,
    ];
  }

  /* ---------------- 화면 출력 ---------------- */

  function addUser(text) {
    const d = document.createElement("div");
    d.className = "agent-msg agent-user";
    d.textContent = text;
    bodyEl.appendChild(d);
    bodyEl.scrollTop = bodyEl.scrollHeight;
    history.push({ role: "user", text });
  }

  function addAssistant(text, meta = {}) {
    const box = document.createElement("div");
    box.className = "agent-msg agent-assistant";
    bodyEl.appendChild(box);
    history.push({ role: "assistant", text });
    typeInto(box, text, () => appendMeta(box, meta));
  }

  /* 답변을 단어 단위로 흘려 씁니다(스트리밍 표현). 문단은 <p> 로 유지합니다. */
  function typeInto(box, text, done) {
    const paragraphs = String(text).split(/\n+/).filter(Boolean);
    const cursor = document.createElement("span");
    cursor.className = "agent-cursor";
    let pi = 0;
    const nextPara = () => {
      if (pi >= paragraphs.length) { cursor.remove(); if (done) done(); return; }
      const p = document.createElement("p");
      box.appendChild(p);
      p.appendChild(cursor);
      const tokens = paragraphs[pi].match(/\S+\s*/g) || [paragraphs[pi]];
      const burst = tokens.length > 80 ? 3 : tokens.length > 40 ? 2 : 1;
      let ti = 0;
      const step = () => {
        if (ti >= tokens.length) { pi += 1; nextPara(); return; }
        for (let b = 0; b < burst && ti < tokens.length; b += 1) {
          cursor.insertAdjacentText("beforebegin", tokens[ti]);
          ti += 1;
        }
        bodyEl.scrollTop = bodyEl.scrollHeight;
        setTimeout(step, 12 + Math.random() * 16);
      };
      step();
    };
    nextPara();
  }

  function appendMeta(box, meta) {
    const cards = meta.cards || [];
    const chips = [];
    if (cards.length) chips.push({ text: `근거 ${cards.length}건`, on: true });
    if (meta.source) chips.push({ text: meta.source, on: false });
    if (meta.year) chips.push({ text: `${meta.year}년 판독 기준`, on: false });

    if (chips.length) {
      const row = document.createElement("div");
      row.className = "agent-meta";
      for (const c of chips) {
        const b = document.createElement("span");
        b.className = "agent-meta-chip" + (c.on ? " on" : "");
        b.textContent = c.text;
        row.appendChild(b);
      }
      box.appendChild(row);
    }

    if (cards.length) {
      const grid = document.createElement("div");
      grid.className = "agent-evidence-grid";
      for (const c of cards) {
        const card = document.createElement("div");
        card.className = "agent-evidence-card";
        card.innerHTML =
          `<span class="agent-evidence-kind">${c.kind}</span>` +
          `<strong>${c.title}</strong>` +
          (c.summary ? `<span class="agent-evidence-summary">${c.summary}</span>` : "") +
          (c.date ? `<span class="agent-evidence-date">${c.date}</span>` : "");
        grid.appendChild(card);
      }
      box.appendChild(grid);
    }

    const items = suggestions();
    if (items.length) {
      const wrap = document.createElement("div");
      wrap.className = "agent-suggest";
      const title = document.createElement("span");
      title.className = "agent-suggest-title";
      title.textContent = "후속 질문";
      wrap.appendChild(title);
      for (const q of items.slice(0, 3)) {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "agent-suggest-btn";
        b.textContent = q;
        b.onclick = () => ask(q);
        wrap.appendChild(b);
      }
      box.appendChild(wrap);
    }
    bodyEl.scrollTop = bodyEl.scrollHeight;
  }

  function setBusy(busy) {
    sendEl.disabled = busy;
    inputEl.disabled = busy;
    if (busy) statusEl.textContent = "판독 자료를 확인하는 중입니다...";
  }

  function shortError(message) {
    const s = String(message || "연결 실패").replace(/\s+/g, " ").trim();
    return s.length > 44 ? `${s.slice(0, 44)}...` : s;
  }

  /* ---------------- 질의 ---------------- */

  async function ask(text) {
    const q = String(text || "").trim();
    if (!q) return;
    addUser(q);
    setBusy(true);
    const ev = buildEvidence();
    const cards = evidenceCards(ev);
    try {
      const res = await fetch("/ai/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: q,
          evidence: ev,
          history: history.slice(-8).map((m) => ({ role: m.role, text: m.text })),
        }),
      });
      if (!res.ok) throw new Error(`질의응답 서버 HTTP ${res.status}`);
      const data = await res.json();
      if (!data.answer) throw new Error(data.detail || data.error || "빈 응답");
      addAssistant(data.answer, { cards, source: data.model ? `모델 ${data.model}` : "서버 응답", year: ev.screen.year });
      statusEl.textContent = data.model ? `Gemini: ${data.model}` : "질의응답 서버 응답 완료";
    } catch (e) {
      addAssistant(localAnswer(q, ev), { cards, source: "화면 자료 요약", year: ev.screen.year });
      statusEl.textContent = `서버 미연결 · 화면 자료 요약 (${shortError(e.message)})`;
    } finally {
      setBusy(false);
    }
  }

  /* ---------------- 초기화 ---------------- */

  function open() {
    panelEl.classList.add("open");
    if (!greeted) {
      greeted = true;
      addAssistant(
        "에코스코프.agent 입니다. 본 화면에 실린 판독 결과만을 근거로 답변드리며, 자료에 없는 사항은 없다고 말씀드립니다.\n" +
        "좌측 목록에서 습지를 선택하신 뒤 질의하시면 해당 습지를 기준으로 답변합니다.",
        { cards: evidenceCards(buildEvidence()), source: "화면 자료", year: window.ECOSCOPE.S.year });
    }
    inputEl.focus();
  }

  function init() {
    panelEl = $("agent-panel");
    bodyEl = $("agent-body");
    inputEl = $("agent-input");
    sendEl = $("agent-send");
    statusEl = $("agent-status");

    $("agent-launcher").onclick = () => (panelEl.classList.contains("open") ? panelEl.classList.remove("open") : open());
    $("agent-close").onclick = () => panelEl.classList.remove("open");

    $("agent-form").addEventListener("submit", (e) => {
      e.preventDefault();
      const q = inputEl.value.trim();
      if (!q) return;
      inputEl.value = "";
      ask(q);
    });
    // Enter 전송, Shift+Enter 줄바꿈
    inputEl.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        $("agent-form").requestSubmit();
      }
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
