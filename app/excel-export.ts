export type ExcelTag = { name: string; type: string };

export type ExcelPaper = {
  id: string;
  title: string;
  venue: string;
  year: number;
  session: string;
  track: string;
  authors: string[];
  doi?: string | null;
  sourceUrl?: string | null;
  pdfUrl?: string | null;
  abstract: string;
  summaryZh: string;
  primaryTopic: string;
  secondaryTopics: string[];
  tags: ExcelTag[];
  analysisStatus: string;
  confidence: number;
};

type CellValue = string | number | null;
type Cell = { value: CellValue; style?: number };
type SheetSpec = {
  name: string;
  rows: Cell[][];
  widths: number[];
  autoFilter?: boolean;
  freezeHeader?: boolean;
  headerHeight?: number;
  rowHeight?: number;
};

const textEncoder = new TextEncoder();
const STYLE = { body: 0, header: 1, wrapped: 2, integer: 3, link: 4, percent: 5, title: 6, label: 7 } as const;
const TAG_TYPE_LABEL: Record<string, string> = { object: "对象", protocol: "协议", technique: "技术", threat: "威胁", goal: "目标" };

function cleanXml(value: unknown) {
  return String(value ?? "")
    .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g, "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;")
    .slice(0, 32767);
}

function columnName(index: number) {
  let value = index + 1;
  let result = "";
  while (value > 0) {
    const remainder = (value - 1) % 26;
    result = String.fromCharCode(65 + remainder) + result;
    value = Math.floor((value - 1) / 26);
  }
  return result;
}

function cellXml(cell: Cell, rowIndex: number, columnIndex: number) {
  const reference = `${columnName(columnIndex)}${rowIndex + 1}`;
  const style = cell.style ? ` s="${cell.style}"` : "";
  if (typeof cell.value === "number" && Number.isFinite(cell.value)) {
    return `<c r="${reference}"${style} t="n"><v>${cell.value}</v></c>`;
  }
  const value = cleanXml(cell.value);
  return `<c r="${reference}"${style} t="inlineStr"><is><t xml:space="preserve">${value}</t></is></c>`;
}

