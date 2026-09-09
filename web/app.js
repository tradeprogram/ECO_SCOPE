/* 에코스코프 — 화면 구성.
 *
 * 이 파일은 수치를 계산하지 않습니다. data/ 의 사전 생성 파일이 유일한 출처입니다.
 *
 * 표기 원칙 — 개방수면 '면적(ha)' 은 검증되지 않았습니다.
 *   독립 센서(Sentinel-2)와 대조한 결과 면적 상관은 R² 0.083 이었고,
 *   면적의 41~87% 가 폴리곤 평균 후방산란으로 설명됐습니다.
 *   따라서 화면은 면적을 측정값으로 제시하지 않고, 같은 습지 안의
 *   **상대 지수(연중 최대 대비 %)** 로만 보여줍니다.
 *   검증된 것은 수면 유무 판정(두 센서 일치율 0.93)과 계절 전환입니다.
 */

const S = {
  summary: null,
  years: [],
  points: [],
  korea: null,
  orbits: [],
  shapes: null,
  validation: null,
  grades: null,
  layer: "",
  year: null,
  sort: "quality",
  onlyOpen: true,
  search: "",
  sel: null,
};

const COLOR = {
  water: "#2b6491",
  waterSoft: "#c7d9e8",
  veg: "#5f8a1c",
  dry: "#b9761b",
  none: "#d3d9d5",
};

const STATE_LABEL = {
  open: "개방수면",
  // 소실의 원인(식생/건조)은 SAR 단독으로 가르지 못한다는 것을 확인했습니다.
  // 화면은 '사라졌다'까지만 말하고, 추정 구분은 괄호로 덧붙입니다.
  veg_covered: "개방수면 소실 (식생 추정)",
  dry_suspect: "개방수면 소실 (산란체 없음)",
  no_open_water: "지표 비적용",
};

const fmt = (n, d = 0) =>
  n === null || n === undefined || Number.isNaN(n)
    ? "—"
    : Number(n).toLocaleString("ko-KR", { minimumFractionDigits: d, maximumFractionDigits: d });

const $ = (id) => document.getElementById(id);
const el = (tag, attrs = {}, kids = []) => {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  for (const kid of [].concat(kids)) node.appendChild(kid);
  return node;
};
const txt = (s) => document.createTextNode(s);

/* ─────────── 자료 ─────────── */

async function boot() {
  const get = (path, fallback) =>
    fetch(path, { cache: "no-cache" }).then((r) => r.json()).catch(() => fallback);

  const [summary, years, points, korea, orbits, shapes, validation, grades] = await Promise.all([
    get("data/summary.json", null),
    get("data/wetland_years.json", []),
    get("data/wetland_points.json", []),
    get("data/korea_adm1.geojson", null),
    get("data/orbit_history.json", []),
    get("data/wetland_shapes.geojson", null),
    get("data/validation.json", null),
    get("data/ecomap_grades.json", null),
  ]);
  Object.assign(S, { summary, years, points, korea, orbits, shapes, validation, grades });
  S.year = summary.years[summary.years.length - 1];

  buildYearSelect();
  renderOverview();
  wireControls();
  renderAll();
}

function buildYearSelect() {
  const sel = $("year-select");
  sel.innerHTML = S.summary.years
    .map((y) => `<option value="${y}"${y === S.year ? " selected" : ""}>${y}년</option>`)
    .join("");
}

/* ─────────── 개요 ─────────── */

const metric = (value, unit, label, cls = "") =>
  `<div class="metric ${cls}"><b>${value}${unit ? `<small>${unit}</small>` : ""}</b>` +
  `<span>${label}</span></div>`;

function renderOverview() {
  const s = S.summary;
  const first = s.years[0], last = s.years[s.years.length - 1];

  $("top-stamp").innerHTML =
    `판독 기간 <b>${first}~${last}</b> · 자료 생성 <b>${s.generated_utc.slice(0, 10)}</b>`;

  $("metrics-obs").innerHTML =
    metric(fmt(s.n_observations), "회", "SAR 관측") +
    metric(fmt(s.n_wetlands), "개소", "판독 습지") +
    metric(fmt(s.mean_revisit_days, 1), "일", "평균 재방문");

  $("metrics-target").innerHTML =
    metric(fmt(s.n_wetlands_open_water), "개소", "개방수면 성립", "water") +
    metric(fmt(s.n_wetlands_with_cover_loss), "개소", "개방수면 소실 관측", "veg") +
    metric(fmt(s.n_wetlands_no_open_water), "개소", "지표 비적용", "mute");

  // 묶은 상관(by_state.open.r2)은 습지 간 크기 차이에 오염되므로 화면에 올리지 않습니다.
  // 습지별 상관의 중앙값만 인용합니다.
  const V = S.validation;
  const v = V && V.by_state && V.by_state.open;
  $("metrics-valid").innerHTML = v
    ? metric(v.presence_agreement.toFixed(2), "", "수면 유무 일치율", "water") +
      metric(fmt(v.n), "건", "대조 관측") +
      metric((V.median_wetland_r2 ?? 0).toFixed(2), "", "면적 R² (중앙값)", "warn")
    : metric("—", "", "검증 자료 없음", "mute");

  const perYear = s.mean_obs_per_wetland_year;
  $("metrics-ratio").innerHTML =
    metric(fmt(Math.round(perYear * 5)), "배", "법정조사 1주기(5년) 관측량") +
    metric(fmt(perYear, 1), "회", "습지당 연 관측") +
    metric(`${first}~${String(last).slice(2)}`, "", "판독 기간");
}

/* ─────────── 목록 ─────────── */

/* 그 습지의 전 기간 최대 개방수면율. 상대 지수의 기준입니다. */
function peakRatio(wid) {
  let peak = 0;
  for (const r of S.years) {
    if (r.wid !== wid) continue;
    for (const o of r.observations) if (o.open_ratio > peak) peak = o.open_ratio;
  }
  return peak;
}

function rowsForYear() {
  let rows = S.years.filter((r) => r.year === S.year);
  if (S.onlyOpen) rows = rows.filter((r) => r.has_open_water);
  if (S.search) {
    const q = S.search.toLowerCase();
    rows = rows.filter((r) => labelOf(r).toLowerCase().includes(q));
  }
  // 고신뢰 우선, 같은 등급 안에서는 개방수면 소실 비중이 큰 순.
  // 첫 화면에 판정 결과가 다양하게 보여야 달력이 무엇을 말하는지 읽힙니다.
  const quality = (r) =>
    (r.confidence === "high" && r.has_open_water ? 0 : 1) * 1e6 -
    Math.round((r.covered_share ?? 0) * 1000);

  const key = {
    quality,
    area: (r) => -r.area_ha,
    obs: (r) => -r.n_obs,
    veg: (r) => -(r.covered_share ?? -1),
  }[S.sort];
  return rows.sort((a, b) => key(a) - key(b));
}

