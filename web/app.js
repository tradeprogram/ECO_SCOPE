/* 에코스코프 — 화면 구성 로직.
 *
 * 이 파일은 수치를 계산하지 않습니다. data/ 의 사전 생성 파일이 유일한 수치 출처입니다.
 * 판독 지표를 변경하려면 src/nie/wetlands/aggregate.py 를 수정한 뒤 다시 생성하시기 바랍니다.
 */

const S = {
  summary: null,
  years: [],          // wetland_years.json
  points: [],
  korea: null,
  orbits: [],
  year: null,
  sort: "quality",
  onlyOpen: true,
  search: "",
  sel: null,
};

const COLOR = {
  water: "#2f6fb0",
  waterSoft: "#cfe0f0",
  veg: "#6f9c1f",
  dry: "#c8801f",
  none: "#d5dcd7",
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

/* ---------------- 자료 적재 ---------------- */

async function boot() {
  // 판독 자료는 다시 생성될 때마다 바뀝니다. 브라우저 캐시가 옛 수치를 붙들지 않도록
  // 항상 재검증을 요청합니다(변경이 없으면 304 로 응답합니다).
  const get = (path, fallback) =>
    fetch(path, { cache: "no-cache" }).then((r) => r.json()).catch(() => fallback);

  const [summary, years, points, korea, orbits] = await Promise.all([
    get("data/summary.json", null),
    get("data/wetland_years.json", []),
    get("data/wetland_points.json", []),
    get("data/korea_adm1.geojson", null),
    get("data/orbit_history.json", []),
  ]);
  S.summary = summary;
  S.years = years;
  S.points = points;
  S.korea = korea;
  S.orbits = orbits;
  S.year = summary.years[summary.years.length - 1];

  buildYearSelect();
  renderKpis();
  renderClaim();
  wireControls();
  renderAll();
}

function buildYearSelect() {
  const sel = $("year-select");
  sel.innerHTML = "";
  for (const y of S.summary.years) {
    const o = document.createElement("option");
    o.value = String(y);
    o.textContent = `${y}년`;
    if (y === S.year) o.selected = true;
    sel.appendChild(o);
  }
}

/* ---------------- 머리말 지표 ---------------- */

function renderKpis() {
  const s = S.summary;
  const items = [
    [fmt(s.n_observations), "SAR 관측"],
    [fmt(s.n_wetlands), "판독 습지"],
    [`${fmt(s.mean_revisit_days, 1)}일`, "평균 재방문"],
    [fmt(s.n_wetlands_open_water), "개방수면 성립"],
    [fmt(s.n_wetlands_with_veg_cover), "식생피복 관측"],
  ];
  $("kpis").innerHTML = items
    .map(([b, t]) => `<div class="kpi"><b>${b}</b><span>${t}</span></div>`)
    .join("");
}

function renderClaim() {
  const s = S.summary;
  const perYear = s.mean_obs_per_wetland_year;
  const ratio = Math.round(perYear * 5); // 현장조사 5년 1주기 대비
  $("claim").innerHTML =
    `전국 자연환경조사 및 내륙습지조사는 <b>5년 1주기</b>로 시행됩니다. ` +
    `동일 습지를 Sentinel-1 위성은 <b>연 ${fmt(perYear, 1)}회</b> 관측하므로, ` +
    `1개 조사 주기 동안 <b>약 ${fmt(ratio)}배</b>의 관측 자료가 축적됩니다. ` +
    `<span style="color:var(--muted)">판독 기간 ${s.years[0]}~${s.years[s.years.length - 1]}년 (${s.years.length}개년) · ` +
    `자료 생성일 ${s.generated_utc.slice(0, 10)}</span>`;
}

/* ---------------- 판독 대상 목록 ---------------- */

function rowsForYear() {
  let rows = S.years.filter((r) => r.year === S.year);
  if (S.onlyOpen) rows = rows.filter((r) => r.has_open_water);
  if (S.search) {
    const q = S.search.toLowerCase();
    rows = rows.filter((r) => labelOf(r).toLowerCase().includes(q));
  }
  // 판독 신뢰도순: 고신뢰 -> 습지명 확인된 것 -> 개방수면적 순.
  // 임계값에 흔들리는 이질 폴리곤이 목록 앞을 차지하지 않도록 하기 위한 기본 정렬입니다.
  const quality = (r) =>
    (r.confidence === "high" && r.has_open_water ? 0 : 1) * 1e9 +
    (r.name ? 0 : 1) * 1e6 -
    Math.min(r.open_ha_max, 1e5);

  const key = {
    quality,
    area: (r) => -r.area_ha,
    open: (r) => -r.open_ha_max,
    obs: (r) => -r.n_obs,
    veg: (r) => -(r.veg_cover_share ?? -1),
  }[S.sort];
  return rows.sort((a, b) => key(a) - key(b));
}

function labelOf(r) {
  return r.name || `무명습지 ${r.wid.split("-").pop().slice(-5)}`;
}

function renderList() {
  const rows = rowsForYear();
  const total = S.years.filter((r) => r.year === S.year).length;
  const openTotal = S.years.filter((r) => r.year === S.year && r.has_open_water).length;
  $("rail-count").textContent = S.search
    ? `검색 결과 ${rows.length}개소`
    : S.onlyOpen
      ? `${rows.length}개소 표시 · ${S.year}년 판독 ${total}개소 중 개방수면 판독이 성립한 습지`
      : `${rows.length}개소 표시 · 이 중 개방수면 판독 성립 ${openTotal}개소`;

  const ul = $("wetland-list");
  ul.innerHTML = "";
  for (const r of rows) {
    const li = document.createElement("li");
    if (S.sel === r.wid) li.className = "on";
    li.dataset.wid = r.wid;

    const tags = [];
    if (!r.has_open_water) tags.push('<span class="tag noopen">지표 비적용</span>');
    if (r.has_open_water && r.confidence === "low") tags.push('<span class="tag low">저신뢰</span>');

    li.innerHTML =
      `<div class="wl-name${r.name ? "" : " anon"}">${labelOf(r)}</div>` +
      `<div class="wl-num">${r.has_open_water ? fmt(r.open_ha_max, 1) + " ha" : "—"}</div>` +
      `<div class="wl-meta">${fmt(r.area_ha)} ha · 관측 ${r.n_obs}회 ${tags.join(" ")}</div>`;
    li.onclick = () => select(r.wid);
    ul.appendChild(li);
  }
  if (!rows.length) {
    ul.innerHTML = '<li style="color:var(--muted);font-size:12px">해당 조건에 부합하는 습지가 없습니다.</li>';
  }
}

function select(wid) {
  S.sel = wid;
  renderList();
  renderCalendar();
  renderTimeseries();
  renderDetail();
  renderLocator();
  renderOrbits();
}

/* ---------------- 관측 가능성 ---------------- */

/* Sentinel-1B 는 2021년 12월 고장으로 소실되었고, Sentinel-1C 는 2024년 12월 발사되었습니다.
 * 그 사이 특정 relative orbit 은 관측이 사실상 중단됩니다. 이 표는 그 사실을 그대로 표시합니다.
 * 이를 확인하지 않고 시계열을 작성하면 관측 공백을 변화 없음으로 오독하게 됩니다. */
function renderOrbits() {
  const host = $("orbits");
  host.innerHTML = "";
  const rec = S.orbits.find((o) => o.wid === S.sel);
  if (!rec) {
    host.innerHTML = '<p style="color:var(--muted);font-size:12px">해당 습지의 관측 가능성 이력이 아직 수집되지 않았습니다.</p>';
    $("orbits-foot").textContent = "";
    return;
  }

  const years = S.summary.years.map(String);
  const orbits = Object.entries(rec.by_orbit_year)
    .map(([orb, byYear]) => ({ orb: Number(orb), byYear, total: Object.values(byYear).reduce((a, b) => a + b, 0) }))
    .sort((a, b) => b.total - a.total)
    .slice(0, 6);

  const cls = (n) => (n < 5 ? "gap" : n >= 20 ? "full" : "part");

  let html = '<table class="orb"><thead><tr><th class="lab">궤도</th>' +
    years.map((y) => `<th>${y}</th>`).join("") + "<th>합계</th></tr></thead><tbody>";
  for (const o of orbits) {
    const chosen = o.orb === rec.chosen_orbit;
    html += `<tr class="${chosen ? "chosen" : ""}"><td class="lab">orbit ${o.orb}</td>` +
      years.map((y) => `<td class="n ${cls(o.byYear[y] || 0)}">${o.byYear[y] || 0}</td>`).join("") +
      `<td class="n">${o.total}</td></tr>`;
  }
  html += "</tbody></table>";
  host.innerHTML = html;

  const broken = orbits.filter((o) => {
    const mid = ["2022", "2023", "2024"].map((y) => o.byYear[y] || 0);
    const early = ["2019", "2020", "2021"].map((y) => o.byYear[y] || 0);
    return early.every((n) => n >= 20) && mid.every((n) => n < 5);
  });
  $("orbits-foot").textContent = broken.length
    ? `orbit ${broken.map((o) => o.orb).join(", ")}은(는) 2019~2021년 연 20회 이상 관측되었으나 ` +
      `2022~2024년 연 5회 미만으로 중단되었습니다. Sentinel-1B 가 2021년 12월 고장난 궤도입니다. ` +
      `2025년 관측이 회복된 것은 2024년 12월 발사된 Sentinel-1C 가 동일 궤도면을 승계하였기 때문입니다. ` +
      `본 시계열은 전 기간 연속 관측되는 orbit ${rec.chosen_orbit}으로 고정하여 판독하였습니다.`
    : `전 기간 연속 관측되는 orbit ${rec.chosen_orbit}으로 고정하여 판독하였습니다. ` +
      `궤도가 혼재되면 입사각이 달라져 후방산란을 직접 비교할 수 없습니다.`;
}

/* ---------------- 관측 달력 ---------------- */

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
  const [r1, g1, b1] = p(a);
  const [r2, g2, b2] = p(b);
  const c = (x, y) => Math.round(x + (y - x) * t);
  return `rgb(${c(r1, r2)},${c(g1, g2)},${c(b1, b2)})`;
}

