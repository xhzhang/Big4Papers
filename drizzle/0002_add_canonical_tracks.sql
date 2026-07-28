ALTER TABLE `papers` ADD `track` text;
--> statement-breakpoint
CREATE INDEX `papers_track_idx` ON `papers` (`track`);
