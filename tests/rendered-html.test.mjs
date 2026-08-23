import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";



async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  return worker.fetch(
    new Request("http://localhost/", { headers: { accept: "text/html" } }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

test("server-renders the SecAtlas application shell", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);
  const html = await response.text();
  assert.match(html, /<title>SecAtlas · 网安四大会论文图谱<\/title>/i);
  assert.match(html, /正在装载论文图谱/);
  assert.doesNotMatch(html, /codex-preview|react-loading-skeleton|Your site is taking shape/i);
});

test("catalog manifest and annual shards cover the complete corpus", async () => {
  const raw = await readFile(new URL("../public/catalog.json", import.meta.url), "utf8");
  const catalog = JSON.parse(raw);
  const shards = await Promise.all(Object.values(catalog.paperShards).map(async (url) => {
    const payload = JSON.parse(await readFile(new URL(`../public${url}`, import.meta.url), "utf8"));
    return payload.papers;
  }));
  const papers = shards.flat();
  assert.ok(catalog.stats.papers >= 3500, `expected full catalog, got ${catalog.stats.papers}`);
  assert.ok(Buffer.byteLength(raw) < 250_000, "root manifest should stay lightweight");
  assert.deepEqual(catalog.coverage.years, [2023, 2024, 2025, 2026]);
  assert.deepEqual(catalog.coverage.venues.sort(), ["ACM CCS", "IEEE S&P", "NDSS", "USENIX Security"].sort());
  assert.deepEqual(catalog.priorityTopics, ["智能手机安全", "AIOS 安全", "认证安全", "智能体安全", "AI 硬件安全", "大模型安全"]);
  assert.ok(catalog.stats.abstracts >= 3400);
  assert.ok(catalog.stats.pdfs >= 2300);
  assert.ok(catalog.stats.sessionPapers >= 4300);
  assert.ok(catalog.stats.sessions >= 700);
  assert.ok(catalog.stats.trackPapers >= 4300);
  assert.ok(catalog.stats.tracks >= 38 && catalog.stats.tracks <= 42);
  assert.equal(papers.length, catalog.stats.papers);
  assert.ok(papers.every((paper) => paper.title && paper.venue && paper.year && Array.isArray(paper.authors)));
  assert.ok(papers.every((paper) => typeof paper.session === "string" && typeof paper.track === "string"));
  assert.ok(papers.every((paper) => ["research", "program", "other"].includes(paper.trackType)));
  assert.ok(papers.every((paper) => typeof paper.abstractAvailable === "boolean" && !("abstract" in paper) && !("trackMapping" in paper)));
  assert.ok(papers.filter((paper) => paper.session).every((paper) => catalog.trackMappings[paper.session]));
  assert.ok(Object.values(catalog.trackMappings).every((mapping) => mapping.ruleId && typeof mapping.confidence === "number"));
  assert.match(catalog.trackRulesetVersion, /^2026\.07-v\d+$/);
  assert.deepEqual(Object.keys(catalog.paperShards).sort(), ["2023", "2024", "2025", "2026"]);
  assert.deepEqual(Object.keys(catalog.detailShards).sort(), ["2023", "2024", "2025", "2026"]);
  assert.equal(catalog.coverageStatus.length, 4);
  assert.ok(catalog.coverageStatus.some((item) => item.venue === "ACM CCS" && item.state === "partial" && item.publishedCount === 383));
  assert.ok(catalog.coverageStatus.some((item) => item.venue === "USENIX Security" && item.state === "complete" && item.publishedCount === 380));
});

test("starter preview files are removed", async () => {
  const page = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");
  const layout = await readFile(new URL("../app/layout.tsx", import.meta.url), "utf8");
  const packageJson = await readFile(new URL("../package.json", import.meta.url), "utf8");
  const catalogApp = await readFile(new URL("../app/catalog-app.tsx", import.meta.url), "utf8");
  const excelExport = await readFile(new URL("../app/excel-export.ts", import.meta.url), "utf8");
  assert.doesNotMatch(page, /_sites-preview|SkeletonPreview/);
  assert.doesNotMatch(layout, /Starter Project|codex-preview/);
  assert.doesNotMatch(packageJson, /react-loading-skeleton/);
  assert.match(catalogApp, /function CompareView/);
  assert.match(catalogApp, /function TeamsView/);
  assert.match(catalogApp, /导出当前结果 Excel/);
  assert.match(catalogApp, /导出 Excel/);
  assert.match(catalogApp, /props\.tracks\.length === 0/);
  assert.match(catalogApp, /研究 Track/);
  assert.match(catalogApp, /官方 Session/);
  assert.match(excelExport, /name: "论文明细"/);
  assert.match(excelExport, /归一化 Track/);
  assert.match(excelExport, /name: "Track 汇总"/);
  assert.match(excelExport, /name: "方向汇总"/);
  assert.match(excelExport, /name: "标签汇总"/);
});



test("deployment keeps the safe update implementation behind static read-only mode", async () => {
  const catalogApp = await readFile(new URL("../app/catalog-app.tsx", import.meta.url), "utf8");
  const server = await readFile(new URL("../pipeline/server.py", import.meta.url), "utf8");
  const packageJson = await readFile(new URL("../package.json", import.meta.url), "utf8");
  const staticHtml = await readFile(new URL("../dist/client/index.html", import.meta.url), "utf8");
  assert.match(catalogApp, /更新数据/);
  assert.match(catalogApp, /catalogAssetUrl\("api\/update"\)/);
  assert.match(catalogApp, /STATIC_READ_ONLY = true/);
  assert.match(catalogApp, /update-status/);
  assert.match(server, /127\.0\.0\.1/);
  assert.match(server, /scope.*smart/);
  assert.doesNotMatch(server, /shell=True/);
  assert.match(packageJson, /scripts\/export-static\.mjs/);
  assert.match(staticHtml, /<title>SecAtlas/);
});
