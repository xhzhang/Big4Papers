import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(path, import.meta.url), "utf8");

test("catalog exposes navigable pagination and summary evidence", async () => {
  const [app, insights] = await Promise.all([
    read("../app/catalog-app.tsx"),
    read("../app/catalog-insights.tsx"),
  ]);

  assert.match(app, /<CatalogPagination/);
  assert.match(app, /已概述 \{fmt\(semanticSummaryCount\)\}/);
  assert.match(app, /仅标题概述/);
  assert.match(insights, /className="pagination-pages"/);
  assert.match(insights, /id="page-jump"/);
  assert.match(insights, /中文概述证据覆盖/);
});

test("team discovery and track analysis remain searchable", async () => {
  const [app, insights, layout] = await Promise.all([
    read("../app/catalog-app.tsx"),
    read("../app/catalog-insights.tsx"),
    read("../app/layout.tsx"),
  ]);

  assert.match(app, /placeholder="作者、合作者、论文、Track 或标签"/);
  assert.match(app, /groups\.length >= 240/);
  assert.match(insights, /四大会 Track 全局分析/);
  assert.match(insights, /Track 年度矩阵/);
  assert.match(insights, /placeholder="例如 Fuzzing、Web Security"/);
  assert.match(layout, /catalog-insights\.css/);
});

test("catalog records the current summary evidence split", async () => {
  const catalog = JSON.parse(await read("../public/catalog.json"));
  assert.equal(catalog.stats.semanticSummaries, catalog.stats.papers);
  assert.equal(
    catalog.stats.abstractGroundedSummaries + catalog.stats.titleOnlySummaries,
    catalog.stats.semanticSummaries,
  );
  assert.ok(catalog.stats.abstractGroundedSummaries > catalog.stats.titleOnlySummaries);
});
