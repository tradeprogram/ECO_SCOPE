// 국립생태원 공모전 제출서류 통합양식을 워드로 재현하고 제안 내용을 채웁니다.
// 원본 hwpx 의 표 구성·문구를 그대로 옮기되, 제안서 항목만 작성했습니다.

const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  WidthType, AlignmentType, VerticalAlign, ShadingType, BorderStyle,
  HeadingLevel, PageBreak, VerticalMergeType, ImageRun,
} = require("docx");

const FONT = "휴먼명조";
const W = 9000;                 // 표 전체 폭(DXA)
const LAB = 1900;               // 라벨 열
const VAL = W - LAB;

// 본문 12pt = half-points 24. 양식이 요구하는 줄간격 160% (240*1.6=384) 는
// **작성한 제안 내용**에만 적용합니다. 양식이 원래 갖고 있던 표·안내문까지
// 160% 로 벌리면 제안 내용이 밀려 3페이지를 넘깁니다.
const LINE160 = { line: 384, lineRule: "auto" };
const LINE = { line: 240, lineRule: "auto" };

function t(text, opt = {}) {
  return new TextRun({ text, font: FONT, size: opt.size ?? 24, bold: !!opt.bold, ...opt });
}
function p(text, opt = {}) {
  return new Paragraph({
    alignment: opt.align,
    spacing: { ...(opt.wide ? LINE160 : LINE),
               before: opt.before ?? 0, after: opt.after ?? 0 },
    indent: opt.indent,
    children: text === "" ? [] : [t(text, opt)],
  });
}
function cell(children, opt = {}) {
  return new TableCell({
    width: { size: opt.width ?? VAL, type: WidthType.DXA },
    columnSpan: opt.span,
    verticalMerge: opt.vMerge,
    verticalAlign: opt.vAlign ?? VerticalAlign.CENTER,
    shading: opt.shade ? { type: ShadingType.CLEAR, fill: opt.shade } : undefined,
    margins: { top: 40, bottom: 40, left: 120, right: 120 },
    children: Array.isArray(children) ? children : [children],
  });
}
function labelCell(text, vMerge) {
  return cell(p(text, { bold: true, align: AlignmentType.CENTER }),
              { width: LAB, shade: "F2F2F2", vMerge });
}
function row(cells) { return new TableRow({ children: cells }); }
function table(rows, cols) {
  return new Table({
    columnWidths: cols ?? [LAB, VAL],
    width: { size: W, type: WidthType.DXA },
    rows,
  });
}
function title(text) {
  return new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 240, after: 240 },
    children: [t(text, { bold: true, size: 32 })],
  });
}
function blank(n = 1) {
  return Array.from({ length: n }, () => p(""));
}

/* ── 공모분야 / 참가형태 셀 ─────────────────────────────────────────── */

const FIELD_LEFT = [
  p("□ 협력기반 생태가치 창출"),
  p("· 생태데이터 개방·활용 확대", { size: 20 }),
  p("· 생태계 보전 및 기후위기 대응", { size: 20 }),
  p("· 민간성장지원 및 협력 강화", { size: 20 }),
];
const FIELD_MID = [
  p("□ 국민 체감 생태가치 확산"),
  p("· 수요자 맞춤 디지털서비스 고도화", { size: 20 }),
  p("· 시민참여 중심 생태가치 확산", { size: 20 }),
  p("· 국민신뢰 기반 적극행정·소통", { size: 20 }),
];
const FIELD_RIGHT = [
  p("☑ 지속가능 혁신경영 고도화", { bold: true }),
  p("· AX 기반 업무효율화", { size: 20, bold: true }),
  p("· ESSG 경영 실행성과 강화", { size: 20 }),
  p("· 성과·환류 기반 혁신경영 확립", { size: 20 }),
];
function fieldRow() {
  const w = Math.floor(VAL / 3);
  return row([
    labelCell("공모분야\n(3개중 택1 ☑)"),
    cell(FIELD_LEFT, { width: w, vAlign: VerticalAlign.TOP }),
    cell(FIELD_MID, { width: w, vAlign: VerticalAlign.TOP }),
    cell(FIELD_RIGHT, { width: VAL - 2 * w, vAlign: VerticalAlign.TOP }),
  ]);
}
const FIELD_COLS = (() => {
  const w = Math.floor(VAL / 3);
  return [LAB, w, w, VAL - 2 * w];
})();


