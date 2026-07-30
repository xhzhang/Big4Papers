import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(path, import.meta.url), "utf8");

test("paper comparison renders the complete English abstract", async () => {
  const source = await read("../app/catalog-app.tsx");
  assert.match(source, /label="摘要证据"[\s\S]*?paper\.abstract \|\| "摘要待补"/);
  assert.doesNotMatch(source, /paper\.abstract\.slice\(0,\s*360\)/);
});

test("team cards open a complete paper timeline with a return path", async () => {
  const [catalogApp, teamDetail, layout] = await Promise.all([
    read("../app/catalog-app.tsx"),
    read("../app/team-detail.tsx"),
    read("../app/layout.tsx"),
  ]);

  assert.match(catalogApp, /查看全部 \{group\.papers\.length\} 篇论文/);
  assert.match(catalogApp, /<TeamDetailView/);
  assert.match(teamDetail, /返回团队脉络/);
  assert.match(teamDetail, /在该团队中搜索/);
  assert.doesNotMatch(teamDetail.match(/function searchableText[\s\S]*?\n\}/)?.[0] ?? "", /paper\.(abstract|summaryZh)/);
  assert.match(teamDetail, /group\.papers[\s\S]*?sort\(\(a, b\) => b\.year - a\.year/);
  assert.match(teamDetail, /onOpenPaper\(paper\)/);
  assert.match(layout, /team-detail\.css/);
});
