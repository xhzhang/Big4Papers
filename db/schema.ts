import { integer, primaryKey, sqliteTable, text } from "drizzle-orm/sqlite-core";

export const papers = sqliteTable("papers", {
  id: text("id").primaryKey(),
  dblpKey: text("dblp_key").unique(),
  title: text("title").notNull(),
  venue: text("venue").notNull(),
  year: integer("year").notNull(),
  session: text("session"),
  track: text("track"),
  doi: text("doi"),
  sourceUrl: text("source_url"),
  pdfUrl: text("pdf_url"),
  abstract: text("abstract"),
  summaryZh: text("summary_zh"),
  primaryTopic: text("primary_topic").notNull().default("其他安全方向"),
  analysisStatus: text("analysis_status").notNull().default("pending"),
  updatedAt: text("updated_at").notNull(),
});

export const authors = sqliteTable("authors", {
  id: text("id").primaryKey(),
  name: text("name").notNull(),
  orcid: text("orcid"),
});

export const paperAuthors = sqliteTable(
  "paper_authors",
  {
    paperId: text("paper_id").notNull(),
    authorId: text("author_id").notNull(),
    authorOrder: integer("author_order").notNull(),
  },
  (table) => [primaryKey({ columns: [table.paperId, table.authorId] })],
);

export const paperTags = sqliteTable(
  "paper_tags",
  {
    paperId: text("paper_id").notNull(),
    tag: text("tag").notNull(),
    tagType: text("tag_type").notNull(),
  },
  (table) => [primaryKey({ columns: [table.paperId, table.tag] })],
);

export const sources = sqliteTable("sources", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  paperId: text("paper_id").notNull(),
  provider: text("provider").notNull(),
  fieldName: text("field_name").notNull(),
  sourceUrl: text("source_url"),
  retrievedAt: text("retrieved_at").notNull(),
});

export const analysisRuns = sqliteTable("analysis_runs", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  paperId: text("paper_id").notNull(),
  provider: text("provider").notNull(),
  model: text("model"),
  promptVersion: text("prompt_version").notNull(),
  status: text("status").notNull(),
  createdAt: text("created_at").notNull(),
});