function labelOf(r) {
  return r.name || `무명습지 ${r.wid.split("-").pop().slice(-5)}`;
}

function renderList() {
  const rows = rowsForYear();
  const total = S.years.filter((r) => r.year === S.year).length;
  // 우측 수치가 무엇인지 한 번만 밝혀 둡니다. 열 제목을 따로 두면 목록이 무거워집니다.
  $("rail-count").textContent = S.search
    ? `검색 ${rows.length}개소 · 우측은 개방수면 소실 비중`
    : `${rows.length} / ${total}개소 · ${S.year}년 · 우측은 개방수면 소실 비중`;

  const ul = $("wetland-list");
  ul.innerHTML = "";
  for (const r of rows) {
    const li = document.createElement("li");
    if (S.sel === r.wid) li.className = "on";

    const tags = [];
    if (!r.has_open_water) tags.push('<span class="tag noopen">비적용</span>');
    if (r.has_open_water && r.confidence === "low") tags.push('<span class="tag low">저신뢰</span>');

    const veg = r.covered_share === null || r.covered_share === undefined
      ? "—"
      : Math.round(r.covered_share * 100) + "%";

    li.innerHTML =
      `<div class="wl-name">${labelOf(r)}</div>` +
      `<div class="wl-num">${veg}</div>` +
      `<div class="wl-meta">${fmt(r.area_ha)} ha · 관측 ${r.n_obs}회 ${tags.join(" ")}</div>`;
    li.onclick = () => select(r.wid);
    ul.appendChild(li);
  }
  if (!rows.length) {
    ul.innerHTML = '<li style="color:var(--muted);font-size:12px;cursor:default">해당 습지가 없습니다.</li>';
  }
}

function select(wid) {
  S.sel = wid;
  renderList();
  renderCalendar();
  renderTimeseries();
  renderDetail();
  renderShape();
  renderLocator();
  renderOrbits();
}

/* ─────────── 관측 가능성 ─────────── */

function renderOrbits() {
  const host = $("orbits");
  host.innerHTML = "";
  const rec = S.orbits.find((o) => o.wid === S.sel);
  if (!rec) {
    host.innerHTML = '<p style="color:var(--muted);font-size:12px;margin:0">수집된 이력이 없습니다.</p>';
    $("orbits-meta").textContent = "";
    $("orbits-foot").textContent = "";
    return;
  }

  const years = S.summary.years.map(String);
  const orbits = Object.entries(rec.by_orbit_year)
    .map(([orb, byYear]) => ({ orb: Number(orb), byYear, total: Object.values(byYear).reduce((a, b) => a + b, 0) }))
    .sort((a, b) => b.total - a.total)
    .slice(0, 5);

  host.innerHTML =
    '<table class="orb"><thead><tr><th class="lab">궤도</th>' +
    years.map((y) => `<th>${y}</th>`).join("") +
    "<th>합계</th></tr></thead><tbody>" +
    orbits.map((o) => {
      const chosen = o.orb === rec.chosen_orbit;
      return `<tr class="${chosen ? "chosen" : ""}"><td class="lab">orbit ${o.orb}${chosen ? " · 사용" : ""}</td>` +
        years.map((y) => {
          const n = o.byYear[y] || 0;
          return `<td class="n ${n < 5 ? "gap" : ""}">${n}</td>`;
        }).join("") +
        `<td class="n">${o.total}</td></tr>`;
    }).join("") +
    "</tbody></table>";

  const broken = orbits.filter((o) => {
    const mid = ["2022", "2023", "2024"].map((y) => o.byYear[y] || 0);
    const early = ["2019", "2020", "2021"].map((y) => o.byYear[y] || 0);
    return early.every((n) => n >= 20) && mid.every((n) => n < 5);
  });
  $("orbits-meta").textContent = `orbit ${rec.chosen_orbit} 고정`;
  $("orbits-foot").textContent = broken.length
    ? `orbit ${broken.map((o) => o.orb).join(", ")}은 2022~2024년 관측이 끊겼습니다. Sentinel-1B 소실(2021.12) 궤도입니다.`
    : `궤도를 섞으면 입사각이 달라져 후방산란을 직접 비교할 수 없습니다.`;
}

/* ─────────── 관측 달력 ─────────── */

const MONTHS = ["1월", "2월", "3월", "4월", "5월", "6월", "7월", "8월", "9월", "10월", "11월", "12월"];
const MAX_CAL_ROWS = 40;

function dayOfYear(iso) {
  const d = new Date(iso + "T00:00:00Z");
  return Math.round((d.getTime() - Date.UTC(d.getUTCFullYear(), 0, 1)) / 86400000);
}

function cellColor(o, baseline) {
  if (o.state === "no_open_water") return COLOR.none;
  if (o.state === "veg_covered") return COLOR.veg;
  if (o.state === "dry_suspect") return COLOR.dry;
  const t = baseline > 0 ? Math.min(1, o.open_ratio / baseline) : 0;
  return mix(COLOR.waterSoft, COLOR.water, 0.25 + 0.75 * t);
}

function mix(a, b, t) {
  const p = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
  const [r1, g1, b1] = p(a), [r2, g2, b2] = p(b);
  const c = (x, y) => Math.round(x + (y - x) * t);
  return `rgb(${c(r1, r2)},${c(g1, g2)},${c(b1, b2)})`;
}

