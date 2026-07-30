import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const catalogSource = await readFile(new URL("../app/catalog-app.tsx", import.meta.url), "utf8");
const excelSource = await readFile(new URL("../app/excel-export.ts", import.meta.url), "utf8");

test("search explains weighted metadata and abstract matches without PDF full text", () => {
  assert.match(catalogSource, /const SEARCH_FIELDS/);
  for (const field of ["title", "authors", "abstract", "summary", "track", "session", "topics", "tags"]) {
    assert.match(catalogSource, new RegExp(`field: "${field}"`));
  }
  assert.match(catalogSource, /function explainSearchMatch/);
  assert.match(catalogSource, /命中字段/);
  assert.match(catalogSource, /包含完整短语/);
  assert.match(catalogSource, /按相关度排序/);
  const searchModel = catalogSource.slice(catalogSource.indexOf("const SEARCH_FIELDS"), catalogSource.indexOf("type PaperDetailShard"));
  assert.doesNotMatch(searchModel, /pdf|full.?text/i);
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
  assert.match(catalogSource, /const \[tracks, setTracks\] = useState<string\[\]>\(initialUrlState\.tracks\)/);
  assert.match(catalogSource, /const \[topics, setTopics\] = useState<string\[\]>\(initialUrlState\.topics\)/);
  assert.match(catalogSource, /const \[tags, setTags\] = useState<string\[\]>\(initialUrlState\.tags\)/);
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
  assert.match(catalogSource, /downloadPaperWorkbook\(await papersWithDetails\(shortlistPapers\), "研读列表", shortlistGroups\)/);
});