/* ── 그림 ────────────────────────────────────────────────────────────────
   제안 내용 칸 폭(약 7100 DXA ≈ 12.5cm)에 맞춰 넣습니다. 캡션은 그림 바로
   아래 작은 글씨로 답니다. 원본은 2배 해상도로 떠서 인쇄해도 뭉개지지 않습니다. */
const FIGDIR = process.argv[3] || "figures";
const FIG_W = 395;                       // pt 단위 표시 폭

function figure(file, ratio, caption, width) {
  const w = width ?? FIG_W;
  return [
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 100, after: 40 },
      children: [new ImageRun({
        type: "png",
        data: fs.readFileSync(`${FIGDIR}/${file}`),
        transformation: { width: w, height: Math.round(w * ratio) },
      })],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 120 },
      children: [t(caption, { size: 18 })],
    }),
  ];
}

/* ── 1. 참가신청서 ──────────────────────────────────────────────────── */

function applicationForm() {
  const q = Math.floor(VAL / 4);
  const cols4 = [LAB, q, q, q, VAL - 3 * q];
  const person = (label, note) => [
    row([
      labelCell(label, VerticalMergeType.RESTART),
      cell(p("성명", { align: AlignmentType.CENTER }), { width: q, shade: "FAFAFA" }),
      cell(p(note ?? ""), { width: q }),
      cell(p("생년월일", { align: AlignmentType.CENTER }), { width: q, shade: "FAFAFA" }),
      cell(p(""), { width: VAL - 3 * q }),
    ]),
    row([
      labelCell("", VerticalMergeType.CONTINUE),
      cell(p("이메일", { align: AlignmentType.CENTER }), { width: q, shade: "FAFAFA" }),
      cell(p(""), { width: q }),
      cell(p("연락처", { align: AlignmentType.CENTER }), { width: q, shade: "FAFAFA" }),
      cell(p(""), { width: VAL - 3 * q }),
    ]),
    row([
      labelCell("", VerticalMergeType.CONTINUE),
      cell(p("우리원 직원여부", { align: AlignmentType.CENTER, size: 20 }), { width: q, shade: "FAFAFA" }),
      cell(p(""), { width: q }),
      cell(p("소속", { align: AlignmentType.CENTER }), { width: q, shade: "FAFAFA" }),
      cell(p("우리원 직원일 경우 작성", { size: 18 }), { width: VAL - 3 * q }),
    ]),
  ];

  return [
    p("붙임", { bold: true }),
    title("공모전 제출서류 통합 양식"),
    title("「2026년도 국립생태원 대국민 경영혁신 아이디어 공모전」 참가신청서"),
    table([
      row([labelCell("접수번호"), cell(p("※ 신청자 기재금지", { size: 20 }))]),
    ]),
    table([fieldRow()], FIELD_COLS),
    table([
      row([labelCell("참가형태"),
           cell(p("☑ 개인    □ 단체 (단체명:                    )"))]),
    ]),
    table([
      ...person("참가자 정보\n(단체는 대표자)"),
      ...person("참가자 정보\n(팀원①)", ""),
      ...person("참가자 정보\n(팀원②)", ""),
    ], cols4),
    ...blank(1),
    p("※ 주요 유의사항 (공고문 및 유의사항 필수 참조)", { bold: true, size: 20 }),
    p("1. 제출된 제안의 저작권은 참가자에게 있으며, 응모와 동시에 추후 수상 시 국립생태원에 수상작 활용을 허락한 것으로 보고, 저작권에 대한 이용료는 수상에 따른 포상금으로 대체합니다.", { size: 20 }),
    p("2. 타 공모전 입상작 등 다른 작품과 유사성·모방성이 인정되는 경우 심사대상에서 제외되며, 수상하였더라도 추후 밝혀질 경우 수상취소 및 상금을 환수할 수 있습니다.", { size: 20 }),
    p("3. 제출된 모든 서류는 일체 반환하지 않으며, 제출 서류 상의 기재착오나 연락불능으로 인한 불이익의 책임은 제안자에게 있습니다.", { size: 20 }),
    ...blank(1),
    p("2026년        월        일", { align: AlignmentType.CENTER }),
    p("참가자(대표자) 성명 :                        (서명 또는 인)", { align: AlignmentType.CENTER }),
    p("국립생태원장 귀하", { align: AlignmentType.CENTER, bold: true, size: 28, before: 160 }),
  ];
}

/* ── 2. 공모전 제안서 ───────────────────────────────────────────────── */