function renderCalendar() {
  $("legend").innerHTML = [
    [COLOR.water, "개방수면"],
    [COLOR.veg, "소실 (식생 추정)"],
    [COLOR.dry, "소실 (산란체 없음)"],
    [COLOR.none, "지표 비적용"],
  ].map(([c, t]) => `<span><i style="background:${c}"></i>${t}</span>`).join("");

  const all = rowsForYear();
  const rows = all.slice(0, MAX_CAL_ROWS);
  const host = $("calendar");
  host.innerHTML = "";
  if (!rows.length) { $("calendar-meta").textContent = ""; $("calendar-foot").textContent = ""; return; }

  // 좌: 습지명 / 중앙: 1년 관측 스트립 / 우: 개방수면 소실 비중
  //   비중을 오른쪽에 함께 두면 각 행이 무엇을 뜻하는지 바로 읽힙니다.
  const LAB = 148, PCT = 56, RH = 18, TOP = 34, SURVEY = 40;
  // 행이 많으면 세로 스크롤바가 생기면서 폭이 줄어듭니다. 그 폭을 미리 빼지 않으면
  // 가로로 넘쳐 오른쪽 소실 비중 열이 잘립니다.
  const willScroll = TOP + rows.length * RH + SURVEY > 420;
  const W = Math.max(700, host.parentElement.clientWidth - (willScroll ? 20 : 4));
  const plotW = W - LAB - PCT;
  const H = TOP + rows.length * RH + SURVEY;
  const x = (doy) => LAB + (doy / 365) * plotW;

  const svg = el("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}` });
  const bodyBottom = TOP + rows.length * RH;

  // 월 구분 — 홀수 달에 옅은 띠를 깔아 시간축이 눈에 들어오게 합니다.
  const monthStart = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 365];
  for (let m = 0; m < 12; m++) {
    if (m % 2 === 0) {
      svg.appendChild(el("rect", {
        x: x(monthStart[m]), y: TOP - 4, width: x(monthStart[m + 1]) - x(monthStart[m]),
        height: bodyBottom - TOP + 4, fill: "#f6f8f7",
      }));
    }
    svg.appendChild(el("text", {
      class: "cal-axis", x: (x(monthStart[m]) + x(monthStart[m + 1])) / 2, y: TOP - 10,
      "text-anchor": "middle",
    }, [txt(String(m + 1))]));
  }
  svg.appendChild(el("text", { class: "cal-axis", x: LAB - 8, y: TOP - 10, "text-anchor": "end" },
    [txt(`${S.year}년 · 월`)]));
  svg.appendChild(el("text", { class: "cal-axis", x: W - 4, y: TOP - 10, "text-anchor": "end" },
    [txt("소실")]));

  rows.forEach((r, i) => {
    const y = TOP + i * RH;
    const sel = S.sel === r.wid;
    if (sel) svg.appendChild(el("rect", { x: 0, y, width: W, height: RH - 1, fill: "#eef5f0" }));

    const lab = el("text", {
      class: "cal-row-label" + (sel ? " sel" : ""),
      x: LAB - 10, y: y + 12, "text-anchor": "end",
    }, [txt(trim(labelOf(r), 17))]);
    lab.style.cursor = "pointer";
    lab.onclick = () => select(r.wid);
    svg.appendChild(lab);

    for (const o of r.observations) {
      const rect = el("rect", {
        class: "cal-cell", x: x(dayOfYear(o.date)) - 2.8, y: y + 3,
        width: 5.6, height: RH - 7, rx: 1, fill: cellColor(o, r.open_ratio_baseline),
      });
      rect.onmouseenter = (e) => showTip(e, cellTip(r, o));
      rect.onmousemove = moveTip;
      rect.onmouseleave = hideTip;
      rect.onclick = () => select(r.wid);
      svg.appendChild(rect);
    }

    // 행 끝에 개방수면 소실 비중 — 이 줄이 무엇을 말하는지 숫자로 못박습니다.
    const share = r.covered_share;
    svg.appendChild(el("text", {
      class: "cal-pct", x: W - 4, y: y + 12, "text-anchor": "end",
      fill: share ? COLOR.veg : "var(--muted)",
    }, [txt(share === null || share === undefined ? "—" : Math.round(share * 100) + "%")]));
  });

  // 현행 현장조사 대비
  const sy = bodyBottom + 12;
  svg.appendChild(el("line", { class: "cal-grid", x1: 0, y1: sy - 4, x2: W, y2: sy - 4 }));
  svg.appendChild(el("text", { class: "cal-row-label", x: LAB - 10, y: sy + 14, "text-anchor": "end" },
    [txt("현행 현장조사")]));
  svg.appendChild(el("rect", { class: "cal-survey", x: LAB, y: sy + 3, width: plotW, height: 16, rx: 2, fill: "none" }));
  svg.appendChild(el("text", {
    class: "cal-survey-label", x: LAB + plotW / 2, y: sy + 14, "text-anchor": "middle",
    stroke: "#fff", "stroke-width": 3, "paint-order": "stroke",
  }, [txt("법정조사 5년 주기 — 이 해에 이 습지를 조사했다는 보장이 없습니다")]));

  host.appendChild(svg);

  const nObs = rows.reduce((a, r) => a + r.n_obs, 0);
  $("calendar-meta").textContent = `${S.year}년 · ${rows.length}개소 · 관측 ${fmt(nObs)}회`;
  $("calendar-foot").textContent =
    `가로축은 ${S.year}년 1월~12월, 칸 하나는 Sentinel-1 관측 1회입니다. ` +
    `색은 그날의 수면 상태이며, 오른쪽 숫자는 그 해 관측 중 개방수면이 사라진 비중입니다.` +
    (all.length > rows.length ? ` 조건 부합 ${all.length}개소 중 상위 ${MAX_CAL_ROWS}개소를 표시합니다.` : "");
}

const trim = (s, n) => (s.length > n ? s.slice(0, n - 1) + "…" : s);

function cellTip(r, o) {
  const peak = peakRatio(r.wid);
  const idx = peak > 0 ? Math.round((o.open_ratio / peak) * 100) : 0;
  return `<b>${labelOf(r)}</b><br>${o.date} · ${STATE_LABEL[o.state]}<br>` +
    `개방수면 지수 <b>${idx}</b> / 100<br>VV 평균 <b>${fmt(o.vv_db, 1)} dB</b>` +
    (o.frames > 1 ? `<br><span style="opacity:.75">동일 일자 ${o.frames}장면 평균</span>` : "");
}

/* ─────────── 시계열 ─────────── */

/* y축은 면적이 아니라 **그 습지 자신의 전 기간 최대 대비 지수**입니다.
   면적 절대값은 검증되지 않았으므로 측정값으로 제시하지 않습니다. */
