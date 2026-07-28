import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const catalogSource = await readFile(new URL("../app/catalog-app.tsx", import.meta.url), "utf8");
const excelSource = await readFile(new URL("../app/excel-export.ts", import.meta.url), "utf8");

test("search remains a metadata substring search rather than PDF full text", () => {
  const matchingFunction = catalogSource.match(/function matchingText\(paper: Paper\) \{[\s\S]*?\n\}/)?.[0] ?? "";
  for (const field of ["paper.title", "paper.authors", "paper.abstract", "paper.summaryZh", "paper.track", "paper.session", "paper.primaryTopic", "paper.secondaryTopics", "paper.tags"]) {
    assert.match(matchingFunction, new RegExp(field.replace(".", "\\.")));
  }
  assert.doesNotMatch(matchingFunction, /pdf|full.?text/i);
});

test("reading-list grouping is chosen when a paper is added", () => {
  assert.match(catalogSource, /secatlas-shortlist-groups/);
  assert.doesNotMatch(catalogSource, /secatlas-shortlist-default-group/);
  assert.match(catalogSource, /function ReadingListPicker/);
  assert.match(catalogSource, /function suggestedShortlistGroup/);
  assert.match(catalogSource, /context\.topics\.find/);
  assert.match(catalogSource, /context\.tags\.find/);
  assert.match(catalogSource, /context\.query\.trim\(\)/);
  assert.match(catalogSource, /new Set\(\[group, currentGroup, suggestedGroup, \.\.\.groups\]/);
  assert.match(catalogSource, /setShortlistGroups\(\(current\) => \(\{ \.\.\.current, \[id\]: group \}\)\)/);
  assert.doesNotMatch(catalogSource, /CourseGroupControl/);
});

test("Track, Topic, and tag filters support multiple removable selections", () => {
  assert.match(catalogSource, /const \[tracks, setTracks\] = useState<string\[\]>\(\[\]\)/);
  assert.match(catalogSource, /const \[topics, setTopics\] = useState<string\[\]>\(\[\]\)/);
  assert.match(catalogSource, /const \[tags, setTags\] = useState<string\[\]>\(\[\]\)/);
  assert.match(catalogSource, /tracks\.length && !tracks\.includes\(paper\.track\)/);
  assert.match(catalogSource, /topics\.length && !topics\.includes\(paper\.primaryTopic\)/);
  assert.match(catalogSource, /tags\.length && !paper\.tags\.some/);
  assert.match(catalogSource, /toggleSelection\(props\.tracks/);
  assert.match(catalogSource, /toggleSelection\(props\.topics/);
  assert.match(catalogSource, /toggleSelection\(props\.tags/);
  assert.match(catalogSource, /className="chip-remove"/);
  assert.match(catalogSource, /移除筛选：/);
});

test("papers already in the reading list can be regrouped or removed", () => {
  assert.match(catalogSource, /paperGroups\[paper\.id\] \|\| DEFAULT_SHORTLIST_GROUP/);
  assert.match(catalogSource, /setPaperGroup\(paper\.id, event\.target\.value\)/);
  assert.match(catalogSource, /removeFromShortlist\(paper\.id\)/);
  assert.match(catalogSource, /Topic 与 Track 保留为论文属性，不再决定列表归类/);
});

test("reading-list export keeps the custom grouping", () => {
  assert.match(excelSource, /function courseGroupRows/);
  assert.match(excelSource, /name: "研读分组"/);
  assert.match(excelSource, /courseGroups\[paper\.id\] \|\| "未分组"/);
  assert.match(catalogSource, /downloadPaperWorkbook\(shortlistPapers, "研读列表", shortlistGroups\)/);
});
