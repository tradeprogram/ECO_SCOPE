/* 에코스코프 — 화면 로직.
 *
 * 원칙: 이 파일은 계산하지 않는다. data/ 의 사전 생성 파일이 유일한 수치 출처다.
 * 판독 지표를 바꾸려면 src/nie/wetlands/aggregate.py 를 고치고 다시 빌드할 것.
 */

const S = {
  summary: null,
  years: [],          // wetland_years.json
  points: [],
  korea: null,
  orbits: [],
  year: null,
  sort: "area",
  onlyOpen: true,
  sel: null,
};

const COLOR = {
  water: "#2f6fb0",
  waterSoft: "#cfe0f0",
  veg: "#6f9c1f",
  dry: "#c8801f",
  none: "#dfe5e0",
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
  const [summary, years, points, korea, orbits] = await Promise.all([
    fetch("data/summary.json").then((r) => r.json()),
    fetch("data/wetland_years.json").then((r) => r.json()),
    fetch("data/wetland_points.json").then((r) => r.json()).catch(() => []),
    fetch("data/korea_adm1.geojson").then((r) => r.json()).catch(() => null),
    fetch("data/orbit_history.json").then((r) => r.json()).catch(() => []),
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

/* ---------------- 헤더 ---------------- */

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
  const yearsSpan = s.years.length;
  const perYear = s.mean_obs_per_wetland_year;
  const ratio = Math.round(perYear * 5); // 현장조사 5년 1회 대비
  $("claim").innerHTML =
    `전국 자연환경조사·내륙습지조사는 <b>5년에 1회</b> 돈다. ` +
    `같은 습지를 Sentinel-1은 <b>연 ${fmt(perYear, 1)}회</b> 본다 — ` +
    `한 조사 주기 동안 <b>${fmt(ratio)}배</b>의 관측이 쌓인다. ` +
    `<span style="color:var(--muted)">판독 기간 ${s.years[0]}~${s.years[s.years.length - 1]} (${yearsSpan}개년), ` +
    `자료 생성 ${s.generated_utc.slice(0, 10)}</span>`;
}

/* ---------------- 대상 목록 ---------------- */

function rowsForYear() {
  let rows = S.years.filter((r) => r.year === S.year);
  if (S.onlyOpen) rows = rows.filter((r) => r.has_open_water);
  const key = {
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
  $("rail-count").textContent = S.onlyOpen
    ? `${rows.length}개소 표시 · 전체 ${total}개소 중 개방수면 판독이 성립한 것`
    : `${rows.length}개소 전체`;

  const ul = $("wetland-list");
  ul.innerHTML = "";
  for (const r of rows) {
    const li = document.createElement("li");
    if (S.sel === r.wid) li.className = "on";
    li.dataset.wid = r.wid;

    const tags = [];
    if (!r.has_open_water) tags.push('<span class="tag noopen">개방수면 없음</span>');
    if (r.confidence === "low") tags.push('<span class="tag low">저신뢰</span>');

    li.innerHTML =
      `<div class="wl-name${r.name ? "" : " anon"}">${labelOf(r)}</div>` +
      `<div class="wl-num">${r.has_open_water ? fmt(r.open_ha_max, 1) + " ha" : "—"}</div>` +
      `<div class="wl-meta">${fmt(r.area_ha)} ha · 관측 ${r.n_obs}회 ${tags.join(" ")}</div>`;
    li.onclick = () => select(r.wid);
    ul.appendChild(li);
  }
  if (!rows.length) {
    ul.innerHTML = '<li style="color:var(--muted);font-size:12px">해당 조건의 습지가 없다.</li>';
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

/* Sentinel-1B 는 2021-12 에 고장났고 Sentinel-1C 는 2024-12 에 발사됐다.
 * 그 사이 특정 relative orbit 은 관측이 사실상 끊긴다. 이 표는 그것을 그대로 보여준다.
 * 이 사실을 모르고 시계열을 그리면 '못 본 기간'을 '변하지 않은 기간'으로 읽게 된다. */
function renderOrbits() {
  const host = $("orbits");
  host.innerHTML = "";
  const rec = S.orbits.find((o) => o.wid === S.sel);
  if (!rec) {
    host.innerHTML = '<p style="color:var(--muted);font-size:12px">이 습지의 관측 가능성 이력이 아직 없다.</p>';
    $("orbits-foot").textContent = "";
    return;
  }

  const years = S.summary.years.map(String);
  const orbits = Object.entries(rec.by_orbit_year)
    .map(([orb, byYear]) => ({ orb: Number(orb), byYear, total: Object.values(byYear).reduce((a, b) => a + b, 0) }))
    .sort((a, b) => b.total - a.total)
    .slice(0, 6);

  const cls = (n) => (n === 0 || n < 5 ? "gap" : n >= 20 ? "full" : "part");

  let html = '<table class="orb"><thead><tr><th class="lab">궤도</th>' +
    years.map((y) => `<th>${y}</th>`).join("") + "<th>합계</th></tr></thead><tbody>";
  for (const o of orbits) {
    const chosen = o.orb === rec.chosen_orbit;
    html += `<tr class="${chosen ? "chosen" : ""}"><td class="lab">orbit ${o.orb}</td>` +
      years.map((y) => {
        const n = o.byYear[y] || 0;
        return `<td class="n ${cls(n)}">${n}</td>`;
      }).join("") +
      `<td class="n">${o.total}</td></tr>`;
  }
  html += "</tbody></table>";
  host.innerHTML = html;

  // 끊긴 궤도가 있는지 문장으로도 남긴다
  const broken = orbits.filter((o) => {
    const mid = ["2022", "2023", "2024"].map((y) => o.byYear[y] || 0);
    const early = ["2019", "2020", "2021"].map((y) => o.byYear[y] || 0);
    return early.every((n) => n >= 20) && mid.every((n) => n < 5);
  });
  $("orbits-foot").textContent = broken.length
    ? `orbit ${broken.map((o) => o.orb).join(", ")} 은 2019~2021년 연 20회 이상 관측되다가 ` +
      `2022~2024년 5회 미만으로 끊겼다. Sentinel-1B 가 2021년 12월 고장난 궤도다. ` +
      `2025년 값이 되살아난 것은 2024년 12월 발사된 Sentinel-1C 가 같은 궤도면을 이어받았기 때문이다. ` +
      `이 시계열은 전 기간 연속인 orbit ${rec.chosen_orbit} 하나로 고정해 판독했다.`
    : `전 기간 연속 관측되는 orbit ${rec.chosen_orbit} 하나로 고정해 판독했다. ` +
      `궤도를 섞으면 입사각이 달라져 후방산란을 직접 비교할 수 없다.`;
}

/* ---------------- 관측 달력 (히어로) ---------------- */

const MONTHS = ["1월", "2월", "3월", "4월", "5월", "6월", "7월", "8월", "9월", "10월", "11월", "12월"];

function dayOfYear(iso) {
  const d = new Date(iso + "T00:00:00Z");
  const start = Date.UTC(d.getUTCFullYear(), 0, 1);
  return Math.round((d.getTime() - start) / 86400000);
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
    [COLOR.veg, "식생피복 — 물이 있으나 수면이 덮임"],
    [COLOR.dry, "건조 의심 — 물도 산란체도 없음"],
    [COLOR.none, "개방수면 지표 비적용 습지"],
  ]
    .map(([c, t]) => `<span><i style="background:${c}"></i>${t}</span>`)
    .join("");
}

function renderCalendar() {
  renderLegend();
  const rows = rowsForYear();
  const host = $("calendar");
  host.innerHTML = "";
  if (!rows.length) return;

  const LAB = 132, PAD_R = 14, RH = 17, TOP = 26, SURVEY_H = 34;
  const W = Math.max(760, host.parentElement.clientWidth - 4);
  const plotW = W - LAB - PAD_R;
  const H = TOP + rows.length * RH + SURVEY_H + 12;
  const x = (doy) => LAB + (doy / 365) * plotW;

  const svg = el("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}` });

  // 월 격자 + 라벨
  const monthStart = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334];
  monthStart.forEach((d, i) => {
    svg.appendChild(el("line", { class: "cal-grid", x1: x(d), y1: TOP - 12, x2: x(d), y2: TOP + rows.length * RH }));
    if (i % 2 === 0) {
      svg.appendChild(el("text", { class: "cal-axis", x: x(d) + 3, y: TOP - 15 }, [txt(MONTHS[i])]));
    }
  });

  // 습지 행
  rows.forEach((r, i) => {
    const y = TOP + i * RH;
    const sel = S.sel === r.wid;
    const lab = el("text", {
      class: "cal-row-label" + (sel ? " sel" : ""),
      x: LAB - 8, y: y + 11, "text-anchor": "end",
    }, [txt(trim(labelOf(r), 15))]);
    lab.style.cursor = "pointer";
    lab.onclick = () => select(r.wid);
    svg.appendChild(lab);

    if (sel) {
      svg.appendChild(el("rect", {
        x: LAB - 2, y: y, width: plotW + 2, height: RH - 2,
        fill: "var(--green-soft)", rx: 3,
      }));
    }

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
  svg.appendChild(el("line", {
    class: "cal-grid", x1: LAB - 2, y1: sy - 6, x2: LAB + plotW, y2: sy - 6,
  }));
  svg.appendChild(el("text", {
    class: "cal-row-label", x: LAB - 8, y: sy + 12, "text-anchor": "end",
  }, [txt("현행 현장조사")]));
  svg.appendChild(el("rect", {
    class: "cal-survey", x: LAB, y: sy + 2, width: plotW, height: 17,
    rx: 3, fill: "none",
  }));
  svg.appendChild(el("text", {
    class: "cal-survey-label", x: LAB + plotW / 2, y: sy + 14, "text-anchor": "middle",
    stroke: "#fff", "stroke-width": 3.5, "paint-order": "stroke",
  }, [txt("5년에 1회 — 이 해에 이 습지를 돌았다는 보장이 없다")]));

  host.appendChild(svg);

  const nObs = rows.reduce((a, r) => a + r.n_obs, 0);
  $("calendar-foot").textContent =
    `${S.year}년 ${rows.length}개소 · 관측 ${fmt(nObs)}회. ` +
    `궤도는 습지별로 관측 횟수가 가장 많은 relative orbit 하나로 고정했다 — ` +
    `궤도가 섞이면 입사각이 달라져 후방산란을 직접 비교할 수 없다.`;
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
    `개방수면 <b>${fmt(o.open_ha, 1)} ha</b> / ${fmt(r.area_ha)} ha<br>` +
    `VV 평균 <b>${fmt(o.vv_db, 1)} dB</b>` +
    (o.frames > 1 ? `<br><span style="opacity:.7">같은 날 ${o.frames}장면 평균</span>` : "");
}

/* ---------------- 시계열 ---------------- */

function renderTimeseries() {
  const host = $("timeseries");
  host.innerHTML = "";
  const all = S.years.filter((r) => r.wid === S.sel).sort((a, b) => a.year - b.year);
  if (!all.length) {
    $("ts-title").textContent = "개방수면적 시계열";
    $("ts-sub").textContent = "왼쪽 목록이나 달력에서 습지를 고르면 그 습지의 변화를 그린다.";
    $("ts-foot").textContent = "";
    host.innerHTML = '<p style="color:var(--muted);font-size:12px;padding:26px 0;text-align:center">선택된 습지가 없다.</p>';
    return;
  }

  const r0 = all[0];
  $("ts-title").textContent = `${labelOf(r0)} — 개방수면적`;
  $("ts-sub").textContent =
    `습지면적 ${fmt(r0.area_ha)} ha · orbit ${r0.rel_orbit} ${r0.orbit_pass === "ASCENDING" ? "상행" : "하행"} · ` +
    `${all.map((a) => a.year).join(", ")}년`;

  const obs = [];
  for (const yr of all) for (const o of yr.observations) obs.push({ ...o, baseline: yr.open_ratio_baseline, area: yr.area_ha });
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

  // 가로 격자 + 좌축(ha)
  for (let i = 0; i <= 4; i++) {
    const v = (maxHa / 4) * i;
    svg.appendChild(el("line", { class: "grid-l", x1: M.l, y1: Y(v), x2: M.l + pw, y2: Y(v) }));
    svg.appendChild(el("text", { class: "ax-t", x: M.l - 6, y: Y(v) + 3, "text-anchor": "end" }, [txt(fmt(v, 0))]));
  }
  // 우축(dB)
  for (const v of [-20, -15, -10]) {
    svg.appendChild(el("text", { class: "ax-t", x: M.l + pw + 6, y: YV(v) + 3, fill: "var(--veg)" }, [txt(`${v}`)]));
  }

  // 식생피복 구간 음영
  for (const o of obs) {
    if (o.state === "veg_covered") {
      svg.appendChild(el("rect", { class: "band-veg", x: X(o.date) - 6, y: M.t, width: 12, height: ph }));
    }
  }

  // 개방수면적 면적 + 선
  const pts = obs.map((o) => `${X(o.date)},${Y(o.open_ha)}`);
  svg.appendChild(el("polygon", {
    class: "area-open",
    points: `${M.l},${M.t + ph} ${pts.join(" ")} ${M.l + pw},${M.t + ph}`,
  }));
  svg.appendChild(el("polyline", { class: "line-open", points: pts.join(" ") }));

  // VV 평균
  svg.appendChild(el("polyline", {
    class: "line-vv",
    points: obs.map((o) => `${X(o.date)},${YV(o.vv_db)}`).join(" "),
  }));

  // 광학(NDVI) 점 — 있는 경우만
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

  // 관측점
  for (const o of obs) {
    const c = el("circle", { class: "pt", cx: X(o.date), cy: Y(o.open_ha), r: 3, fill: cellColor(o, o.baseline) });
    c.onmouseenter = (e) => showTip(e, `${o.date}<br>개방수면 <b>${fmt(o.open_ha, 1)} ha</b><br>VV <b>${fmt(o.vv_db, 1)} dB</b><br>민감도(Otsu) ${fmt(o.open_ha_alt, 1)} ha`);
    c.onmousemove = moveTip;
    c.onmouseleave = hideTip;
    svg.appendChild(c);
  }

  // 연도 눈금
  const years = [...new Set(obs.map((o) => o.date.slice(0, 4)))];
  for (const y of years) {
    const first = obs.find((o) => o.date.startsWith(y));
    svg.appendChild(el("text", { class: "ax-t", x: X(first.date), y: H - 8 }, [txt(y)]));
  }
  svg.appendChild(el("line", { class: "ax", x1: M.l, y1: M.t + ph, x2: M.l + pw, y2: M.t + ph }));
  svg.appendChild(el("text", {
    class: "chart-note", x: M.l + pw, y: M.t + 9, "text-anchor": "end",
  }, [txt("좌축 ha · 우축 VV dB(점선) · 초록점 Sentinel-2 NDVI")]));

  host.appendChild(svg);

  const nVeg = all.reduce((a, r) => a + r.n_veg_covered, 0);
  const nObs = all.reduce((a, r) => a + r.n_obs, 0);
  $("ts-foot").textContent =
    `관측 ${nObs}회 중 식생피복 ${nVeg}회. ` +
    (optical.length
      ? `Sentinel-2 ${optical.length}장면으로 교차검증했다 — 개방수면이 줄 때 NDVI 가 오르면 물이 빠진 것이 아니라 수면이 덮인 것이다.`
      : `이 습지는 광학 교차검증 자료가 아직 없다.`);
}

/* ---------------- 습지 카드 ---------------- */

function renderDetail() {
  const host = $("detail");
  const all = S.years.filter((r) => r.wid === S.sel).sort((a, b) => b.year - a.year);
  if (!all.length) {
    host.innerHTML = '<p style="color:var(--muted);font-size:12px">습지를 선택하면 지표를 표시한다.</p>';
    return;
  }
  const r = all[0];
  const stats = [
    ["", fmt(r.area_ha) + " ha", "습지 면적"],
    ["water", (r.has_open_water ? fmt(r.open_ha_max, 1) + " ha" : "—"), "개방수면 최대(P90)"],
    ["water", (r.has_open_water ? fmt(r.open_ha_med, 1) + " ha" : "—"), "개방수면 중앙값"],
    ["veg", (r.veg_cover_share === null ? "—" : Math.round(r.veg_cover_share * 100) + "%"), "식생피복 관측 비중"],
    ["", r.n_obs + "회", `${r.year}년 관측`],
    ["", fmt(r.revisit_days, 1) + "일", "평균 재방문"],
  ];
  let html = '<div class="detail-grid">' +
    stats.map(([cls, b, s]) => `<div class="stat ${cls}"><b>${b}</b><span>${s}</span></div>`).join("") +
    "</div>";

  if (!r.has_open_water) {
    html += `<div class="note warn">이 습지는 연중 최대 개방수면율이 5% 미만이다. 삼림습지·초본습지처럼 SAR 로 볼 개방수면이 사실상 없는 유형으로 보인다. <b>개방수면 지표를 적용하지 않는다</b> — 기준선이 0에 가까운데 비율로 피복을 판정하면 아무 의미 없는 수치가 나온다.</div>`;
  } else if (r.confidence === "low") {
    html += `<div class="note warn">고정임계(-16 dB)와 장면별 Otsu 판독이 최대 <b>${fmt(r.thr_disagree_ha_max, 1)} ha</b> 갈린다 (최대 개방수면적의 20% 초과). 판독창이 물/뭍 이봉을 만들지 못하는 이질적 폴리곤일 가능성이 크다. <b>이 습지의 수치는 신뢰하지 말 것.</b></div>`;
  } else {
    html += `<div class="note">고정임계와 Otsu 판독의 최대 괴리는 <b>${fmt(r.thr_disagree_ha_max, 1)} ha</b>로, 최대 개방수면적의 ${Math.round((r.thr_disagree_ha_max / Math.max(r.open_ha_max, .01)) * 100)}% 수준이다. 임계값 선택이 결과를 좌우하지 않는다.</div>`;
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
    if (!shown.has(p.wid)) continue;
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

/* ---------------- 툴팁 ---------------- */

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
<h3>왜 SAR 인가</h3>
<p>습지 수면은 장마·태풍기에 가장 크게 변한다. 광학 위성은 바로 그때 구름에 막힌다.
Sentinel-1 은 C-band 레이더라 구름을 통과한다.</p>

<h3>무엇을 재는가</h3>
<p><b>개방수면적만</b> 잰다. 잔잔한 수면은 레이더를 경면반사시켜 후방산란이 급락한다 —
신호가 크고 방향이 한쪽이라 판독이 안정적이다.
반대로 식생 아래 침수(이중반사)는 논의 담수 관리 주기와 같은 대역에서 움직여 오탐이 심하다.
그래서 <b>식생 하부 침수는 판정하지 않는다.</b></p>

<h3>절차</h3>
<ul>
<li>Sentinel-1 GRD, IW, VV+VH — 습지별로 관측이 가장 많은 relative orbit 하나로 고정</li>
<li>speckle 완화: 반경 50 m focal median</li>
<li>개방수면: VV &lt; −16 dB, 경사 5° 초과 지형 제외(산지 레이더 그림자 배제)</li>
<li>습지 폴리곤별 수면 점유율 → 개방수면적(ha)</li>
<li>같은 날 두 장면(프레임 경계)은 평균 내고 <b>1회로</b> 센다</li>
</ul>

<h3>임계값을 왜 고정했나</h3>
<p>처음엔 장면별 Otsu 를 주지표로 썼다. 파일럿에서 대면적·이질 폴리곤의 판독창이
물/뭍 이봉을 만들지 못해 임계값이 −14.9 ~ −19.4 dB 로 요동쳤고,
같은 습지·같은 달의 면적이 39~123 ha 로 갈렸다.
그래서 물리 범위가 안정적인 고정임계를 주지표로 두고 <b>Otsu 는 민감도 검사로만</b> 남겼다.
둘이 최대 개방수면적의 20% 넘게 갈리는 습지-연도는 <b>저신뢰</b>로 표시한다.</p>

<h3>광학 교차검증</h3>
<p>개방수면이 줄었을 때 원인이 둘이다 — 물이 빠졌거나, 식생이 덮었거나.
같은 폴리곤·같은 기간의 Sentinel-2 NDVI/NDWI 를 붙여 가른다.
NDVI 가 오르고 NDWI 가 떨어지면 물은 그대로 있고 수면이 덮인 것이다.</p>`,
  },
  data: {
    title: "자료 출처",
    html: `
<h3>위성</h3>
<table>
<tr><th>자료</th><th>해상도/주기</th><th>출처</th></tr>
<tr><td>Sentinel-1 GRD (SAR)</td><td>10 m / 12일</td><td>ESA Copernicus</td></tr>
<tr><td>Sentinel-2 SR (광학)</td><td>10~20 m / 5일</td><td>ESA Copernicus</td></tr>
<tr><td>Copernicus DEM GLO-30</td><td>30 m</td><td>ESA</td></tr>
<tr><td>JRC Global Surface Water</td><td>30 m</td><td>EC JRC</td></tr>
</table>
<p>모두 무료 공개 자료다. 상용 고해상도 영상은 쓰지 않았다.</p>

<h3>습지 경계</h3>
<p><b>현재 화면은 OpenStreetMap 부트스트랩 경계로 돌아간다</b>
(© OpenStreetMap contributors, ODbL).
정본은 공공데이터포털의 <code>국립생태원_내륙습지 공간데이터 및 속성정보</code>
(내륙습지 2,704개소, SHP, EPSG:5186)이며 다운로드에 로그인이 필요해 아직 반영되지 않았다.
정본을 <code>data/raw/nie_inland_wetlands/</code> 에 넣고 다시 빌드하면
습지명·유형·코드가 그대로 들어오고 이 화면의 모든 수치가 정본 경계로 다시 계산된다.</p>

<h3>연계 예정</h3>
<p>국립생태원 생태자연도 오픈API (공공데이터포털 <code>B553084/ecoapi</code>, WMS/WFS/속성조회).
어댑터는 <code>src/nie/ecobank/client.py</code> 에 이미 있고 인증키만 넣으면 붙는다.</p>`,
  },
  limits: {
    title: "이 시스템이 하지 않는 것",
    html: `
<h3>수위를 재지 않는다</h3>
<p>SAR 은 수면의 <b>넓이</b>를 본다. 깊이는 보지 않는다.
개방수면적이 줄었다고 수위가 낮아졌다고 말할 수 없다.</p>

<h3>식생 하부 침수를 판정하지 않는다</h3>
<p>이중반사 신호는 논의 담수·중간낙수 관리 주기와 같은 대역에서 움직인다.
선행 프로젝트(충남 농경지)에서 사건 17일 <b>전</b> 영상이 사건 후보다 큰 이상치를 냈다.
근거가 서기 전까지 이 판정을 화면에 올리지 않는다.</p>

<h3>개방수면이 없는 습지에 지표를 씌우지 않는다</h3>
<p>연중 최대 개방수면율이 5% 미만인 습지는 삼림습지·초본습지처럼
SAR 로 볼 수면이 애초에 없다. 이런 습지는 <b>개방수면 지표 비적용</b>으로 따로 센다.
기준선이 0에 가까운데 비율로 피복을 판정하면 0을 0으로 나누는 꼴이 된다.</p>

<h3>보정되지 않은 값이 있다</h3>
<p>식생피복 판정의 VV 문턱 −13 dB 는 파일럿 습지 하나(우포늪 2024)에서 나온 잠정값이다.
개방수면 관측은 −16~−22 dB, 식생피복 관측은 −8.8~−12 dB 로 갈렸고 그 사이가 비어 있었다.
<b>전국·습지유형별 보정 전까지 이 문턱은 잠정이다.</b></p>

<h3>저신뢰 판독을 숨기지 않는다</h3>
<p>임계값 선택에 결과가 흔들리는 습지-연도는 <b>저신뢰</b>로 표시해 그대로 보여준다.
평균에 섞어 지워버리지 않는다.</p>`,
  },
};

function wireControls() {
  $("year-select").onchange = (e) => { S.year = Number(e.target.value); renderAll(); };
  $("sort-select").onchange = (e) => { S.sort = e.target.value; renderAll(); };
  $("only-open").onchange = (e) => { S.onlyOpen = e.target.checked; renderAll(); };

  for (const btn of document.querySelectorAll("[data-panel]")) {
    btn.onclick = () => openPanel(PANELS[btn.dataset.panel]);
  }
  $("drawer-close").onclick = closeDrawer;
  window.addEventListener("resize", debounce(() => { renderCalendar(); renderTimeseries(); }, 180));
}

function openPanel(p) {
  $("drawer-title").textContent = p.title;
  $("drawer-body").innerHTML = p.html;
  $("drawer-body").className = "drawer-body";
  $("drawer-body").style.padding = "";   // 채팅이 0으로 만들어 둔 것을 되돌린다
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