function renderTimeseries() {
  const host = $("timeseries");
  host.innerHTML = "";
  const all = S.years.filter((r) => r.wid === S.sel).sort((a, b) => a.year - b.year);
  if (!all.length) {
    $("ts-title").textContent = "개방수면 지수";
    $("ts-meta").textContent = "";
    $("ts-foot").textContent = "";
    host.innerHTML = '<p style="color:var(--muted);font-size:12px;padding:32px 0;text-align:center;margin:0">습지를 선택하십시오.</p>';
    return;
  }

  const r0 = all[0];
  const peak = peakRatio(S.sel) || 1;
  $("ts-title").textContent = `${labelOf(r0)} — 개방수면 지수`;
  $("ts-meta").innerHTML =
    `습지면적 ${fmt(r0.area_ha)} ha · orbit ${r0.rel_orbit} ${r0.orbit_pass === "ASCENDING" ? "상행" : "하행"}<br>` +
    `${all[0].year}~${all[all.length - 1].year}년`;

  const obs = [];
  for (const yr of all) for (const o of yr.observations) obs.push({ ...o, baseline: yr.open_ratio_baseline });
  obs.sort((a, b) => (a.date < b.date ? -1 : 1));

  const W = Math.max(560, host.clientWidth || 620), H = 300;
  const M = { t: 16, r: 40, b: 28, l: 38 };
  const pw = W - M.l - M.r, ph = H - M.t - M.b;

  const t0 = new Date(obs[0].date).getTime();
  const t1 = new Date(obs[obs.length - 1].date).getTime();
  const X = (d) => M.l + ((new Date(d).getTime() - t0) / Math.max(1, t1 - t0)) * pw;
  const idxOf = (o) => (o.open_ratio / peak) * 100;
  const Y = (v) => M.t + ph - (v / 100) * ph;
  const YV = (v) => M.t + ph - ((v + 25) / 20) * ph;

  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H });

  for (const v of [0, 25, 50, 75, 100]) {
    svg.appendChild(el("line", { class: "grid-l", x1: M.l, y1: Y(v), x2: M.l + pw, y2: Y(v) }));
    svg.appendChild(el("text", { class: "ax-t", x: M.l - 6, y: Y(v) + 3, "text-anchor": "end" }, [txt(String(v))]));
  }
  for (const v of [-20, -15, -10]) {
    svg.appendChild(el("text", { class: "ax-t", x: M.l + pw + 6, y: YV(v) + 3, fill: COLOR.veg }, [txt(String(v))]));
  }

  for (const o of obs) {
    if (o.state === "veg_covered") {
      svg.appendChild(el("rect", { class: "band-veg", x: X(o.date) - 5, y: M.t, width: 10, height: ph }));
    }
  }

  const pts = obs.map((o) => `${X(o.date)},${Y(idxOf(o))}`);
  svg.appendChild(el("polygon", { class: "area-open", points: `${M.l},${M.t + ph} ${pts.join(" ")} ${M.l + pw},${M.t + ph}` }));
  svg.appendChild(el("polyline", { class: "line-open", points: pts.join(" ") }));
  svg.appendChild(el("polyline", { class: "line-vv", points: obs.map((o) => `${X(o.date)},${YV(o.vv_db)}`).join(" ") }));

  const optical = all.flatMap((yr) => yr.optical || []);
  for (const p of optical) {
    if (p.ndvi === null || p.ndvi === undefined) continue;
    const dot = el("circle", { class: "dot-ndvi pt", cx: X(p.date), cy: M.t + ph - ((p.ndvi + 0.2) / 1.2) * ph, r: 2.2 });
    dot.onmouseenter = (e) => showTip(e, `${p.date}<br>Sentinel-2 NDVI <b>${fmt(p.ndvi, 2)}</b>`);
    dot.onmousemove = moveTip;
    dot.onmouseleave = hideTip;
    svg.appendChild(dot);
  }

  for (const o of obs) {
    const c = el("circle", { class: "pt", cx: X(o.date), cy: Y(idxOf(o)), r: 2.6, fill: cellColor(o, o.baseline) });
    c.onmouseenter = (e) => showTip(e,
      `${o.date} · ${STATE_LABEL[o.state]}<br>개방수면 지수 <b>${Math.round(idxOf(o))}</b> / 100<br>VV <b>${fmt(o.vv_db, 1)} dB</b>`);
    c.onmousemove = moveTip;
    c.onmouseleave = hideTip;
    svg.appendChild(c);
  }

  for (const y of [...new Set(obs.map((o) => o.date.slice(0, 4)))]) {
    const first = obs.find((o) => o.date.startsWith(y));
    svg.appendChild(el("text", { class: "ax-t", x: X(first.date), y: H - 9 }, [txt(y)]));
  }
  svg.appendChild(el("line", { class: "ax", x1: M.l, y1: M.t + ph, x2: M.l + pw, y2: M.t + ph }));
  svg.appendChild(el("text", { class: "chart-note", x: M.l + pw, y: M.t + 8, "text-anchor": "end" },
    [txt("좌축 지수(전 기간 최대=100) · 우축 VV dB · 녹색점 NDVI")]));

  host.appendChild(svg);

  const nCov = all.reduce((a, r) => a + (r.n_covered ?? 0), 0);
  const nObs = all.reduce((a, r) => a + r.n_obs, 0);
  $("ts-foot").textContent =
    `관측 ${nObs}회 중 개방수면 소실 ${nCov}회. 면적 절대값은 검증되지 않아 지수로 표시합니다.` +
    (optical.length ? ` Sentinel-2 ${optical.length}장면으로 교차검증하였습니다.` : "");
}

/* ─────────── 습지 요약 ─────────── */

function renderDetail() {
  const host = $("detail");
  const all = S.years.filter((r) => r.wid === S.sel).sort((a, b) => b.year - a.year);
  if (!all.length) {
    host.innerHTML = '<p style="color:var(--muted);font-size:12px;margin:0">습지를 선택하십시오.</p>';
    return;
  }
  const r = all.find((x) => x.year === S.year) || all[0];
  const pct = (v) => (v === null || v === undefined ? "—" : Math.round(v * 100) + "%");
  const openShare = r.n_obs ? (r.n_obs - r.n_veg_covered - r.n_dry_suspect) / r.n_obs : null;

  const rows = [
    ["습지 면적", `${fmt(r.area_ha)} ha`, ""],
    ["판독 연도", `${r.year}년`, ""],
    ["관측 횟수", `${r.n_obs}회`, ""],
    ["평균 재방문", `${fmt(r.revisit_days, 1)}일`, ""],
    ["개방수면 관측", r.has_open_water ? pct(openShare) : "—", "water"],
    ["개방수면 소실", r.has_open_water ? pct(r.covered_share) : "—", "veg"],
    ["판독 신뢰도", r.has_open_water ? (r.confidence === "high" ? "고" : "저") : "지표 비적용", ""],
  ];

  let html = '<table class="stat-table"><tbody>' +
    rows.map(([k, v, c]) => `<tr><th>${k}</th><td class="${c}">${v}</td></tr>`).join("") +
    "</tbody></table>";

  const eg = S.grades && S.grades[S.sel];
  if (eg && eg.grades) {
    // 0% 로 반올림되는 등급까지 늘어놓으면 읽는 사람이 얻는 것이 없습니다.
    const items = Object.entries(eg.grades)
      .filter(([, v]) => v >= 0.005).slice(0, 3)
      .map(([k, v]) => `${k} ${Math.round(v * 100)}%`).join(" · ");
    if (items) {
      html += `<p class="note"><b>생태자연도</b> ${items}` +
        (eg.coverage < 0.95
          ? ` <span class="dim">(습지의 ${Math.round(eg.coverage * 100)}%만 등급도에 포함)</span>`
          : "") +
        `</p>`;
    }
  }

  if (!r.has_open_water) {
    html += '<p class="note warn">연중 최대 개방수면율이 5% 미만입니다. 삼림습지·초본습지와 같이 SAR 로 관측할 수면이 없는 유형으로 판단되어 개방수면 지표를 적용하지 않습니다.</p>';
  } else if (r.confidence === "low") {
    html += '<p class="note warn">임계값 선택에 따라 판독이 크게 변동합니다. 이 습지의 값은 판단 근거로 사용하지 마십시오.</p>';
  }
  host.innerHTML = html;
}

