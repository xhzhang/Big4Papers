"use client";

import { useMemo, useState } from "react";

import type { Paper } from "./catalog-app";

export type TeamDetailGroup = {
  anchor: string;
  members: string[];
  papers: Paper[];
  topTopic: string;
  topicCounts: Map<string, number>;
};

function fmt(value: number) {
  return new Intl.NumberFormat("zh-CN").format(value);
}

function initials(value: string) {
  return value
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

function searchableText(paper: Paper) {
  return [
    paper.title,
    paper.authors.join(" "),
    paper.track,
    paper.primaryTopic,
    paper.secondaryTopics.join(" "),
    paper.tags.map((tag) => tag.name).join(" "),
  ].join(" ").toLowerCase();
}

export function TeamDetailView({
  group,
  onBack,
  onOpenPaper,
}: {
  group: TeamDetailGroup;
  onBack: () => void;
  onOpenPaper: (paper: Paper) => void;
}) {
  const [query, setQuery] = useState("");
  const normalizedQuery = query.trim().toLowerCase();
  const years = useMemo(
    () => Array.from(new Set(group.papers.map((paper) => paper.year))).sort((a, b) => b - a),
    [group.papers],
  );
  const topicStats = useMemo(
    () => Array.from(group.topicCounts.entries()).sort((a, b) => b[1] - a[1]),
    [group.topicCounts],
  );
  const filteredPapers = useMemo(
    () => group.papers
      .filter((paper) => !normalizedQuery || searchableText(paper).includes(normalizedQuery))
      .sort((a, b) => b.year - a.year || a.title.localeCompare(b.title, "en")),
    [group.papers, normalizedQuery],
  );

  return (
    <section className="inner-view team-detail">
      <button className="team-back-button" type="button" onClick={onBack}>
        <span aria-hidden="true">←</span> 返回团队脉络
      </button>

      <div className="team-detail-intro">
        <div className="team-detail-avatars" aria-hidden="true">
          {group.members.slice(0, 3).map((member) => <span key={member}>{initials(member)}</span>)}
        </div>
        <div>
          <h1>{group.anchor} 合作组</h1>
          <p>依据跨年度共同作者关系推断，用于追踪持续工作；不代表已经核实的机构或实验室归属。</p>
        </div>
      </div>

      <dl className="team-detail-stats">
        <div><dt>收录论文</dt><dd>{fmt(group.papers.length)} 篇</dd></div>
        <div><dt>活跃年度</dt><dd>{years.slice().reverse().join("—")}</dd></div>
        <div><dt>持续合作者</dt><dd>{fmt(group.members.length)} 人</dd></div>
        <div><dt>主要方向</dt><dd>{group.topTopic}</dd></div>
      </dl>

      <div className="team-detail-context">
        <section aria-labelledby="team-members-title">
          <h2 id="team-members-title">持续合作者</h2>
          <div className="team-detail-members">{group.members.map((member) => <span key={member}>{member}</span>)}</div>
        </section>
        <section aria-labelledby="team-topics-title">
          <h2 id="team-topics-title">方向分布</h2>
          <div className="team-detail-topics">
            {topicStats.slice(0, 8).map(([topic, count]) => <span key={topic}><b>{topic}</b>{count} 篇</span>)}
          </div>
        </section>
      </div>

      <div className="team-paper-heading">
        <div>
          <h2>全部论文</h2>
          <p>按年份从新到旧排列；点击论文标题可查看完整摘要、中文概述和来源链接。</p>
        </div>
        <label className="team-paper-search">
          <span>在该团队中搜索</span>
          <div>
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="标题、作者、Track、Topic 或标签"
            />
            {query && <button type="button" onClick={() => setQuery("")}>清空</button>}
          </div>
        </label>
      </div>

      <div className="team-paper-result" aria-live="polite">
        <strong>{fmt(filteredPapers.length)}</strong> / {fmt(group.papers.length)} 篇论文
        {normalizedQuery && <span> · 搜索“{query.trim()}”</span>}
      </div>

      {filteredPapers.length ? (
        <div className="team-paper-timeline">
          {years.map((year) => {
            const yearPapers = filteredPapers.filter((paper) => paper.year === year);
            if (!yearPapers.length) return null;
            return (
              <section className="team-year-section" key={year} aria-labelledby={`team-year-${year}`}>
                <header>
                  <h3 id={`team-year-${year}`}>{year}</h3>
                  <span>{yearPapers.length} 篇</span>
                </header>
                <div className="team-detail-paper-list">
                  {yearPapers.map((paper) => (
                    <article className="team-detail-paper" key={paper.id}>
                      <div className="team-detail-paper-meta">
                        <span>{paper.venue}</span>
                        {paper.track && <span>{paper.track}</span>}
                        <span>{paper.primaryTopic}</span>
                      </div>
                      <button type="button" onClick={() => onOpenPaper(paper)}>{paper.title}</button>
                      <p className="team-detail-paper-authors">{paper.authors.join(" · ")}</p>
                      <p className="team-detail-paper-summary">{paper.summaryZh || "中文概述待生成。"}</p>
                      <div className="team-detail-paper-tags">
                        {paper.tags.slice(0, 5).map((tag) => <span key={tag.name}>{tag.name}</span>)}
                        {paper.summaryStatus === "title-only" && <em>仅标题概述</em>}
                      </div>
                    </article>
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      ) : (
        <div className="empty-state team-paper-empty">
          <span>⌕</span>
          <h3>没有匹配论文</h3>
          <p>可尝试更短的标题、作者或方向关键词。</p>
          <button className="primary-button" type="button" onClick={() => setQuery("")}>清空搜索</button>
        </div>
      )}

      <div className="team-detail-footer">
        <button className="team-back-button" type="button" onClick={onBack}><span aria-hidden="true">←</span> 返回团队脉络</button>
      </div>
    </section>
  );
}