function renderLegend() {
  $("legend").innerHTML = [
    [COLOR.water, "개방수면 (짙을수록 넓음)"],
    [COLOR.veg, "식생피복 — 수면은 있으나 식생이 덮은 상태"],
    [COLOR.dry, "건조 의심 — 수면과 산란체가 모두 확인되지 않음"],
    [COLOR.none, "개방수면 지표 비적용 습지"],
  ]
    .map(([c, t]) => `<span><i style="background:${c}"></i>${t}</span>`)
    .join("");
}

function renderCalendar() {
  renderLegend();
  const all = rowsForYear();
  const rows = all.slice(0, MAX_CAL_ROWS);
  const host = $("calendar");
  host.innerHTML = "";
  if (!rows.length) return;

  const LAB = 132, PAD_R = 14, RH = 17, TOP = 26, SURVEY_H = 36;
  const W = Math.max(760, host.parentElement.clientWidth - 4);
  const plotW = W - LAB - PAD_R;
  const H = TOP + rows.length * RH + SURVEY_H + 12;
  const x = (doy) => LAB + (doy / 365) * plotW;

  const svg = el("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}` });

  const monthStart = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334];
  monthStart.forEach((d, i) => {
    svg.appendChild(el("line", { class: "cal-grid", x1: x(d), y1: TOP - 12, x2: x(d), y2: TOP + rows.length * RH }));
    if (i % 2 === 0) svg.appendChild(el("text", { class: "cal-axis", x: x(d) + 3, y: TOP - 15 }, [txt(MONTHS[i])]));
  });

  rows.forEach((r, i) => {
    const y = TOP + i * RH;
    const sel = S.sel === r.wid;
    if (sel) {
      svg.appendChild(el("rect", {
        x: LAB - 2, y, width: plotW + 2, height: RH - 2, fill: "rgba(210,236,222,.72)", rx: 3,
      }));
    }
    const lab = el("text", {
      class: "cal-row-label" + (sel ? " sel" : ""),
      x: LAB - 8, y: y + 11, "text-anchor": "end",
    }, [txt(trim(labelOf(r), 15))]);
    lab.style.cursor = "pointer";
    lab.onclick = () => select(r.wid);
    svg.appendChild(lab);

    for (const o of r.observations) {
      const cx = x(dayOfYear(o.date));
      const rect = el("rect", {
        class: "cal-cell", x: cx - 2.6, y: y + 2, width: 5.2, height: RH - 6,
        rx: 2, fill: cellColor(o, r.open_ratio_baseline),
      });
      rect.onmouseenter = (e) => showTip(e, cellTip(r, o));
      rect.onmousemove = moveTip;
      rect.onmouseleave = hideTip;
      rect.onclick = () => select(r.wid);
      svg.appendChild(rect);
    }
  });

  // 현행 현장조사 대비 행
  const sy = TOP + rows.length * RH + 12;
  svg.appendChild(el("line", { class: "cal-grid", x1: LAB - 2, y1: sy - 6, x2: LAB + plotW, y2: sy - 6 }));
  svg.appendChild(el("text", {
    class: "cal-row-label", x: LAB - 8, y: sy + 14, "text-anchor": "end",
  }, [txt("현행 현장조사")]));
  svg.appendChild(el("rect", {
    class: "cal-survey", x: LAB, y: sy + 2, width: plotW, height: 17, rx: 3, fill: "none",
  }));
  svg.appendChild(el("text", {
    class: "cal-survey-label", x: LAB + plotW / 2, y: sy + 14, "text-anchor": "middle",
    stroke: "#fff", "stroke-width": 3.5, "paint-order": "stroke",
  }, [txt("5년 1주기 — 해당 연도에 이 습지를 조사하였다는 보장이 없습니다")]));

  host.appendChild(svg);

  const nObs = rows.reduce((a, r) => a + r.n_obs, 0);
  $("calendar-foot").textContent =
    `${S.year}년 ${rows.length}개소 · 관측 ${fmt(nObs)}회를 표시하였습니다` +
    (all.length > rows.length ? ` (조건 부합 ${all.length}개소 중 상위 ${MAX_CAL_ROWS}개소).` : ".") +
    ` 궤도는 습지별로 관측 횟수가 가장 많은 relative orbit 하나로 고정하였습니다. ` +
    `궤도가 혼재되면 입사각이 달라져 후방산란을 직접 비교할 수 없습니다.`;
}