/* ─────────── 판독 경계 ─────────── */

function renderShape() {
  const host = $("shape");
  host.innerHTML = "";
  const feat = S.shapes && S.shapes.features.find((f) => f.properties.wid === S.sel);
  if (!feat) { host.innerHTML = '<p style="color:var(--muted);font-size:11px;margin:0">경계 자료 없음</p>'; return; }

  const rings = feat.geometry.type === "Polygon" ? feat.geometry.coordinates : feat.geometry.coordinates.flat();
  let minLon = 180, maxLon = -180, minLat = 90, maxLat = -90;
  for (const ring of rings) for (const [lon, lat] of ring) {
    if (lon < minLon) minLon = lon;
    if (lon > maxLon) maxLon = lon;
    if (lat < minLat) minLat = lat;
    if (lat > maxLat) maxLat = lat;
  }

  // 경도 1도의 실제 거리는 cos(위도) 배입니다. 빼면 형상이 옆으로 늘어납니다.
  const kx = Math.cos(((minLat + maxLat) / 2 * Math.PI) / 180);
  const spanX = Math.max((maxLon - minLon) * kx, 1e-9);
  const spanY = Math.max(maxLat - minLat, 1e-9);

  const W = 190, H = 140, PAD = 12, BAR = 15;
  const scale = Math.min((W - PAD * 2) / spanX, (H - PAD - BAR) / spanY);
  const offX = (W - spanX * scale) / 2, offY = (H - BAR - spanY * scale) / 2;
  const X = (lon) => offX + (lon - minLon) * kx * scale;
  const Y = (lat) => offY + (maxLat - lat) * scale;

  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H });

  if (S.layer && feat.properties.bbox5186) {
    const requested = S.layer;
    const src = `/map/wms?layer=${encodeURIComponent(S.layer)}&bbox=${feat.properties.bbox5186}` +
                `&width=${Math.max(Math.round(spanX * scale), 64)}&height=${Math.max(Math.round(spanY * scale), 64)}`;
    const img = el("image", {
      x: offX, y: offY, width: spanX * scale, height: spanY * scale,
      href: src, preserveAspectRatio: "none", opacity: 0.9,
    });
    const note = el("text", { class: "shape-note", x: 4, y: 11 }, [txt("식생도 불러오는 중…")]);
    // 도면이 없는 구역도 서버는 200 과 투명 PNG 로 응답합니다. 그대로 두면 화면에
    // 아무 변화가 없어 기능이 고장난 것처럼 보입니다. 실제로 그려진 화소가 있는지
    // 확인해 '자료 없음' 과 '오류' 를 구분해 알립니다.
    img.addEventListener("load", () => {
      note.remove();
      blankTile(src).then((blank) => {
        if (!blank || S.layer !== requested) return;
        img.remove();
        svg.appendChild(el("text", { class: "shape-note", x: 4, y: 11 },
          [txt("이 습지에는 해당 도면이 없습니다")]));
      });
    });
    img.addEventListener("error", () => {
      img.remove();
      note.textContent = "식생도를 불러오지 못했습니다";
    });
    svg.appendChild(img);
    svg.appendChild(note);
  }

  // 레이어를 겹칠 때는 경계를 윤곽선만 남깁니다.
  // 채움색이 불투명해 아래 깔린 식생도를 통째로 가리던 문제가 있었습니다.
  for (const ring of rings) {
    svg.appendChild(el("path", {
      class: "shape-poly" + (S.layer ? " outline" : ""),
      d: ring.map((c, i) => `${i ? "L" : "M"}${X(c[0]).toFixed(1)},${Y(c[1]).toFixed(1)}`).join("") + "Z",
    }));
  }

  const targets = [50, 100, 200, 500, 1000, 2000, 5000];
  const target = targets.find((m) => (m / 111320) * scale >= 36) || targets[targets.length - 1];
  const barPx = (target / 111320) * scale, by = H - 6;
  svg.appendChild(el("line", { class: "scale-bar", x1: PAD, y1: by, x2: PAD + barPx, y2: by }));
  svg.appendChild(el("line", { class: "scale-bar", x1: PAD, y1: by - 3, x2: PAD, y2: by + 3 }));
  svg.appendChild(el("line", { class: "scale-bar", x1: PAD + barPx, y1: by - 3, x2: PAD + barPx, y2: by + 3 }));
  svg.appendChild(el("text", { class: "ax-t", x: PAD + barPx + 5, y: by + 3 },
    [txt(target >= 1000 ? `${target / 1000} km` : `${target} m`)]));

  host.appendChild(svg);
  for (const b of document.querySelectorAll(".layer-btn")) {
    b.classList.toggle("on", (b.dataset.layer || "") === S.layer);
  }
}

/* 타일에 그려진 화소가 있는지 확인합니다. 같은 출처라 캔버스를 읽을 수 있습니다.
   결과를 캐시해 레이어를 오갈 때 같은 타일을 다시 받지 않게 합니다. */
const tileCache = new Map();

function blankTile(src) {
  if (tileCache.has(src)) return Promise.resolve(tileCache.get(src));
  return fetch(src)
    .then((r) => (r.ok ? r.blob() : Promise.reject(new Error(String(r.status)))))
    .then((b) => createImageBitmap(b))
    .then((bmp) => {
      const c = document.createElement("canvas");
      c.width = bmp.width; c.height = bmp.height;
      const ctx = c.getContext("2d", { willReadFrequently: true });
      ctx.drawImage(bmp, 0, 0);
      const d = ctx.getImageData(0, 0, c.width, c.height).data;
      let drawn = 0;
      for (let i = 3; i < d.length; i += 4) if (d[i] > 10) drawn++;
      // 경계선 몇 픽셀만 걸친 경우까지 '있음' 으로 보면 화면에는 여전히 아무것도
      // 안 보입니다. 0.5% 미만은 없는 것으로 처리합니다.
      const blank = drawn / (c.width * c.height) < 0.005;
      tileCache.set(src, blank);
      return blank;
    })
    .catch(() => false);   // 확인에 실패하면 이미지를 지우지 않습니다.
}