const 제안명 = "5년에 한 번을 12일에 한 번으로 — 위성 레이더 기반 내륙습지 상시 스크리닝 체계";

const 제안요약 = [
  "5년마다 한 번 보던 내륙습지를 평균 12.3일마다 볼 수 있게 하였습니다. 법정조사 1주기 동안의 관측량이 150배가 됩니다.",
  "제안이 아니라 실적입니다. 전국 489개소를 8개년(2018~2025) 판독하여 SAR 관측 16,314회를 이미 처리하였고, 결과는 공개 운영 중입니다.",
  "추가 예산이 필요 없습니다. 무료 공개위성과 우리원이 이미 개방한 에코뱅크 오픈API만으로 구성됩니다.",
  "정확도를 함께 냅니다. 광학 위성과 대조해 수면 유무 판정 일치율 0.976을 확인하였고, 검증되지 않은 수치는 산출물에서 뺐습니다.",
];

// [텍스트, 단계] — 0: ○ 제목, 1: - 중항목, 2: · 본문
const 제안내용 = [
  ["추진 배경 및 목적", 0],
  ["현황 및 문제점 — 5년에 한 번, 그 사이는 공백입니다", 1],
  ["우리원은 내륙습지 2,704개소를 관리하지만 법정조사 주기는 5년입니다(「습지보전법」 제4조). 조사와 조사 사이 4년 동안 무슨 일이 일어나는지 확인할 상시 수단이 없습니다.", 2],
  ["그 4년은 조용하지 않습니다. 본 판독에서 관측 16,314회 중 1,730회(10.6%)에서 개방수면이 기준선의 30% 아래로 내려갔습니다. 습지 수면은 주 단위로 움직입니다.", 2],
  ["대상지 선정도 같습니다. 어디를 먼저 볼지 판단할 정량 근거가 없어 조사 인력 배분이 경험에 의존합니다.", 2],
  { fig: "fig2_calendar.png", ratio: 0.459,
    cap: "[그림 1] 관측 달력 — 칸 하나가 Sentinel-1 관측 1회. 5년 주기로는 보이지 않던 연중 변동이 습지마다 기록된다." },
  ["추진 목적 — 조사를 대체하지 않고 그 사이를 메웁니다", 1],
  ["법정조사는 대체할 수 없습니다. 본 제안은 빈 4년을 메우고, 다음 조사가 어디로 가야 하는지를 숫자로 제시합니다.", 2],
  ["자료는 이미 무료로 내려오고 있습니다. Sentinel 위성이 12일마다 한반도를 찍고, 우리원은 습지 경계를 에코뱅크로 개방해 두었습니다.", 2],
  ["추진 내용", 0],
  ["추진 실적 — 제안이 아니라 이미 낸 결과입니다", 1],
  ["전국 489개소 · 8개년(2018~2025) · SAR 관측 16,314회를 처리하였습니다. 본 방법이 성립하는 하천형·호수형 30헥타르 이상은 전량 판독을 마쳤습니다.", 2],
  ["결과는 공개 운영 중이며, 담당자가 습지별 시계열·관측 달력·생태자연도 등급을 보고 조사 계획용 CSV 로 내려받을 수 있습니다.", 2],
  { fig: "fig1_screen.png", ratio: 0.641,
    cap: "[그림 2] 실행 화면 (ecoscope-nie.vercel.app) — 지금 접속하면 동작하는 결과물이다." },
  ["실행 방법 — 에코뱅크 정본 경계 적재 → 습지별 궤도 고정 → Sentinel-1 후방산란 −16dB 미만·경사 5도 이하를 수체로 판독 → 상태 분류 → Sentinel-2 광학 교차검증. 시범운영 6개월, 조사계획 연계 12개월을 제안합니다.", 1],
  ["차별성 — 세 가지", 1],
  ["첫째, 전국 규모의 실증입니다. 시범 몇 개소가 아니라 489개소·8개년을 실제로 돌려 결과를 냈습니다.", 2],
  ["둘째, 정확도를 함께 냅니다. 58개소·짝지은 관측 1,035건을 광학 위성과 대조해 수면 유무 판정 일치율 0.976을 확인하였습니다. 원리가 다른 두 센서가 독립적으로 같은 판정을 내렸습니다.", 2],
  ["셋째, 쓸 수 없는 것을 먼저 밝힙니다. 면적 절대값은 시간 변동을 못 따라가 산출물에서 뺐고(결정계수 중앙값 0.071), 감소 원인 판정과 풍파 보정 가설은 검증에 실패해 철회하였습니다. 의사결정 자료는 틀릴 수 있는 범위가 명시되어야 실무에서 쓸 수 있습니다.", 2],
  ["수혜 대상 및 혜택 수준", 1],
  ["내륙습지조사·습지보호지역 관리 부서는 대상지 선정에 8개년 이력을 활용하고, 생태정보 부서는 생태자연도 등급과 판독 결과의 정합성을 점검할 수 있습니다. 대국민으로는 에코뱅크 개방자료의 활용 사례가 됩니다.", 2],
  ["예상되는 문제점 및 극복방안", 1],
  ["(적용 한계) 늪·소택형과 산지형·인공형은 대상이 아닙니다. 적용 범위를 산출물에 명시해 오·적용을 막습니다.", 2],
  ["(관측 공백) Sentinel-1B 소실(2021.12)로 일부 궤도가 끊깁니다. 궤도별 관측 이력을 함께 제공해 공백을 '변화 없음'으로 읽지 않게 하였습니다.", 2],
  ["(해석 오용) 용어를 법령상 공식 용어·학술 용어·조작적 정의로 구분해 표기합니다.", 2],
];