function trim(s, n) {
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

function cellTip(r, o) {
  const state = {
    open: "개방수면",
    veg_covered: "식생피복",
    dry_suspect: "건조 의심",
    no_open_water: "개방수면 지표 비적용",
  }[o.state];
  return `<b>${labelOf(r)}</b><br>${o.date} · ${state}<br>` +
    `개방수면 <b>${fmt(o.open_ha, 1)} ha</b> / 습지면적 ${fmt(r.area_ha)} ha<br>` +
    `VV 평균 <b>${fmt(o.vv_db, 1)} dB</b>` +
    (o.frames > 1 ? `<br><span style="opacity:.75">동일 일자 ${o.frames}장면 평균</span>` : "");
}

/* ---------------- 시계열 ---------------- */

function renderTimeseries() {
  const host = $("timeseries");
  host.innerHTML = "";
  const all = S.years.filter((r) => r.wid === S.sel).sort((a, b) => a.year - b.year);
  if (!all.length) {
    $("ts-title").textContent = "개방수면적 시계열";
    $("ts-sub").textContent = "좌측 목록 또는 관측 달력에서 습지를 선택하시기 바랍니다.";
    $("ts-foot").textContent = "";
    host.innerHTML = '<p style="color:var(--muted);font-size:12px;padding:28px 0;text-align:center">선택된 습지가 없습니다.</p>';
    return;
  }

  const r0 = all[0];
  $("ts-title").textContent = `${labelOf(r0)} — 개방수면적`;
  $("ts-sub").textContent =
    `습지면적 ${fmt(r0.area_ha)} ha · orbit ${r0.rel_orbit} ${r0.orbit_pass === "ASCENDING" ? "상행" : "하행"} · ` +
    `판독 연도 ${all.map((a) => a.year).join(", ")}년`;

  const obs = [];
  for (const yr of all) for (const o of yr.observations) obs.push({ ...o, baseline: yr.open_ratio_baseline });
  obs.sort((a, b) => (a.date < b.date ? -1 : 1));

  const W = Math.max(560, host.clientWidth || 620), H = 250;
  const M = { t: 14, r: 46, b: 26, l: 46 };
  const pw = W - M.l - M.r, ph = H - M.t - M.b;

  const t0 = new Date(obs[0].date).getTime();
  const t1 = new Date(obs[obs.length - 1].date).getTime();
  const X = (d) => M.l + ((new Date(d).getTime() - t0) / Math.max(1, t1 - t0)) * pw;

  const maxHa = Math.max(...obs.map((o) => o.open_ha), 1);
  const Y = (v) => M.t + ph - (v / maxHa) * ph;
  const vvMin = -25, vvMax = -5;
  const YV = (v) => M.t + ph - ((v - vvMin) / (vvMax - vvMin)) * ph;

  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H });

  for (let i = 0; i <= 4; i++) {
    const v = (maxHa / 4) * i;
    svg.appendChild(el("line", { class: "grid-l", x1: M.l, y1: Y(v), x2: M.l + pw, y2: Y(v) }));
    svg.appendChild(el("text", { class: "ax-t", x: M.l - 6, y: Y(v) + 3, "text-anchor": "end" }, [txt(fmt(v, 0))]));
  }
  for (const v of [-20, -15, -10]) {
    svg.appendChild(el("text", { class: "ax-t", x: M.l + pw + 6, y: YV(v) + 3, fill: "var(--veg)" }, [txt(`${v}`)]));
  }

  for (const o of obs) {
    if (o.state === "veg_covered") {
      svg.appendChild(el("rect", { class: "band-veg", x: X(o.date) - 6, y: M.t, width: 12, height: ph }));
    }
  }

  const pts = obs.map((o) => `${X(o.date)},${Y(o.open_ha)}`);
  svg.appendChild(el("polygon", {
    class: "area-open",
    points: `${M.l},${M.t + ph} ${pts.join(" ")} ${M.l + pw},${M.t + ph}`,
  }));
  svg.appendChild(el("polyline", { class: "line-open", points: pts.join(" ") }));
  svg.appendChild(el("polyline", {
    class: "line-vv", points: obs.map((o) => `${X(o.date)},${YV(o.vv_db)}`).join(" "),
  }));

  const optical = all.flatMap((yr) => yr.optical || []);
  for (const p of optical) {
    if (p.ndvi === null || p.ndvi === undefined) continue;
    const yv = M.t + ph - ((p.ndvi + 0.2) / 1.2) * ph;
    const dot = el("circle", { class: "dot-ndvi pt", cx: X(p.date), cy: yv, r: 2.4 });
    dot.onmouseenter = (e) => showTip(e, `${p.date}<br>Sentinel-2 NDVI <b>${fmt(p.ndvi, 2)}</b><br>NDWI <b>${fmt(p.ndwi, 2)}</b>`);
    dot.onmousemove = moveTip;
    dot.onmouseleave = hideTip;
    svg.appendChild(dot);
  }

  for (const o of obs) {
    const c = el("circle", { class: "pt", cx: X(o.date), cy: Y(o.open_ha), r: 3, fill: cellColor(o, o.baseline) });
    c.onmouseenter = (e) => showTip(e,
      `${o.date}<br>개방수면 <b>${fmt(o.open_ha, 1)} ha</b><br>VV <b>${fmt(o.vv_db, 1)} dB</b><br>민감도 검사(Otsu) ${fmt(o.open_ha_alt, 1)} ha`);
    c.onmousemove = moveTip;
    c.onmouseleave = hideTip;
    svg.appendChild(c);
  }

  for (const y of [...new Set(obs.map((o) => o.date.slice(0, 4)))]) {
    const first = obs.find((o) => o.date.startsWith(y));
    svg.appendChild(el("text", { class: "ax-t", x: X(first.date), y: H - 8 }, [txt(y)]));
  }
  svg.appendChild(el("line", { class: "ax", x1: M.l, y1: M.t + ph, x2: M.l + pw, y2: M.t + ph }));
  svg.appendChild(el("text", {
    class: "chart-note", x: M.l + pw, y: M.t + 9, "text-anchor": "end",
  }, [txt("좌축 ha · 우축 VV dB(점선) · 녹색점 Sentinel-2 NDVI")]));

  host.appendChild(svg);

  const nVeg = all.reduce((a, r) => a + r.n_veg_covered, 0);
  const nObs = all.reduce((a, r) => a + r.n_obs, 0);
  $("ts-foot").textContent =
    `관측 ${nObs}회 중 식생피복 ${nVeg}회로 판정되었습니다. ` +
    (optical.length
      ? `Sentinel-2 ${optical.length}장면으로 교차검증하였습니다. 개방수면이 감소한 시기에 NDVI 가 상승하였다면, 이는 수량이 감소한 것이 아니라 수면이 식생에 덮인 것으로 해석합니다.`
      : `본 습지는 광학 교차검증 자료가 아직 수집되지 않았습니다.`);
}

