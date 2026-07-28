CREATE TABLE `analysis_runs` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`paper_id` text NOT NULL,
	`provider` text NOT NULL,
	`model` text,
	`prompt_version` text NOT NULL,
	`status` text NOT NULL,
	`created_at` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `authors` (
	`id` text PRIMARY KEY NOT NULL,
	`name` text NOT NULL,
	`orcid` text
);
--> statement-breakpoint
CREATE TABLE `paper_authors` (
	`paper_id` text NOT NULL,
	`author_id` text NOT NULL,
	`author_order` integer NOT NULL,
	PRIMARY KEY(`paper_id`, `author_id`)
);
--> statement-breakpoint
CREATE TABLE `paper_tags` (
	`paper_id` text NOT NULL,
	`tag` text NOT NULL,
	`tag_type` text NOT NULL,
	PRIMARY KEY(`paper_id`, `tag`)
);
--> statement-breakpoint
CREATE TABLE `papers` (
	`id` text PRIMARY KEY NOT NULL,
	`dblp_key` text,
	`title` text NOT NULL,
	`venue` text NOT NULL,
	`year` integer NOT NULL,
	`doi` text,
	`source_url` text,
	`pdf_url` text,
	`abstract` text,
	`summary_zh` text,
	`primary_topic` text DEFAULT '其他安全方向' NOT NULL,
	`analysis_status` text DEFAULT 'pending' NOT NULL,
	`updated_at` text NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `papers_dblp_key_unique` ON `papers` (`dblp_key`);--> statement-breakpoint
CREATE TABLE `sources` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`paper_id` text NOT NULL,
	`provider` text NOT NULL,
	`field_name` text NOT NULL,
	`source_url` text,
	`retrieved_at` text NOT NULL
);