const 소요예산 = [
  ["추가 예산 없이 즉시 착수할 수 있습니다. 무료 공개위성과 우리원이 이미 개방한 자료만으로 구성됩니다.", 1],
  ["(산출근거) 위성영상 0원(코페르니쿠스 무료 공개) · 습지 경계·생태자연도 0원(에코뱅크 오픈API·공공데이터포털) · 시스템 구축비 0원(구축 완료, 운영 중).", 1],
  ["전국 2,704개소로 확대할 경우 무상 연산 한도를 넘으므로 유상 전환 또는 원내 연산 자원 활용 검토가 필요합니다(단가 별도 산정).", 1],
];

const 기대효과 = [
  ["(관측 주기) 5년 → 평균 12.3일. 법정조사 1주기 동안의 관측량으로 환산하면 약 150배입니다.", 1],
  ["(관측 범위) 조사 인력에 비례하던 동시 관측 습지가 489개소로 늘어납니다. 30헥타르 이상 하천형·호수형은 이미 전량 판독을 마쳤습니다.", 1],
  ["(조사 효율) 변화가 관측된 습지를 우선 후보로 제시합니다. 개방수면이 발달하지 않아 이 방식의 대상이 아닌 120개소를 미리 걸러 조사 자원의 낭비를 막습니다.", 1],
  ["(기준선 확보) 2018년 이후 8개년 이력이 이미 쌓여 있습니다. 다음 법정조사 결과를 대조할 기준선이 지금 존재합니다.", 1],
  
  ["(비용 절감) 전국자연환경조사의 현지조사 여비·수당만 2022~2026년 매년 40~45억원, 조사원 570~600명 규모입니다(나라장터 과업설명서). 다만 도엽 단위 수치여서 습지 1개소당 환산 근거가 확인되지 않아 절감액은 제시하지 않습니다.", 1],
];

const 기타사항 = [
  ["심사 과정에서 직접 확인하실 수 있습니다. 판독 결과 화면(ecoscope-nie.vercel.app)과 판독 방법 명세, 전체 소스코드를 공개하고 있습니다.", 1],
  ["개발 과정의 결함과 기각한 가설도 원인·증거와 함께 12건 기록하여 공개하였습니다. 무엇이 틀렸었는지를 남기는 것이 결과의 신뢰성을 뒷받침한다고 보았습니다.", 1],
  ["본 체계는 조사 대상 선정을 보조하는 참고 자료이며, 법정조사를 대체하거나 습지의 법적 상태를 판정하는 근거가 아닙니다.", 1],
];

function lines(items) {
  return items.flatMap((it) => {
    // 그림 항목: { fig, ratio, cap, w }
    if (it && it.fig) return figure(it.fig, it.ratio, it.cap, it.w);
    const [text, lvl] = it;
    if (lvl === 0) return p("○ " + text, { bold: true, before: 60, wide: true });
    if (lvl === 1) return p(" - " + text, { wide: true, indent: { left: 200, hanging: 120 } });
    return p("· " + text, { wide: true, indent: { left: 480, hanging: 140 } });
  });
}

