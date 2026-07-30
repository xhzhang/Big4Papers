"use client";

import type { CSSProperties, FormEvent } from "react";
import { useMemo, useRef, useState } from "react";

import type { Catalog } from "./catalog-app";

function fmt(value: number) {
  return new Intl.NumberFormat("zh-CN").format(value);
}

function pageItems(current: number, total: number): Array<number | string> {
  if (total <= 9) return Array.from({ length: total }, (_, index) => index + 1);
  const candidates = new Set([1, total, current - 2, current - 1, current, current + 1, current + 2]);
  const pages = Array.from(candidates).filter((value) => value >= 1 && value <= total).sort((a, b) => a - b);
  const items: Array<number | string> = [];
  pages.forEach((value, index) => {
    const previous = pages[index - 1];
    if (index > 0 && value - previous > 1) {
      if (value - previous === 2) items.push(previous + 1);
      else items.push(`ellipsis-${previous}-${value}`);
    }
    items.push(value);
  });
  return items;
}

export function CatalogPagination({ page, pageCount, onPageChange }: { page: number; pageCount: number; onPageChange: (page: number) => void }) {
  const draftRef = useRef<HTMLInputElement>(null);

  function goToPage(value: number) {
    const next = Math.min(pageCount, Math.max(1, Math.round(value)));
    onPageChange(next);
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const parsed = Number(draftRef.current?.value);
    if (Number.isFinite(parsed)) goToPage(parsed);
  }

  return (
    <nav className="pagination" aria-label="论文列表分页">
      <div className="pagination-main">
        <button className="pagination-edge" disabled={page === 1} onClick={() => goToPage(1)}>首页</button>
        <button disabled={page === 1} onClick={() => goToPage(page - 1)}>上一页</button>
        <div className="pagination-pages">
          {pageItems(page, pageCount).map((item) => typeof item === "number" ? (
            <button
              key={item}
              className={item === page ? "current" : ""}
              aria-current={item === page ? "page" : undefined}
              aria-label={`第 ${item} 页`}
              onClick={() => goToPage(item)}
            >
              {item}
            </button>
          ) : <span key={item} aria-hidden="true">…</span>)}
        </div>
        <button disabled={page === pageCount} onClick={() => goToPage(page + 1)}>下一页</button>
        <button className="pagination-edge" disabled={page === pageCount} onClick={() => goToPage(pageCount)}>末页</button>
      </div>
      <form className="pagination-jump" onSubmit={submit}>
        <label htmlFor="page-jump">跳至</label>
        <input key={page} ref={draftRef} id="page-jump" type="number" inputMode="numeric" min={1} max={pageCount} defaultValue={page} />
        <button type="submit">前往</button>
        <span>共 {pageCount} 页</span>
      </form>
    </nav>
  );
}

export function SummaryEvidenceStrip({ total, semantic, grounded, titleOnly }: { total: number; semantic: number; grounded: number; titleOnly: number }) {
  const pending = Math.max(0, total - semantic);
  const groundedPercent = total ? (grounded / total) * 100 : 0;
  const titleOnlyPercent = total ? (titleOnly / total) * 100 : 0;
  return (
    <section className="summary-evidence" aria-labelledby="summary-evidence-title">
      <div>
        <h2 id="summary-evidence-title">中文概述证据覆盖</h2>
        <p>所有论文均有中文概述，但证据强度不同；“仅标题概述”不包含摘要中才能确认的方法和实验结论。</p>
      </div>
      <div className="summary-evidence-numbers">
        <span><strong>{fmt(grounded)}</strong> 摘要驱动</span>
        <span><strong>{fmt(titleOnly)}</strong> 仅标题</span>
        {pending > 0 && <span><strong>{fmt(pending)}</strong> 待生成</span>}
      </div>
      <div className="summary-evidence-bar" aria-label={`摘要驱动 ${grounded} 篇，仅标题 ${titleOnly} 篇`}>
        <i className="grounded" style={{ width: `${groundedPercent}%` }} />
        <i className="title-only" style={{ width: `${titleOnlyPercent}%` }} />
      </div>
      <div className="summary-evidence-legend">
        <span><i className="grounded" />摘要驱动 · 可概括方法与摘要明确给出的结果</span>
        <span><i className="title-only" />仅标题 · 仅说明标题可确认的研究对象或问题</span>
      </div>
    </section>
  );
}

type TrackStat = {
  track: string;
  total: number;
  counts: Record<number, number>;
  baseline: number;
  comparable: number;
  change: number;
  shares: Record<number, number>;
  shareChange: number;
};