/* ---------------- 습지 판독 요약 ---------------- */

function renderDetail() {
  const host = $("detail");
  const all = S.years.filter((r) => r.wid === S.sel).sort((a, b) => b.year - a.year);
  if (!all.length) {
    host.innerHTML = '<p style="color:var(--muted);font-size:12px">습지를 선택하시면 판독 지표를 표시합니다.</p>';
    return;
  }
  const r = all.find((x) => x.year === S.year) || all[0];
  const stats = [
    ["", fmt(r.area_ha) + " ha", "습지 면적"],
    ["water", r.has_open_water ? fmt(r.open_ha_max, 1) + " ha" : "—", "개방수면 최대(P90)"],
    ["water", r.has_open_water ? fmt(r.open_ha_med, 1) + " ha" : "—", "개방수면 중앙값"],
    ["veg", r.veg_cover_share === null ? "—" : Math.round(r.veg_cover_share * 100) + "%", "식생피복 관측 비중"],
    ["", r.n_obs + "회", `${r.year}년 관측 횟수`],
    ["", fmt(r.revisit_days, 1) + "일", "평균 재방문 주기"],
  ];
  let html = '<div class="detail-grid">' +
    stats.map(([cls, b, s]) => `<div class="stat ${cls}"><b>${b}</b><span>${s}</span></div>`).join("") +
    "</div>";

  if (!r.has_open_water) {
    html += `<div class="note warn">본 습지는 연중 최대 개방수면율이 5% 미만입니다. 삼림습지·초본습지와 같이 SAR 로 관측할 개방수면이 사실상 존재하지 않는 유형으로 판단됩니다. 이 경우 <b>개방수면 지표를 적용하지 않습니다.</b> 기준선이 0에 가까운 상태에서 비율로 피복을 판정하면 의미 없는 수치가 산출되기 때문입니다.</div>`;
  } else if (r.confidence === "low") {
    html += `<div class="note warn">고정임계(−16 dB) 판독과 장면별 Otsu 판독의 차이가 최대 <b>${fmt(r.thr_disagree_ha_max, 1)} ha</b>로, 최대 개방수면적의 20%를 초과합니다. 판독창이 수면과 육지의 이봉 분포를 형성하지 못하는 이질적 폴리곤일 가능성이 높습니다. <b>본 습지의 수치는 판단 근거로 사용하지 마시기 바랍니다.</b></div>`;
  } else {
    const pct = Math.round((r.thr_disagree_ha_max / Math.max(r.open_ha_max, 0.01)) * 100);
    html += `<div class="note">고정임계 판독과 Otsu 판독의 최대 차이는 <b>${fmt(r.thr_disagree_ha_max, 1)} ha</b>로 최대 개방수면적의 ${pct}% 수준입니다. 임계값 선택이 결과를 좌우하지 않음을 확인하였습니다.</div>`;
  }
  host.innerHTML = html;
}