function buildSheetXml(spec: SheetSpec) {
  const rowXml = spec.rows.map((row, rowIndex) => {
    const cells = row.map((cell, columnIndex) => cellXml(cell, rowIndex, columnIndex)).join("");
    const height = rowIndex === 0 ? (spec.headerHeight ?? 24) : (spec.rowHeight ?? 18);
    return `<row r="${rowIndex + 1}" ht="${height}" customHeight="1">${cells}</row>`;
  }).join("");
  const columns = spec.widths.map((width, index) => `<col min="${index + 1}" max="${index + 1}" width="${width}" customWidth="1"/>`).join("");
  const lastCell = `${columnName(Math.max(0, spec.widths.length - 1))}${Math.max(1, spec.rows.length)}`;
  const pane = spec.freezeHeader === false ? "" : '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>';
  const filter = spec.autoFilter === false || spec.rows.length < 2 ? "" : `<autoFilter ref="A1:${lastCell}"/>`;
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetViews><sheetView workbookViewId="0" showGridLines="0">${pane}</sheetView></sheetViews>
  <sheetFormatPr defaultRowHeight="18"/>
  <cols>${columns}</cols>
  <sheetData>${rowXml}</sheetData>
  ${filter}
  <pageMargins left="0.3" right="0.3" top="0.5" bottom="0.5" header="0.2" footer="0.2"/>
</worksheet>`;
}

function cell(value: CellValue, style: number = STYLE.body): Cell {
  return { value, style };
}

function paperRows(papers: ExcelPaper[], courseGroups?: Record<string, string>) {
  const headers = ["论文标题", "研读分组", "会议", "年份", "归一化 Track", "官方 Session", "作者", "主 Topic", "辅助 Topic", "标签", "中文概述", "英文摘要", "论文页面", "PDF", "DOI", "分析置信度", "分析状态"];
  return [
    headers.map((value) => cell(value, STYLE.header)),
    ...papers.map((paper) => [
      cell(paper.title, STYLE.wrapped),
      cell(courseGroups ? (courseGroups[paper.id] || "未分组") : ""),
      cell(paper.venue),
      cell(paper.year, STYLE.integer),
      cell(paper.track || "未归一化", STYLE.wrapped),
      cell(paper.session || "未获取", STYLE.wrapped),
      cell(paper.authors.join("; "), STYLE.wrapped),
      cell(paper.primaryTopic),
      cell(paper.secondaryTopics.join("; ")),
      cell(paper.tags.map((tag) => `${TAG_TYPE_LABEL[tag.type] ?? tag.type}:${tag.name}`).join("; "), STYLE.wrapped),
      cell(paper.summaryZh, STYLE.wrapped),
      cell(paper.abstract, STYLE.wrapped),
      cell(paper.sourceUrl ?? "", STYLE.link),
      cell(paper.pdfUrl ?? "", STYLE.link),
      cell(paper.doi ?? ""),
      cell(paper.confidence, STYLE.percent),
      cell(paper.analysisStatus),
    ]),
  ];
}

function trackRows(papers: ExcelPaper[]) {
  const groups = new Map<string, ExcelPaper[]>();
  for (const paper of papers) {
    const track = paper.track || "未归一化";
    groups.set(track, [...(groups.get(track) ?? []), paper]);
  }
  const headers = ["归一化 Track", "论文数", "占比", "年份", "会议", "官方 Session 示例"];
  const rows = Array.from(groups.entries())
    .sort((a, b) => b[1].length - a[1].length || a[0].localeCompare(b[0], "en"))
    .map(([track, items]) => [
      cell(track),
      cell(items.length, STYLE.integer),
      cell(papers.length ? items.length / papers.length : 0, STYLE.percent),
      cell(Array.from(new Set(items.map((paper) => paper.year))).sort((a, b) => a - b).join("; ")),
      cell(Array.from(new Set(items.map((paper) => paper.venue))).sort().join("; "), STYLE.wrapped),
      cell(Array.from(new Set(items.map((paper) => paper.session).filter(Boolean))).slice(0, 8).join("; "), STYLE.wrapped),
    ]);
  return [headers.map((value) => cell(value, STYLE.header)), ...rows];
}
function topicRows(papers: ExcelPaper[]) {
  const groups = new Map<string, { papers: ExcelPaper[]; tags: Map<string, number> }>();
  for (const paper of papers) {
    const entry = groups.get(paper.primaryTopic) ?? { papers: [], tags: new Map<string, number>() };
    entry.papers.push(paper);
    paper.tags.forEach((tag) => entry.tags.set(tag.name, (entry.tags.get(tag.name) ?? 0) + 1));
    groups.set(paper.primaryTopic, entry);
  }
  const headers = ["主 Topic", "论文数", "占比", "年份", "会议", "高频标签"];
  const rows = Array.from(groups.entries())
    .sort((a, b) => b[1].papers.length - a[1].papers.length || a[0].localeCompare(b[0], "zh-CN"))
    .map(([topic, entry]) => {
      const years = Array.from(new Set(entry.papers.map((paper) => paper.year))).sort((a, b) => a - b).join("; ");
      const venues = Array.from(new Set(entry.papers.map((paper) => paper.venue))).sort().join("; ");
      const tags = Array.from(entry.tags.entries()).sort((a, b) => b[1] - a[1]).slice(0, 8).map(([name, count]) => `${name} (${count})`).join("; ");
      return [cell(topic), cell(entry.papers.length, STYLE.integer), cell(papers.length ? entry.papers.length / papers.length : 0, STYLE.percent), cell(years), cell(venues, STYLE.wrapped), cell(tags, STYLE.wrapped)];
    });
  return [headers.map((value) => cell(value, STYLE.header)), ...rows];
}

function tagRows(papers: ExcelPaper[]) {
  const groups = new Map<string, { type: string; count: number; topics: Set<string> }>();
  for (const paper of papers) {
    for (const tag of paper.tags) {
      const entry = groups.get(tag.name) ?? { type: tag.type, count: 0, topics: new Set<string>() };
      entry.count += 1;
      entry.topics.add(paper.primaryTopic);
      groups.set(tag.name, entry);
    }
  }
  const headers = ["标签", "类型", "论文数", "占比", "涉及主 Topic"];
  const rows = Array.from(groups.entries())
    .sort((a, b) => b[1].count - a[1].count || a[0].localeCompare(b[0]))
    .map(([name, entry]) => [
      cell(name),
      cell(TAG_TYPE_LABEL[entry.type] ?? entry.type),
      cell(entry.count, STYLE.integer),
      cell(papers.length ? entry.count / papers.length : 0, STYLE.percent),
      cell(Array.from(entry.topics).sort().join("; "), STYLE.wrapped),
    ]);
  return [headers.map((value) => cell(value, STYLE.header)), ...rows];
}

function courseGroupRows(papers: ExcelPaper[], courseGroups: Record<string, string>) {
  const groups = new Map<string, ExcelPaper[]>();
  for (const paper of papers) {
    const name = courseGroups[paper.id] || "未分组";
    groups.set(name, [...(groups.get(name) ?? []), paper]);
  }
  const headers = ["研读分组", "论文数", "占比", "年份", "会议", "论文标题"];
  const rows = Array.from(groups.entries())
    .sort((a, b) => b[1].length - a[1].length || a[0].localeCompare(b[0], "zh-CN"))
    .map(([name, items]) => [
      cell(name),
      cell(items.length, STYLE.integer),
      cell(papers.length ? items.length / papers.length : 0, STYLE.percent),
      cell(Array.from(new Set(items.map((paper) => paper.year))).sort((a, b) => a - b).join("; ")),
      cell(Array.from(new Set(items.map((paper) => paper.venue))).sort().join("; "), STYLE.wrapped),
      cell(items.map((paper) => paper.title).join("; "), STYLE.wrapped),
    ]);
  return [headers.map((value) => cell(value, STYLE.header)), ...rows];
}

function infoRows(papers: ExcelPaper[], scopeLabel: string, generatedAt: Date, includesCourseGroups = false) {
  return [
    [cell("SecAtlas 论文导出", STYLE.title), cell("")],
    [cell("导出范围", STYLE.label), cell(scopeLabel)],
    [cell("论文数量", STYLE.label), cell(papers.length, STYLE.integer)],
    [cell("生成时间", STYLE.label), cell(generatedAt.toLocaleString("zh-CN", { hour12: false }))],
    [cell("数据说明", STYLE.label), cell("Topic 与标签为机器候选；中文概述仅在通过标题/摘要证据校验后导出，研读讨论或综述写作前仍请结合论文原文复核。", STYLE.wrapped)],
    [cell("工作表", STYLE.label), cell(`${includesCourseGroups ? "研读分组：按自定义研读主题聚合；" : ""}论文明细：逐篇记录；Track 汇总：跨会议、跨年份聚合；方向汇总：按主 Topic 聚合；标签汇总：按受控标签聚合。`, STYLE.wrapped)],
  ];
}

function stylesXml() {
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <numFmts count="1"><numFmt numFmtId="164" formatCode="0.0%"/></numFmts>
  <fonts count="4">
    <font><sz val="11"/><name val="Aptos"/><color rgb="FF14243A"/></font>
    <font><b/><sz val="11"/><name val="Aptos"/><color rgb="FFFFFFFF"/></font>
    <font><u/><sz val="10"/><name val="Aptos"/><color rgb="FF245D8F"/></font>
    <font><b/><sz val="16"/><name val="Aptos Display"/><color rgb="FF14243A"/></font>
  </fonts>
  <fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF245D8F"/><bgColor indexed="64"/></patternFill></fill></fills>
  <borders count="2"><border/><border><bottom style="thin"><color rgb="FFDCE3EA"/></bottom></border></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="8">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="top"/></xf>
    <xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFill="1" applyFont="1" applyAlignment="1"><alignment vertical="center"/></xf>
    <xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
    <xf numFmtId="1" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyAlignment="1"><alignment horizontal="right" vertical="top"/></xf>
    <xf numFmtId="0" fontId="2" fillId="0" borderId="1" xfId="0" applyFont="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
    <xf numFmtId="164" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyAlignment="1"><alignment horizontal="right" vertical="top"/></xf>
    <xf numFmtId="0" fontId="3" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1"><alignment vertical="center"/></xf>
    <xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFill="1" applyFont="1" applyAlignment="1"><alignment vertical="center"/></xf>
  </cellXfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>`;
}