export function TrackInsights({ catalog, onSelectTrack }: { catalog: Catalog; onSelectTrack: (track: string) => void }) {
  const years = useMemo(() => [...catalog.coverage.years].sort((a, b) => a - b), [catalog.coverage.years]);
  const baselineYear = years[0];
  const latestYear = years[years.length - 1];
  const comparisonYear = years.length > 1 ? years[years.length - 2] : latestYear;
  const [trackQuery, setTrackQuery] = useState("");
  const [sortBy, setSortBy] = useState<"total" | "latest" | "growth">("total");
  const [showAll, setShowAll] = useState(false);
  const researchPapers = useMemo(() => catalog.papers.filter((paper) => paper.track && paper.trackType === "research"), [catalog.papers]);

  const trackStats = useMemo(() => {
    const counts = new Map<string, Record<number, number>>();
    const yearResearchTotals = Object.fromEntries(years.map((year) => [year, researchPapers.filter((paper) => paper.year === year).length]));
    researchPapers.forEach((paper) => {
      const byYear = counts.get(paper.track) ?? Object.fromEntries(years.map((year) => [year, 0]));
      byYear[paper.year] = (byYear[paper.year] ?? 0) + 1;
      counts.set(paper.track, byYear);
    });
    return Array.from(counts.entries()).map(([track, byYear]): TrackStat => {
      const total = years.reduce((sum, year) => sum + (byYear[year] ?? 0), 0);
      const baseline = byYear[baselineYear] ?? 0;
      const comparable = byYear[comparisonYear] ?? 0;
      const shares = Object.fromEntries(years.map((year) => [year, yearResearchTotals[year] ? (byYear[year] ?? 0) / yearResearchTotals[year] : 0]));
      return { track, total, counts: byYear, baseline, comparable, change: comparable - baseline, shares, shareChange: (shares[comparisonYear] ?? 0) - (shares[baselineYear] ?? 0) };
    });
  }, [baselineYear, comparisonYear, researchPapers, years]);

  const yearTotals = years.map((year) => ({
    year,
    papers: researchPapers.filter((paper) => paper.year === year).length,
    activeTracks: trackStats.filter((track) => (track.counts[year] ?? 0) > 0).length,
  }));
  const maxYearTotal = Math.max(...yearTotals.map((item) => item.papers), 1);
  const rankedByTotal = [...trackStats].sort((a, b) => b.total - a.total || a.track.localeCompare(b.track, "en"));
  const maxTrackTotal = rankedByTotal[0]?.total ?? 1;
  const largestTrack = rankedByTotal[0];
  const strongestGrowth = [...trackStats].filter((track) => track.baseline >= 5).sort((a, b) => b.shareChange - a.shareChange || b.change - a.change)[0];
  const normalizedQuery = trackQuery.trim().toLowerCase();
  const sortedTracks = trackStats
    .filter((track) => !normalizedQuery || track.track.toLowerCase().includes(normalizedQuery))
    .sort((a, b) => {
      if (sortBy === "latest") return b.comparable - a.comparable || b.total - a.total;
      if (sortBy === "growth") return b.shareChange - a.shareChange || b.change - a.change;
      return b.total - a.total || a.track.localeCompare(b.track, "en");
    });
  const visibleTracks = showAll ? sortedTracks : sortedTracks.slice(0, 12);

  return (
    <section className="track-insights" aria-labelledby="track-insights-title">
      <div className="analysis-heading">
        <div>
          <h2 id="track-insights-title">四大会 Track 全局分析</h2>
          <p>只统计由官网 Session 归一化得到的研究型 Track；Poster、Demo、Workshop 与未归类项不进入方向趋势。点击 Track 可回到论文库查看对应论文。</p>
        </div>
        <span>{fmt(catalog.stats.researchTrackPapers ?? researchPapers.length)} 篇研究 Track · {fmt(catalog.stats.excludedTrackPapers ?? 0)} 篇已排除非研究分组</span>
      </div>

      <div className="track-analysis-grid">
        <article className="track-distribution">
          <header><div><h3>论文规模最大的方向</h3><p>按 2023—{latestYear} 当前收录总量排序</p></div><strong>Top 8</strong></header>
          <div className="ranked-track-bars">
            {rankedByTotal.slice(0, 8).map((track, index) => (
              <button key={track.track} onClick={() => onSelectTrack(track.track)}>
                <span className="rank">{String(index + 1).padStart(2, "0")}</span>
                <span className="ranked-track-name">{track.track}</span>
                <span className="ranked-track-bar"><i style={{ width: `${(track.total / maxTrackTotal) * 100}%` }} /></span>
                <strong>{fmt(track.total)}</strong>
              </button>
            ))}
          </div>
        </article>

        <article className="year-structure">
          <header><div><h3>年度收录与方向覆盖</h3><p>{latestYear} 尚未完整收齐，不参与增长判断</p></div><strong>{baselineYear}—{latestYear}</strong></header>
          <div className="year-volume-chart">
            {yearTotals.map((item) => (
              <div key={item.year}>
                <span><i style={{ height: `${Math.max(9, (item.papers / maxYearTotal) * 100)}%` }} /></span>
                <strong>{fmt(item.papers)}</strong>
                <b>{item.year}</b>
                <small>{item.activeTracks} 个方向</small>
              </div>
            ))}
          </div>
          <dl className="analysis-notes">
            <div><dt>最大 Track</dt><dd>{largestTrack?.track ?? "—"} · {fmt(largestTrack?.total ?? 0)} 篇</dd></div>
            <div><dt>{baselineYear}→{comparisonYear} 占比增长</dt><dd>{strongestGrowth?.track ?? "—"} · {strongestGrowth ? `${strongestGrowth.shareChange >= 0 ? "+" : ""}${(strongestGrowth.shareChange * 100).toFixed(1)} pp` : "—"}</dd></div>
            <div><dt>{latestYear} 口径</dt><dd>当前收录快照，待四会完整后再做同比</dd></div>
          </dl>
        </article>
      </div>

      <div className="track-matrix-section">
        <div className="matrix-heading">
          <div><h3>Track 年度矩阵</h3><p>单元格显示论文数；悬停可查看当年研究 Track 占比。变化列使用可比较的 {baselineYear}→{comparisonYear} 占比变化。</p></div>
          <div className="matrix-controls">
            <label><span>搜索 Track</span><input value={trackQuery} onChange={(event) => { setTrackQuery(event.target.value); setShowAll(false); }} placeholder="例如 Fuzzing、Web Security" /></label>
            <label><span>排序</span><select value={sortBy} onChange={(event) => setSortBy(event.target.value as typeof sortBy)}><option value="total">论文总量</option><option value="latest">{comparisonYear} 热度</option><option value="growth">{baselineYear}→{comparisonYear} 增长</option></select></label>
          </div>
        </div>

        <div className="track-matrix" role="table" aria-label="Track 年度论文数量" style={{ "--year-columns": years.length } as CSSProperties}>
          <div className="track-matrix-head" role="row">
            <span role="columnheader">Track</span>
            {years.map((year) => <span role="columnheader" key={year}>{year}{year === latestYear ? "*" : ""}</span>)}
            <span role="columnheader">总计</span>
            <span role="columnheader">占比变化</span>
          </div>
          {visibleTracks.map((track) => {
            const rowMax = Math.max(...years.map((year) => track.counts[year] ?? 0), 1);
            return (
              <div className="track-matrix-row" role="row" key={track.track}>
                <button role="cell" onClick={() => onSelectTrack(track.track)}>{track.track}</button>
                {years.map((year) => {
                  const count = track.counts[year] ?? 0;
                  const heat = count ? 0.09 + (count / rowMax) * 0.34 : 0;
                  return <span role="cell" className="matrix-cell" title={count ? `${year} 年占当年研究 Track 论文的 ${((track.shares[year] ?? 0) * 100).toFixed(1)}%` : `${year} 年无论文`} style={{ "--heat": heat } as CSSProperties} key={year}>{count || "—"}</span>;
                })}
                <strong role="cell">{fmt(track.total)}</strong>
                <em role="cell" className={track.shareChange > 0 ? "up" : track.shareChange < 0 ? "down" : ""}>{track.shareChange > 0 ? "+" : ""}{(track.shareChange * 100).toFixed(1)} pp</em>
              </div>
            );
          })}
        </div>
        {visibleTracks.length === 0 && <div className="matrix-empty">没有匹配的 Track，请尝试更短的关键词。</div>}
        {sortedTracks.length > 12 && <button className="matrix-more" onClick={() => setShowAll(!showAll)}>{showAll ? "收起矩阵" : `查看全部 ${sortedTracks.length} 个 Track`}</button>}
        <p className="matrix-footnote">* {latestYear} 为当前公开数据快照，部分会议尚未形成完整论文列表。</p>
      </div>
    </section>
  );
}