/* ---------------- 위치 ---------------- */

function renderLocator() {
  const host = $("locator");
  host.innerHTML = "";
  if (!S.korea) return;

  const W = 260, H = 300, PAD = 10;
  const LON = [125.5, 130.0], LAT = [33.0, 38.7];
  const X = (lon) => PAD + ((lon - LON[0]) / (LON[1] - LON[0])) * (W - PAD * 2);
  const Y = (lat) => H - PAD - ((lat - LAT[0]) / (LAT[1] - LAT[0])) * (H - PAD * 2);

  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H });
  const drawRing = (ring) =>
    el("path", { class: "loc-land", d: ring.map((c, i) => `${i ? "L" : "M"}${X(c[0]).toFixed(1)},${Y(c[1]).toFixed(1)}`).join("") + "Z" });

  for (const f of S.korea.features) {
    const g = f.geometry;
    const polys = g.type === "Polygon" ? [g.coordinates] : g.coordinates;
    for (const poly of polys) svg.appendChild(drawRing(poly[0]));
  }

  const shown = new Set(rowsForYear().map((r) => r.wid));
  for (const p of S.points) {
    if (!shown.has(p.wid) && p.wid !== S.sel) continue;
    const on = p.wid === S.sel;
    const c = el("circle", { class: "loc-dot" + (on ? " on" : ""), cx: X(p.lon), cy: Y(p.lat), r: on ? 5 : 3 });
    c.onmouseenter = (e) => showTip(e, `<b>${p.name || "무명습지"}</b><br>${fmt(p.area_ha)} ha`);
    c.onmousemove = moveTip;
    c.onmouseleave = hideTip;
    c.style.cursor = "pointer";
    c.onclick = () => select(p.wid);
    svg.appendChild(c);
  }
  host.appendChild(svg);
}

