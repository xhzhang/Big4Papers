import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";



async function render() {
  const html = await readFile(new URL("../out/index.html", import.meta.url), "utf8");
  return new Response(html, { status: 200, headers: { "content-type": "text/html; charset=utf-8" } });
}

test("static export renders the SecAtlas application shell", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);
  const html = await response.text();
  assert.match(html, /<title>SecAtlas · 网安四大会论文图谱<\/title>/i);
  assert.match(html, /正在装载论文图谱/);
  assert.doesNotMatch(html, /codex-preview|react-loading-skeleton|Your site is taking shape/i);
});

test("catalog covers all four venues and the controlled priority taxonomy", async () => {
  const raw = await readFile(new URL("../public/catalog.json", import.meta.url), "utf8");
  const catalog = JSON.parse(raw);
  assert.ok(catalog.stats.papers >= 3500, `expected full three-year catalog, got ${catalog.stats.papers}`);
  assert.deepEqual(catalog.coverage.years, [2023, 2024, 2025, 2026]);
  assert.deepEqual(catalog.coverage.venues.sort(), ["ACM CCS", "IEEE S&P", "NDSS", "USENIX Security"].sort());
  assert.deepEqual(catalog.priorityTopics, ["智能手机安全", "AIOS 安全", "认证安全", "智能体安全", "AI 硬件安全", "大模型安全"]);
  assert.ok(catalog.stats.abstracts >= 3400);
  assert.ok(catalog.stats.pdfs >= 2300);
  assert.ok(catalog.stats.sessionPapers >= 4300);
  assert.ok(catalog.stats.sessions >= 700);
  assert.ok(catalog.stats.trackPapers >= 4300);
  assert.ok(catalog.stats.tracks >= 38 && catalog.stats.tracks <= 42);
  assert.equal(catalog.papers.length, catalog.stats.papers);
  assert.ok(catalog.papers.every((paper) => paper.title && paper.venue && paper.year && Array.isArray(paper.authors)));
  assert.ok(catalog.papers.every((paper) => typeof paper.session === "string" && typeof paper.track === "string"));
  assert.equal(catalog.coverageStatus.length, 4);
  assert.ok(catalog.coverageStatus.some((item) => item.venue === "ACM CCS" && item.state === "awaiting"));
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
  assert.match(catalogApp, /归一化 Track/);
  assert.match(catalogApp, /官方 Session/);
  assert.match(excelExport, /name: "论文明细"/);
  assert.match(excelExport, /归一化 Track/);
  assert.match(excelExport, /name: "Track 汇总"/);
  assert.match(excelExport, /name: "方向汇总"/);
  assert.match(excelExport, /name: "标签汇总"/);
});



test("static-publish is a self-contained Vercel static site", async () => {
  const catalogApp = await readFile(new URL("../app/catalog-app.tsx", import.meta.url), "utf8");
  const packageJson = await readFile(new URL("../package.json", import.meta.url), "utf8");
  const vercelConfig = JSON.parse(await readFile(new URL("../vercel.json", import.meta.url), "utf8"));
  const staticHtml = await readFile(new URL("../out/index.html", import.meta.url), "utf8");
  const sourceCatalog = await readFile(new URL("../public/catalog.json", import.meta.url), "utf8");
  const staticCatalog = await readFile(new URL("../out/catalog.json", import.meta.url), "utf8");

  assert.doesNotMatch(catalogApp, /更新数据|\/api\/update|update-status/);
  assert.match(catalogApp, /静态论文库/);
  assert.match(packageJson, /"build": "next build"/);
  assert.match(packageJson, /http\.server 3000 --directory out/);
  assert.equal(vercelConfig.framework, null);
  assert.equal(vercelConfig.outputDirectory, "out");
  assert.equal(vercelConfig.buildCommand, "pnpm build");
  assert.equal(staticCatalog, sourceCatalog);
  assert.match(staticHtml, /<title>SecAtlas/);
});