function proposalForm() {
  return [
    new Paragraph({ children: [new PageBreak()] }),
    title("공모전 제안서"),
    table([
      row([labelCell("접수번호"), cell(p("※ 신청자 기재금지", { size: 20 }))]),
    ]),
    table([fieldRow()], FIELD_COLS),
    table([
      row([labelCell("제 안 명"), cell(p(제안명))]),
      row([labelCell("제안 요약"),
           cell(제안요약.map((s) => p("- " + s, { wide: true, indent: { left: 180, hanging: 120 } })),
                { vAlign: VerticalAlign.TOP })]),
      row([cell([
        p("제안 내용", { bold: true, align: AlignmentType.CENTER }),
        p("※ A4 용지 1페이지 이상 3페이지 이내, 휴먼명조 12, 줄 간격 160%", { size: 18, align: AlignmentType.CENTER }),
      ], { span: 2, width: W, shade: "F2F2F2" })]),
      row([cell(lines(제안내용), { span: 2, width: W, vAlign: VerticalAlign.TOP })]),
      row([labelCell("소요예산"),
           cell(lines(소요예산), { vAlign: VerticalAlign.TOP })]),
      row([labelCell("기대효과"),
           cell(lines(기대효과), { vAlign: VerticalAlign.TOP })]),
      row([labelCell("기타사항"),
           cell(lines(기타사항), { vAlign: VerticalAlign.TOP })]),
    ]),
  ];
}

/* ── 3. 개인정보 동의서 ─────────────────────────────────────────────── */

function privacyForm() {
  return [
    new Paragraph({ children: [new PageBreak()] }),
    title("개인정보 수집 · 이용 동의서"),
    p("‘2026년도 국립생태원 대국민 경영혁신 아이디어 공모전’과 관련하여 「개인정보 보호법」 제15조(개인정보의 수집·이용)에 따라 아래와 같이 귀하의 개인정보 수집·이용에 대한 동의를 얻고자 합니다.", { size: 22 }),
    ...blank(1),
    p("1. 개인정보의 수집·이용 목적", { bold: true }),
    p("본인확인 및 응모작에 대한 개인 식별, 공지사항 전달 및 질의응답, 시상 및 포상지급 등 공모전 관리를 위한 용도로만 사용됩니다.", { size: 22 }),
    p("※ 공모전 결과를 대내·외로 홍보 또는 국립생태원 사업으로 추진할 경우, 필요 시 응모자의 개인정보를 공개할 수 있음(성명 등 최소한의 정보에 한함)", { size: 20 }),
    p("2. 수집하려는 개인정보의 항목", { bold: true }),
    p("성명, 연락처, 생년월일, 이메일", { size: 22 }),
    p("3. 개인정보의 보유 및 이용 기간", { bold: true }),
    p("수집일로부터 공모전 종료 당해 연도(2026. 12. 31.)까지 보유 및 활용하며, 보유기간 경과 시 즉시 파기합니다.", { size: 22 }),
    p("4. 동의 및 거부권리 안내", { bold: true }),
    p("귀하는 「개인정보보호법」에 의해 개인정보 수집·이용에 대해 동의를 거부할 권리가 있으며, 거부 시에는 공모전 응모에 제한될 수 있음을 알려드립니다.", { size: 22 }),
    ...blank(1),
    p("본인은 「개인정보보호법」 등 관련 법규에 의거하여, 위와 같이 개인정보 수집·이용에 동의합니다."),
    ...blank(1),
    p("□ 동의함          □ 동의하지 않음", { align: AlignmentType.CENTER }),
    ...blank(1),
    p("2026년        월        일", { align: AlignmentType.CENTER }),
    p("참가자 성명 :                        (서명 또는 인)", { align: AlignmentType.CENTER }),
    p("국립생태원장 귀하", { align: AlignmentType.CENTER, bold: true, size: 28, before: 160 }),
  ];
}

/* ── 4. 사적이해관계 확인서 ─────────────────────────────────────────── */