/* ---------------- 안내선 ---------------- */

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
function hideTip() {
  if (tipNode) tipNode.style.display = "none";
}

/* ---------------- 설명 서랍 ---------------- */

const PANELS = {
  method: {
    title: "판독 방법",
    html: `
<h3>SAR 를 사용하는 이유</h3>
<p>습지 수면은 장마철과 태풍기에 가장 크게 변동합니다. 광학 위성은 바로 그 시기에 구름으로
관측이 제한됩니다. Sentinel-1 은 C-band 레이더로서 구름을 투과하여 관측이 가능합니다.</p>

<h3>측정 대상</h3>
<p><b>개방수면적만</b> 측정합니다. 잔잔한 수면은 레이더를 경면반사시켜 후방산란이 급격히
감소하므로, 신호가 크고 방향이 일정하여 판독이 안정적입니다.
반면 식생 하부 침수(이중반사)는 논의 담수 관리 주기와 동일한 대역에서 변동하여 오탐이 심합니다.
따라서 <b>식생 하부 침수는 판정하지 않습니다.</b></p>

<h3>판독 절차</h3>
<ul>
<li>Sentinel-1 GRD, IW 모드, VV+VH — 습지별로 관측이 가장 많은 relative orbit 하나로 고정</li>
<li>스페클 완화: 반경 50 m focal median 적용</li>
<li>개방수면 판정: VV &lt; −16 dB, 경사 5° 초과 지형 제외(산지 레이더 그림자 배제)</li>
<li>습지 폴리곤별 수면 점유율을 산출하여 개방수면적(ha)으로 환산</li>
<li>동일 일자 2장면(프레임 경계)은 평균하여 <b>1회로</b> 계수</li>
</ul>

<h3>임계값을 고정한 이유</h3>
<p>당초 장면별 Otsu 를 주지표로 적용하였으나, 시범 판독에서 대면적·이질 폴리곤의 판독창이
수면과 육지의 이봉 분포를 형성하지 못하여 임계값이 −14.9 ~ −19.4 dB 로 변동하였고,
동일 습지·동일 시기의 면적이 39~123 ha 로 갈렸습니다.
이에 물리적 범위가 안정적인 고정임계를 주지표로 하고 <b>Otsu 는 민감도 검사로만</b> 유지하였습니다.
양자의 차이가 최대 개방수면적의 20%를 초과하는 습지-연도는 <b>저신뢰</b>로 표시합니다.</p>

<h3>광학 교차검증</h3>
<p>개방수면이 감소한 경우 원인은 두 가지입니다 — 수량이 감소하였거나, 식생이 수면을 덮은 것입니다.
동일 폴리곤·동일 기간의 Sentinel-2 NDVI/NDWI 를 함께 산출하여 이를 구분합니다.
NDVI 가 상승하고 NDWI 가 하강하였다면 수량은 유지된 상태에서 수면이 덮인 것으로 해석합니다.</p>`,
  },
  data: {
    title: "자료 출처",
    html: `
<h3>위성 자료</h3>
<table>
<tr><th>자료</th><th>해상도 / 주기</th><th>제공기관</th></tr>
<tr><td>Sentinel-1 GRD (SAR)</td><td>10 m / 12일</td><td>ESA Copernicus</td></tr>
<tr><td>Sentinel-2 SR (광학)</td><td>10~20 m / 5일</td><td>ESA Copernicus</td></tr>
<tr><td>Copernicus DEM GLO-30</td><td>30 m</td><td>ESA</td></tr>
<tr><td>JRC Global Surface Water</td><td>30 m</td><td>EC JRC</td></tr>
</table>
<p>모두 무상 공개 자료입니다. 상용 고해상도 영상은 사용하지 않았습니다.</p>

<h3>습지 경계</h3>
<p><b>현재 화면은 OpenStreetMap 기반의 임시 경계로 운영됩니다</b>
(© OpenStreetMap contributors, ODbL).
정본은 공공데이터포털의 <code>국립생태원_내륙습지 공간데이터 및 속성정보</code>
(내륙습지 2,704개소, SHP, EPSG:5186)이며, 내려받기에 로그인이 필요하여 아직 반영하지 못하였습니다.
정본 자료를 <code>data/raw/nie_inland_wetlands/</code> 에 배치한 후 다시 생성하면
습지명·유형·코드가 그대로 반영되며 화면의 모든 수치가 정본 경계 기준으로 재산출됩니다.</p>

<h3>연계 예정</h3>
<p>국립생태원 생태자연도 오픈API (공공데이터포털 <code>B553084/ecoapi</code>, WMS/WFS/속성조회).
어댑터는 <code>src/nie/ecobank/client.py</code> 에 구현되어 있으며 인증키만 등록하면 연동됩니다.</p>`,
  },
  limits: {
    title: "판독 한계",
    html: `
<h3>수위는 측정하지 않습니다</h3>
<p>SAR 는 수면의 <b>면적</b>을 관측합니다. 수심은 관측하지 않습니다.
개방수면적이 감소하였다는 사실만으로 수위가 저하되었다고 판단할 수 없습니다.</p>

<h3>식생 하부 침수는 판정하지 않습니다</h3>
<p>이중반사 신호는 논의 담수·중간낙수 관리 주기와 동일한 대역에서 변동합니다.
선행 과업(충청남도 농경지)에서 사건 발생 17일 <b>이전</b> 영상이 사건 이후 영상보다 큰 이상치를
산출한 사례가 확인되었습니다. 근거가 확립되기 전까지 본 판정은 산출물에 포함하지 않습니다.</p>

<h3>개방수면이 없는 습지에는 지표를 적용하지 않습니다</h3>
<p>연중 최대 개방수면율이 5% 미만인 습지는 삼림습지·초본습지와 같이
SAR 로 관측할 수면이 존재하지 않는 유형입니다. 이러한 습지는 <b>지표 비적용</b>으로 별도 집계합니다.
기준선이 0에 가까운 상태에서 비율로 피복을 판정하면 의미 없는 수치가 산출됩니다.</p>

<h3>보정이 완료되지 않은 값이 있습니다</h3>
<p>식생피복 판정의 VV 임계 −13 dB 는 시범 습지 1개소(우포늪 2024년)에서 도출한 잠정값입니다.
해당 습지에서 개방수면 관측은 −16~−22 dB, 식생피복 관측은 −8.8~−12 dB 로 구분되었고
그 사이 구간은 관측되지 않았습니다.
<b>전국·습지유형별 보정이 완료되기 전까지 본 임계는 잠정값입니다.</b></p>

<h3>저신뢰 판독을 은폐하지 않습니다</h3>
<p>임계값 선택에 따라 결과가 변동하는 습지-연도는 <b>저신뢰</b>로 표시하여 그대로 제시합니다.
평균에 포함시켜 희석하지 않습니다.</p>`,
  },
};

function wireControls() {
  $("year-select").onchange = (e) => { S.year = Number(e.target.value); renderAll(); };
  $("sort-select").onchange = (e) => { S.sort = e.target.value; renderAll(); };
  $("only-open").onchange = (e) => { S.onlyOpen = e.target.checked; renderAll(); };
  $("rail-search").oninput = debounce((e) => { S.search = e.target.value.trim(); renderAll(); }, 160);

  for (const btn of document.querySelectorAll("[data-panel]")) {
    btn.onclick = () => openPanel(PANELS[btn.dataset.panel]);
  }
  $("drawer-close").onclick = closeDrawer;
  window.addEventListener("resize", debounce(() => { renderCalendar(); renderTimeseries(); }, 180));
}

function openPanel(p) {
  $("drawer-title").textContent = p.title;
  $("drawer-body").innerHTML = p.html;
  $("drawer").hidden = false;
}
function closeDrawer() { $("drawer").hidden = true; }

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
  renderLocator();
  renderOrbits();
}

window.ECOSCOPE = { S, select, openPanel, closeDrawer, labelOf, fmt };
boot();