/* ─────────── 위치 ─────────── */

function renderLocator() {
  const host = $("locator");
  host.innerHTML = "";
  if (!S.korea) return;

  const W = 190, H = 250, PAD = 8;
  const LON = [125.5, 130.0], LAT = [33.0, 38.7];
  const X = (lon) => PAD + ((lon - LON[0]) / (LON[1] - LON[0])) * (W - PAD * 2);
  const Y = (lat) => H - PAD - ((lat - LAT[0]) / (LAT[1] - LAT[0])) * (H - PAD * 2);

  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H });
  for (const f of S.korea.features) {
    const g = f.geometry;
    const polys = g.type === "Polygon" ? [g.coordinates] : g.coordinates;
    for (const poly of polys) {
      svg.appendChild(el("path", {
        class: "loc-land",
        d: poly[0].map((c, i) => `${i ? "L" : "M"}${X(c[0]).toFixed(1)},${Y(c[1]).toFixed(1)}`).join("") + "Z",
      }));
    }
  }

  const shown = new Set(rowsForYear().map((r) => r.wid));
  for (const p of S.points) {
    if (!shown.has(p.wid) && p.wid !== S.sel) continue;
    const on = p.wid === S.sel;
    const c = el("circle", { class: "loc-dot" + (on ? " on" : ""), cx: X(p.lon), cy: Y(p.lat), r: on ? 4.5 : 2.5 });
    c.onmouseenter = (e) => showTip(e, `<b>${p.name || "무명습지"}</b><br>${fmt(p.area_ha)} ha`);
    c.onmousemove = moveTip;
    c.onmouseleave = hideTip;
    c.style.cursor = "pointer";
    c.onclick = () => select(p.wid);
    svg.appendChild(c);
  }
  host.appendChild(svg);
}

/* ─────────── 안내선 ─────────── */

let tipNode = null;
function showTip(e, html) {
  if (!tipNode) {
    tipNode = document.createElement("div");
    tipNode.className = "tip";
    document.body.appendChild(tipNode);
  }
  tipNode.innerHTML = html;
  tipNode.style.display = "block";
  moveTip(e);
}
function moveTip(e) {
  if (!tipNode) return;
  const pad = 14;
  let x = e.clientX + pad, y = e.clientY + pad;
  const r = tipNode.getBoundingClientRect();
  if (x + r.width > window.innerWidth - 8) x = e.clientX - r.width - pad;
  if (y + r.height > window.innerHeight - 8) y = e.clientY - r.height - pad;
  tipNode.style.left = x + "px";
  tipNode.style.top = y + "px";
}
function hideTip() { if (tipNode) tipNode.style.display = "none"; }

/* ─────────── 안내 서랍 ─────────── */

function validationPanel() {
  const v = S.validation;
  if (!v) return "<p>검증 자료가 아직 생성되지 않았습니다.</p>";
  const o = v.by_state.open || {};
  const byW = Object.values(v.by_wetland || {}).filter((m) => m.n).sort((a, b) => b.n - a.n);
  const A = v.area_level_vs_variation || {};

  return `
<h3>무엇과 대조했는가</h3>
<p>현장 실측 자료가 없으므로 <b>독립 센서와의 일치도</b>로 정확도를 대신합니다.
같은 습지·같은 시기(±${v.max_offset_days || 3}일)를 Sentinel-1 레이더와 Sentinel-2 광학이
각각 관측한 짝을 만들어 비교하였습니다. 습지 <b>${v.n_wetlands_validated}개소</b>,
짝지은 관측 <b>${fmt(v.overall.n)}건</b>입니다.</p>

<h3>수면 유무 판정 — 성립</h3>
<table>
<tr><th>구분</th><th class="n">표본</th><th class="n">두 센서 판정 일치율</th></tr>
${Object.entries(v.by_state).map(([k, m]) =>
  `<tr><td>${STATE_LABEL[k] || k}</td><td class="n">${m.n}</td>` +
  `<td class="n">${m.presence_agreement}</td></tr>`).join("")}
</table>
<p>개방수면 구간의 일치율 <b>${o.presence_agreement}</b>가 이 시스템이 실제로 검증한 값입니다.
식생피복 구간은 두 센서가 모두 0에 가까워 자동으로 일치하는 부분이 섞입니다.</p>

<h3>면적 — 수준과 변동을 갈라 보아야 합니다</h3>
<p>낮은 R²를 곧바로 &lsquo;면적이 틀렸다&rsquo;로 읽으면 안 됩니다. R²는 <b>변동을 얼마나
설명하는가</b>이므로, 수면 넓이가 연중 거의 변하지 않는 습지에서는 수준이 정확해도
0에 가깝게 나옵니다. 두 가지를 나누어 확인하였습니다.</p>
<table>
<tr><th>확인한 것</th><th class="n">값</th><th>판정</th></tr>
<tr><td>레이더 평균 / 광학 평균</td><td class="n">${A.level_ratio_median}</td>
    <td>치우침 없음</td></tr>
<tr><td>±10% 안에 드는 습지</td><td class="n">${A.level_within_10pct} / ${A.n_wetlands}</td>
    <td>개별 습지는 편차 큼</td></tr>
<tr><td>MAE (수면적 대비, 중앙)</td><td class="n">${A.mae_pct_of_water_median}%</td>
    <td>정밀하지 않음</td></tr>
<tr><td>습지별 R² (중앙)</td><td class="n">${A.wetland_r2_median}</td>
    <td>시간 변동은 못 따라감</td></tr>
</table>
<p>전체를 놓고 보면 치우침은 없습니다(평균비 ${A.level_ratio_median}). 그러나 개별 습지의
수준 오차가 크고(수면적의 ${A.mae_pct_of_water_median}%), 시간에 따른 증감은 따라가지
못합니다. ${A.n_wetlands}개소 중 R² 0.5 이상은 <b>${A.wetland_r2_ge_05}개소</b>뿐입니다.</p>
<table>
<tr><th>습지</th><th class="n">표본</th><th class="n">면적 R²</th><th class="n">MAE (ha)</th></tr>
${byW.map((m) =>
  `<tr><td>${m.name || "—"}</td><td class="n">${m.n}</td>` +
  `<td class="n">${m.r2 ?? "—"}</td><td class="n">${fmt(m.mae_ha, 1)}</td></tr>`).join("")}
</table>
<p><b>여러 습지를 묶은 상관은 읽지 마십시오.</b> 크기가 다른 습지를 한데 넣으면
&lsquo;큰 습지는 둘 다 크다&rsquo;는 자명한 사실이 높은 상관으로 나타납니다.
습지별 R² 중앙값이 ${v.median_wetland_r2}인 자료에서, 묶어서 계산하면 ${o.r2}이 됩니다.
이 값은 판독 성능이 아닙니다.</p>
<p>원인을 확인한 결과 개방수면율의 <b>41~87%</b>가 폴리곤 평균 후방산란으로 설명됐습니다.
고정임계로 면적을 내면 밝기 분포가 통째로 이동할 때 임계 아래 화소 비율도 함께 움직입니다.
산출된 면적은 수면의 공간적 범위가 아니라 <b>그 습지가 전체적으로 얼마나 물처럼 보이는가</b>의
재진술에 가깝습니다.</p>
<p>풍파 가설도 검토하였으나 습지별로 상관의 부호가 뒤집혀 기각하였습니다.</p>

<h3>따라서 무엇을 쓰는가</h3>
<ul>
<li><b>쓰지 않음</b> — 개방수면적(ha) 절대값, 습지 간 면적 비교, 연도 간 면적 증감의 정량 해석</li>
<li><b>씀</b> — 수면 유무 판정(일치율 ${o.presence_agreement}), 계절 전환, 같은 습지 안의 상대 지수</li>
</ul>
<p>화면의 시계열 y축이 면적이 아니라 <b>전 기간 최대를 100으로 둔 지수</b>인 이유입니다.</p>`;
}