function conflictForm() {
  const half = Math.floor(VAL / 2);
  return [
    new Paragraph({ children: [new PageBreak()] }),
    title("사적이해관계 여부 확인서 및 회피 신청서"),
    p("국립생태원은 「2026년도 대국민 경영혁신 아이디어 공모전」 수상작 선정과정에서 공모전 참가자와 사적 이해관계로 인한 부패발생 소지를 사전에 차단함과 동시에 공정하고 청렴한 심사를 위하여 아래와 같이 사적 이해관계 여부를 확인하고 있으니, 해당하는 내용을 작성하여 주시기 바랍니다.", { size: 22 }),
    ...blank(1),
    table([
      row([labelCell("참가자", VerticalMergeType.RESTART),
           cell(p("성명", { align: AlignmentType.CENTER }), { width: 1200, shade: "FAFAFA" }),
           cell(p(""), { width: 2100 }),
           cell(p("생년월일", { align: AlignmentType.CENTER }), { width: 1300, shade: "FAFAFA" }),
           cell(p(""), { width: VAL - 4600 })]),
      row([labelCell("", VerticalMergeType.CONTINUE),
           cell(p("연락처", { align: AlignmentType.CENTER }), { width: 1400, shade: "FAFAFA" }),
           cell(p("☎"), { width: VAL - 1400, span: 3 })]),
    ], [LAB, 1200, 2100, 1300, VAL - 4600]),
    ...blank(1),
    p("※ 해당하는 항목에 체크(∨) 표시해 주세요.", { size: 20 }),
    table([
      row([cell(p("사적이해관계 여부 확인", { bold: true, align: AlignmentType.CENTER }),
                { span: 2, width: W, shade: "F2F2F2" })]),
      row([cell(p("국립생태원 소속 임원 또는 직원으로 재직한 경험(2년 이내)이 있는가?"), { width: W - 1800 }),
           cell(p("□ 예    □ 아니오", { align: AlignmentType.CENTER }), { width: 1800 })]),
      row([cell(p("배우자 또는 4촌 이내 친족 중 국립생태원에 재직하고 있는 임원 또는 직원이 있는가?"), { width: W - 1800 }),
           cell(p("□ 예    □ 아니오", { align: AlignmentType.CENTER }), { width: 1800 })]),
    ], [W - 1800, 1800]),
    ...blank(1),
    p("이해충돌 회피 신청", { bold: true }),
    p("위에서 “예”에 하나 이상 답변한 경우, 다음의 사적이해관계자가 공모전 심사업무에 참여하는 것에 대해 회피를 신청합니다.", { size: 22 }),
    table([
      row([labelCell("사적이해관계자\n(국립생태원 임직원)"),
           cell(p("성명", { align: AlignmentType.CENTER }), { width: 1400, shade: "FAFAFA" }),
           cell(p(""), { width: half - 1400 }),
           cell(p("연락처", { align: AlignmentType.CENTER }), { width: 1400, shade: "FAFAFA" }),
           cell(p("☎"), { width: VAL - half - 1400 })]),
      row([labelCell("", VerticalMergeType.CONTINUE),
           cell(p("부서", { align: AlignmentType.CENTER }), { width: 1400, shade: "FAFAFA" }),
           cell(p(""), { width: half - 1400 }),
           cell(p("직위", { align: AlignmentType.CENTER }), { width: 1400, shade: "FAFAFA" }),
           cell(p(""), { width: VAL - half - 1400 })]),
    ], [LAB, 1400, half - 1400, 1400, VAL - half - 1400]),
    ...blank(1),
    p("「2026년도 대국민 경영혁신 아이디어 공모전」 참가와 관련하여 사적이해관계 여부에 대하여 위와 같이 확인합니다. 만약 위 사항이 사실과 다른 경우에는 심사대상에서 제외되며, 수상하였더라도 추후 밝혀질 경우 수상취소 및 상금 환수 등 어떠한 불이익도 감수할 것을 서약합니다.", { size: 22 }),
    ...blank(2),
    p("2026년        월        일", { align: AlignmentType.CENTER }),
    ...blank(1),
    p("참가자 :                        (서명 또는 인)", { align: AlignmentType.CENTER }),
  ];
}

/* ── 문서 ───────────────────────────────────────────────────────────── */

const doc = new Document({
  styles: {
    default: {
      document: { run: { font: FONT, size: 24 }, paragraph: { spacing: LINE } },
    },
  },
  sections: [{
    properties: {
      page: { margin: { top: 1000, right: 1000, bottom: 1000, left: 1000 } },
    },
    children: [
      ...applicationForm(),
      ...proposalForm(),
      ...privacyForm(),
      ...conflictForm(),
    ],
  }],
});

Packer.toBuffer(doc).then((buf) => {
  const out = process.argv[2] || "out.docx";
  fs.writeFileSync(out, buf);
  console.log("작성 완료:", out, `(${(buf.length / 1024).toFixed(0)} KB)`);
});