function workbookFiles(sheets: SheetSpec[], generatedAt: Date) {
  const sheetEntries = sheets.map((sheet, index) => `<sheet name="${cleanXml(sheet.name)}" sheetId="${index + 1}" r:id="rId${index + 1}"/>`).join("");
  const relationships = sheets.map((_, index) => `<Relationship Id="rId${index + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet${index + 1}.xml"/>`).join("");
  const worksheetTypes = sheets.map((_, index) => `<Override PartName="/xl/worksheets/sheet${index + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>`).join("");
  const files: Array<[string, string]> = [
    ["[Content_Types].xml", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>${worksheetTypes}<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/><Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/></Types>`],
    ["_rels/.rels", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>`],
    ["docProps/app.xml", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"><Application>SecAtlas</Application><DocSecurity>0</DocSecurity><ScaleCrop>false</ScaleCrop><Company></Company><LinksUpToDate>false</LinksUpToDate><SharedDoc>false</SharedDoc><HyperlinksChanged>false</HyperlinksChanged><AppVersion>1.0</AppVersion></Properties>`],
    ["docProps/core.xml", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:title>SecAtlas 论文导出</dc:title><dc:creator>SecAtlas</dc:creator><cp:lastModifiedBy>SecAtlas</cp:lastModifiedBy><dcterms:created xsi:type="dcterms:W3CDTF">${generatedAt.toISOString()}</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">${generatedAt.toISOString()}</dcterms:modified></cp:coreProperties>`],
    ["xl/workbook.xml", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><bookViews><workbookView activeTab="0"/></bookViews><sheets>${sheetEntries}</sheets><calcPr calcId="191029"/></workbook>`],
    ["xl/_rels/workbook.xml.rels", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">${relationships}<Relationship Id="rId${sheets.length + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>`],
    ["xl/styles.xml", stylesXml()],
  ];
  sheets.forEach((sheet, index) => files.push([`xl/worksheets/sheet${index + 1}.xml`, buildSheetXml(sheet)]));
  return files;
}

const crcTable = (() => {
  const table = new Uint32Array(256);
  for (let index = 0; index < 256; index += 1) {
    let value = index;
    for (let bit = 0; bit < 8; bit += 1) value = (value & 1) ? (0xEDB88320 ^ (value >>> 1)) : (value >>> 1);
    table[index] = value >>> 0;
  }
  return table;
})();

function crc32(bytes: Uint8Array) {
  let crc = 0xFFFFFFFF;
  for (const byte of bytes) crc = crcTable[(crc ^ byte) & 0xFF] ^ (crc >>> 8);
  return (crc ^ 0xFFFFFFFF) >>> 0;
}

function write16(view: DataView, offset: number, value: number) { view.setUint16(offset, value, true); }
function write32(view: DataView, offset: number, value: number) { view.setUint32(offset, value >>> 0, true); }

function concat(parts: Uint8Array[]) {
  const total = parts.reduce((sum, part) => sum + part.length, 0);
  const output = new Uint8Array(total);
  let offset = 0;
  for (const part of parts) { output.set(part, offset); offset += part.length; }
  return output;
}

function zipStore(files: Array<[string, string]>, date = new Date()) {
  const localParts: Uint8Array[] = [];
  const centralParts: Uint8Array[] = [];
  let localOffset = 0;
  const dosTime = (date.getHours() << 11) | (date.getMinutes() << 5) | Math.floor(date.getSeconds() / 2);
  const dosDate = ((date.getFullYear() - 1980) << 9) | ((date.getMonth() + 1) << 5) | date.getDate();
  for (const [filename, content] of files) {
    const name = textEncoder.encode(filename);
    const data = textEncoder.encode(content);
    const crc = crc32(data);
    const local = new Uint8Array(30 + name.length);
    const localView = new DataView(local.buffer);
    write32(localView, 0, 0x04034B50); write16(localView, 4, 20); write16(localView, 6, 0x0800); write16(localView, 8, 0);
    write16(localView, 10, dosTime); write16(localView, 12, dosDate); write32(localView, 14, crc); write32(localView, 18, data.length); write32(localView, 22, data.length);
    write16(localView, 26, name.length); write16(localView, 28, 0); local.set(name, 30);
    localParts.push(local, data);

    const central = new Uint8Array(46 + name.length);
    const centralView = new DataView(central.buffer);
    write32(centralView, 0, 0x02014B50); write16(centralView, 4, 20); write16(centralView, 6, 20); write16(centralView, 8, 0x0800); write16(centralView, 10, 0);
    write16(centralView, 12, dosTime); write16(centralView, 14, dosDate); write32(centralView, 16, crc); write32(centralView, 20, data.length); write32(centralView, 24, data.length);
    write16(centralView, 28, name.length); write16(centralView, 30, 0); write16(centralView, 32, 0); write16(centralView, 34, 0); write16(centralView, 36, 0);
    write32(centralView, 38, 0); write32(centralView, 42, localOffset); central.set(name, 46);
    centralParts.push(central);
    localOffset += local.length + data.length;
  }
  const centralDirectory = concat(centralParts);
  const end = new Uint8Array(22);
  const endView = new DataView(end.buffer);
  write32(endView, 0, 0x06054B50); write16(endView, 4, 0); write16(endView, 6, 0); write16(endView, 8, files.length); write16(endView, 10, files.length);
  write32(endView, 12, centralDirectory.length); write32(endView, 16, localOffset); write16(endView, 20, 0);
  return concat([...localParts, centralDirectory, end]);
}

export function createPaperWorkbook(papers: ExcelPaper[], scopeLabel: string, generatedAt = new Date(), courseGroups?: Record<string, string>) {
  const sheets: SheetSpec[] = [
    { name: "导出说明", rows: infoRows(papers, scopeLabel, generatedAt, Boolean(courseGroups)), widths: [18, 78], autoFilter: false, freezeHeader: false, headerHeight: 30, rowHeight: 30 },
    { name: "论文明细", rows: paperRows(papers, courseGroups), widths: [48, 24, 20, 10, 30, 36, 40, 22, 28, 42, 52, 72, 48, 48, 24, 14, 14], rowHeight: 54 },
    ...(courseGroups ? [{ name: "研读分组", rows: courseGroupRows(papers, courseGroups), widths: [30, 12, 12, 20, 42, 80], rowHeight: 36 }] : []),
    { name: "Track 汇总", rows: trackRows(papers), widths: [34, 12, 12, 20, 42, 72], rowHeight: 30 },
    { name: "方向汇总", rows: topicRows(papers), widths: [26, 12, 12, 20, 42, 52], rowHeight: 28 },
    { name: "标签汇总", rows: tagRows(papers), widths: [30, 14, 12, 12, 52], rowHeight: 24 },
  ];
  return zipStore(workbookFiles(sheets, generatedAt), generatedAt);
}

export function downloadPaperWorkbook(papers: ExcelPaper[], scopeLabel: string, courseGroups?: Record<string, string>) {
  if (!papers.length) return;
  const bytes = createPaperWorkbook(papers, scopeLabel, new Date(), courseGroups);
  const blob = new Blob([bytes], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  const safeLabel = scopeLabel.replace(/[\\/:*?"<>|]/g, "-").replace(/\s+/g, "-").slice(0, 48) || "论文";
  anchor.href = url;
  anchor.download = `SecAtlas-${safeLabel}-${new Date().toISOString().slice(0, 10)}.xlsx`;
  anchor.click();
  URL.revokeObjectURL(url);
}