const PANELS = {
  terms: {
    title: "용어",
    html: `
<h3>법령·기관의 공식 용어</h3>
<table>
<tr><th>용어</th><th>근거</th></tr>
<tr><td>내륙습지</td><td>「습지보전법」 제2조 — 육지 또는 섬에 있는 호수·못·늪·하천 또는 하구</td></tr>
<tr><td>전국내륙습지조사</td><td>「습지보전법」 제4조에 따른 <b>5년 주기</b> 법정조사 (기초조사·정밀조사)</td></tr>
<tr><td>습지보호지역</td><td>「습지보전법」 제8조</td></tr>
<tr><td>하천습지·호수습지·산지습지·인공습지</td><td>국립생태원 습지 유형 분류</td></tr>
<tr><td>생태자연도</td><td>「자연환경보전법」에 따른 등급도</td></tr>
</table>

<h3>이 판독의 조작적 용어</h3>
<p>아래는 <b>이 시스템이 판독 결과를 설명하기 위해 정의한 용어</b>입니다.
법령이나 국립생태원 습지 유형 분류의 공식 명칭이 아닙니다.</p>
<table>
<tr><th>용어</th><th>이 시스템에서의 정의</th></tr>
<tr><td><b>개방수면</b></td><td>식생에 덮이지 않아 위성 레이더에 매끈한 면으로 관측되는 수면.
영어 <i>open water</i>에 대응하는 표현으로, 판독 결과를 가리키기 위해 이 시스템이 사용합니다.
VV 후방산란 −16 dB 미만이고 지형 경사 5° 이하인 화소를 말합니다.</td></tr>
<tr><td><b>개방수면 소실</b></td><td>개방수면이 그 습지 기준선의 30% 미만으로 줄어든 관측.
<b>이 시스템이 측정한 것은 여기까지입니다.</b> 줄어든 원인은 이 판정에 포함되지 않습니다.</td></tr>
<tr><td><b>식생 추정 / 산란체 없음</b></td><td>소실 관측을 VV 평균 −13 dB 로 다시 나눈
<b>실험적 구분</b>입니다. 광학과 대조한 결과 특이도가 0.10 에 그쳐 개별 관측의 판정
근거로는 쓰지 않습니다(판독 한계 참조). 화면에서는 참고 표시로만 남깁니다.</td></tr>
<tr><td><b>지표 비적용</b></td><td>연중 최대 개방수면율이 5% 미만이어서 개방수면 지표를 적용하지 않은 습지.
삼림습지·초본습지처럼 SAR 로 관측할 수면이 없는 유형입니다.</td></tr>
<tr><td><b>개방수면 지수</b></td><td>그 습지 자신의 전 기간 최대 개방수면율을 100으로 둔 상대값.
면적이 검증되지 않았으므로 절대값 대신 씁니다.</td></tr>
<tr><td><b>관측 가능성</b></td><td>궤도별 연간 관측 횟수 이력. 관측이 없어서 생긴 공백을
&lsquo;변화 없음&rsquo;으로 읽지 않기 위해 판독보다 먼저 확인합니다.</td></tr>
</table>

<h3>표기 원칙</h3>
<p>공식 용어와 이 시스템의 조작적 용어를 섞어 쓰지 않습니다.
판정 결과를 법령상 상태(예: 습지 훼손, 가뭄)로 옮겨 적지 않습니다.
&lsquo;건조 의심&rsquo;은 관측 상태의 이름이지 습지의 상태를 확정한 것이 아닙니다.</p>`,
  },
  method: {
    title: "판독 방법",
    html: `
<h3>SAR 를 쓰는 이유</h3>
<p>습지 수면은 장마철과 태풍기에 가장 크게 변동하는데, 광학 위성은 그 시기에 구름으로 관측이 막힙니다.
Sentinel-1 은 C-band 레이더로 구름을 투과합니다.</p>

<h3>절차</h3>
<ul>
<li>Sentinel-1 GRD, IW, VV+VH — 습지별로 전 기간 연속 관측되는 relative orbit 하나로 고정</li>
<li>스페클 완화: 반경 50 m focal median</li>
<li>개방수면 판정: VV &lt; −16 dB, 경사 5° 초과 지형 제외</li>
<li>동일 일자 2장면(프레임 경계)은 평균하여 1회로 계수</li>
<li>Sentinel-2 NDVI·NDWI 를 같은 폴리곤에 붙여 원인을 가름</li>
</ul>

<h3>개방수면 감소의 원인은 개별 관측 단위로 판정하지 않습니다</h3>
<p>수면이 줄어 보이는 원인은 둘입니다. 수량이 감소하였거나, 식생이 수면을 덮은 것입니다.
당초에는 VV 평균이 함께 <b>상승</b>하면 식생으로 판정하였습니다. 습지 17개소·짝지음 173건을
Sentinel-2 NDVI 와 대조한 결과 <b>이 판정은 성립하지 않았습니다.</b></p>
<p>−13 dB 에서 민감도는 0.98 이지만 특이도가 0.10 입니다. 식생이 없는 관측의 90%도
&lsquo;식생피복&rsquo;으로 넘어갑니다. 두 분포가 거의 포개져 있어(식생 5/50/95 =
−12.8/−11.2/−9.9, 비식생 −13.7/−10.7/−9.7 dB) 어느 지점에서 잘라도 판별력
(Youden J 0.085)이 이 수준입니다. VV 와 녹색도의 상관도 전 기간 +0.14, 생장기 −0.13 으로
부호가 뒤집힙니다. 그래서 화면은 &lsquo;개방수면이 사라졌다&rsquo;까지만 말합니다.</p>
<p>다만 계절은 원인을 예측합니다. 생장기(5~9월) 소실 관측의 광학 구성은
식생 55% · 비식생 15%, 비생장기에는 14% · 28% 로 뒤집힙니다. 개별 관측이 아니라
<b>집계 수준에서는</b> &lsquo;여름철 소실은 대개 식생&rsquo;이라고 말할 수 있습니다.</p>

<h3>관측 가능성을 판독보다 먼저 봅니다</h3>
<p>Sentinel-1B 는 2021년 12월 소실되었고 Sentinel-1C 는 2024년 12월 발사되었습니다.
그 사이 특정 궤도는 관측이 끊깁니다. 이를 확인하지 않으면 관측 공백을 &lsquo;변화 없음&rsquo;으로 읽게 됩니다.</p>`,
  },
  validation: { title: "검증 결과", html: null },
  data: {
    title: "자료 출처",
    html: `
<h3>위성</h3>
<table>
<tr><th>자료</th><th>해상도 / 주기</th><th>제공</th></tr>
<tr><td>Sentinel-1 GRD (SAR)</td><td>10 m / 12일</td><td>ESA Copernicus</td></tr>
<tr><td>Sentinel-2 SR (광학)</td><td>10~20 m / 5일</td><td>ESA Copernicus</td></tr>
<tr><td>Copernicus DEM GLO-30</td><td>30 m</td><td>ESA</td></tr>
<tr><td>ERA5-Land (풍속)</td><td>11 km / 1시간</td><td>ECMWF</td></tr>
</table>
<p>모두 무상 공개 자료이며 상용 고해상도 영상은 사용하지 않았습니다.</p>

<h3>습지 경계</h3>
<p>국립생태원 에코뱅크 오픈API <code>습지_내륙_면</code> (내륙습지 2,704개소, EPSG:5186).
습지명·습지코드·유형·보호지역 지정 여부가 함께 제공됩니다.</p>

<h3>연계</h3>
<p>국립생태원 생태자연도 오픈API (공공데이터포털 <code>B553084/ecoapi</code>).
자연환경조사·생태계정밀조사 식생도는 판독 경계 도면에 겹쳐 볼 수 있습니다.</p>`,
  },
  limits: {
    title: "판독 한계",
    html: `
<h3>면적을 측정값으로 제시하지 않습니다</h3>
<p>독립 센서와 대조한 결과, 전체로 보면 치우침은 없으나(평균비 0.993) 개별 습지의 오차가 크고
(수면적의 약 11%), 시간에 따른 증감은 따라가지 못합니다(습지별 R² 중앙 0.07).
근거는 &lsquo;검증 결과&rsquo;를 보십시오. 화면의 시계열은 같은 습지 안의 <b>상대 지수</b>입니다.</p>

<h3>수위는 측정하지 않습니다</h3>
<p>SAR 는 수면의 넓이를 관측하며 수심은 관측하지 않습니다.</p>

<h3>식생 하부 침수는 판정하지 않습니다</h3>
<p>이중반사 신호는 논의 담수 관리 주기와 같은 대역에서 변동하여 오탐이 심합니다.
근거가 확립되기 전까지 산출물에 포함하지 않습니다.</p>

<h3>개방수면이 없는 습지에는 지표를 적용하지 않습니다</h3>
<p>연중 최대 개방수면율 5% 미만인 습지는 삼림습지·초본습지와 같이 SAR 로 관측할 수면이 없는
유형입니다. 별도 집계하며, 다른 센서·다른 지표가 필요합니다.</p>

<h3>경계가 뚜렷하지 않은 습지</h3>
<p>늪·소택형 습지는 개방수면이 정수식생으로 연속적으로 이어져 그을 경계가 없습니다.
이 방법은 경계가 뚜렷한 호수·하천형 습지에서 성립합니다.</p>

<h3>원인 판정은 실험 항목으로 내렸습니다</h3>
<p>식생피복 판정의 VV 임계 −13 dB 는 시범 습지 1개소에서 나온 값이었습니다.
전국 자료(습지 17개소·짝지음 173건)로 검사한 결과 최적값은 −13.0 dB 로 같았으나,
판별력이 없었습니다(Youden J 0.085, 특이도 0.10). 식생이 없는 관측의 90%도
&lsquo;식생피복&rsquo;으로 분류되며, 실제 소실 관측의 93.8%가 그렇게 분류되어
사실상 상수 분류기입니다.
주지표를 <b>개방수면 소실 비중</b>으로 바꾸고, 원인 구분은 실험 항목으로 내렸습니다.</p>

<h3>남은 것</h3>
<p>소실의 원인을 실제로 가르려면 편파비(VH/VV)나 간섭 결맞음처럼 구조를 보는 지표가
필요합니다. 이 시스템은 아직 그것을 쓰지 않습니다.</p>`,
  },
};

