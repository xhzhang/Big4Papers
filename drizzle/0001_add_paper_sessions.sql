ALTER TABLE `papers` ADD `session` text;
--> statement-breakpoint
CREATE INDEX `papers_session_idx` ON `papers` (`venue`, `year`, `session`);
