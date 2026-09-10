// 국립생태원 공모전 제출서류 통합양식을 워드로 재현하고 제안 내용을 채웁니다.
// 원본 hwpx 의 표 구성·문구를 그대로 옮기되, 제안서 항목만 작성했습니다.

const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  WidthType, AlignmentType, VerticalAlign, ShadingType, BorderStyle,
  HeadingLevel, PageBreak, VerticalMergeType,
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

const 제안명 = "위성 레이더 기반 내륙습지 상시 스크리닝 체계 구축 — 법정조사 주기 사이의 관측 공백 해소";

const 제안요약 = [
  "전국 내륙습지 489개소를 Sentinel-1 위성 레이더로 8개년(2018~2025) 판독하여, 평균 12.3일 간격의 수면 상태 이력 16,314건을 구축하였습니다.",
  "「습지보전법」 제4조 5년 주기 법정조사 사이의 공백을 메워, 어느 습지를 먼저 조사할지 판단할 근거를 상시 공급합니다.",
  "무료 공개위성과 우리원 에코뱅크 오픈API만 사용하며, 시제품이 이미 동작하고 있습니다. 독립 센서 교차검증 결과와 검증에 실패한 항목을 함께 명시합니다.",
];

// [텍스트, 단계] — 0: ○ 제목, 1: - 중항목, 2: · 본문
const 제안내용 = [
  ["추진 배경 및 목적", 0],
  ["현황 및 문제점", 1],
  ["내륙습지 2,704개소를 5년 주기(「습지보전법」 제4조)로 조사합니다. 조사 사이 약 4년의 상태 변화는 기록되지 않고, 어디를 먼저 볼지 판단할 근거도 부족합니다.", 2],
  ["습지 수면은 주 단위로 변합니다. 본 판독에서도 관측 16,314회 중 1,730회(10.6%)에서 개방수면이 해당 습지 기준선의 30% 아래로 내려갔습니다.", 2],
  ["추진 목적 및 필요성", 1],
  ["전수 조사를 대체하지 않고, 조사 우선순위의 근거를 상시 공급합니다.", 2],
  ["판독 대상 489개소 중 120개소는 개방수면율 5% 미만으로, 수면 기반 감시 대상이 아님을 사전 식별할 수 있습니다.", 2],
  ["추진 내용", 0],
  ["추진 개요", 1],
  ["(대상) 하천형·호수형 내륙습지 30헥타르 이상 489개소 판독 완료.", 2],
  ["(기간) 시범운영 6개월, 조사계획 연계 12개월.", 2],
  ["(방법) 에코뱅크 정본 경계 적재 → 궤도 고정 → Sentinel-1 후방산란 -16dB 미만·경사 5도 이하를 수체로 판독 → 상태 분류 → Sentinel-2 광학 교차검증.", 2],
  ["기존 사업·정책과의 차별성", 1],
  ["차별성은 기술이 아니라 산출물의 설계에 있습니다. 판독 결과와 그 신뢰 범위를 함께 싣습니다.", 2],
  ["(검증된 것) 수면 유무 판정의 두 센서 일치율 0.976 (58개소·1,035건). 원리가 다른 레이더와 광학이 독립적으로 같은 판정을 내렸습니다.", 2],
  ["(검증되지 않은 것) 면적 절대값은 치우침은 없으나(평균비 0.993) 시간 변동을 못 따라갑니다(결정계수 중앙값 0.071). 상대 지수로만 표시합니다.", 2],
  ["(기각한 것) 감소 원인의 후방산란 판정(특이도 0.10)과 풍파 가설을 기각하였습니다.", 2],
  ["수혜 대상(범위) 및 혜택 수준", 1],
  ["내륙습지조사·습지보호지역 관리 부서(조사 대상지 선정 시 8개년 이력 활용), 생태정보 부서 및 대국민(생태자연도 등급 병렬 제시 60개소).", 2],
  ["예상되는 문제점 및 극복방안", 1],
  ["(적용 한계) 늪·소택형과 산지형·인공형은 대상이 아닙니다. 적용 범위 명시를 산출물에 포함해 오해를 차단합니다.", 2],
  ["(관측 공백) Sentinel-1B 소실(2021.12)로 일부 궤도가 끊깁니다. 궤도별 관측 이력을 함께 제공합니다.", 2],
  ["(해석 오용) 용어를 법령상 공식 용어·학술 용어·조작적 정의로 구분해 표기합니다.", 2],
];

const 소요예산 = [
  ["신규 예산 확보가 착수의 전제 조건이 아닙니다.", 1],
  ["(산출근거) 위성영상 0원(코페르니쿠스), 습지 경계·생태자연도 0원(에코뱅크·공공데이터포털), 시제품 구축비 0원(구축 완료).", 1],
  ["전국 2,704개소 확대 시 무상 연산 한도를 초과하므로 유상 전환 또는 원내 연산 자원 검토가 필요합니다(단가 별도 산정).", 1],
];

const 기대효과 = [
  ["(관측 주기) 습지 상태 확인 주기 5년 → 위성 재방문 평균 12.3일.", 1],
  ["(관측 범위) 동시 관측 489개소. 본 방법이 성립하는 30헥타르 이상은 전량 판독 완료.", 1],
  ["(조사 효율) 변화가 관측된 습지를 우선 후보로 제시하고, 감시 대상이 아닌 120개소를 사전 식별합니다.", 1],
  ["(기준선 확보) 8개년 이력이 축적되어 향후 조사와 대조할 기준선이 존재합니다.", 1],
  ["(참고) 전국자연환경조사의 현지조사 여비·수당은 2022~2026년 매년 40~45억원, 조사원 570~600명입니다(나라장터 과업설명서). 다만 도엽 단위 수치여서 습지 1개소당 환산 근거가 없어 절감액은 제시하지 않습니다.", 1],
];

const 기타사항 = [
  ["판독 결과 화면(ecoscope-nie.vercel.app), 판독 방법 명세, 검증 기록을 공개하고 있어 심사 과정에서 직접 확인하실 수 있습니다. 개발 과정의 결함과 기각한 가설도 원인·증거와 함께 12건 기록하여 공개하였습니다.", 1],
  ["본 체계는 조사 대상 선정을 보조하는 참고 자료이며 법정조사를 대체하지 않습니다.", 1],
];

function lines(items) {
  return items.map(([text, lvl]) => {
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