function wireControls() {
  $("year-select").onchange = (e) => { S.year = Number(e.target.value); renderAll(); };
  $("sort-select").onchange = (e) => { S.sort = e.target.value; renderAll(); };
  $("only-open").onchange = (e) => { S.onlyOpen = e.target.checked; renderAll(); };
  $("rail-search").oninput = debounce((e) => { S.search = e.target.value.trim(); renderAll(); }, 160);

  for (const b of document.querySelectorAll(".layer-btn")) {
    b.onclick = () => { S.layer = b.dataset.layer || ""; renderShape(); };
  }
  for (const btn of document.querySelectorAll("[data-panel]")) {
    btn.onclick = () => openPanel(btn.dataset.panel);
  }
  $("drawer-close").onclick = () => { $("drawer").hidden = true; };
  window.addEventListener("resize", debounce(() => { renderCalendar(); renderTimeseries(); }, 180));
  window.addEventListener("keydown", (e) => { if (e.key === "Escape") $("drawer").hidden = true; });
}

function openPanel(key) {
  const p = PANELS[key];
  if (!p) return;
  $("drawer-title").textContent = p.title;
  $("drawer-body").innerHTML = key === "validation" ? validationPanel() : p.html;
  $("drawer").hidden = false;
}

function debounce(fn, ms) {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

function renderAll() {
  const rows = rowsForYear();
  if (!S.sel || !rows.some((r) => r.wid === S.sel)) S.sel = rows.length ? rows[0].wid : null;
  renderList();
  renderCalendar();
  renderTimeseries();
  renderDetail();
  renderShape();
  renderLocator();
  renderOrbits();
}

window.ECOSCOPE = { S, select, openPanel, labelOf, fmt };
boot();
