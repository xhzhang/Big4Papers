"use client";

import { useEffect, useMemo, useState } from "react";

import { downloadPaperWorkbook } from "./excel-export";

type Tag = { name: string; type: string };
type Paper = {
  id: string;
  title: string;
  venue: string;
  venueName: string;
  venueUrl: string;
  year: number;
  session: string;
  track: string;
  authors: string[];
  doi?: string | null;
  sourceUrl?: string | null;
  pdfUrl?: string | null;
  abstract: string;
  summaryZh: string;
  summaryStatus: "pending" | "template" | "abstract-grounded" | "title-only" | "human";
  summaryProvider: string;
  summaryModel: string;
  primaryTopic: string;
  secondaryTopics: string[];
  tags: Tag[];
  analysisStatus: string;
  confidence: number;
};
type CoverageStatus = {
  venue: string;
  year: number;
  state: "complete" | "partial" | "awaiting";
  label: string;
  publishedCount: number | null;
  collectedCount: number;
  sourceUrl: string;
  note: string;
};
type Catalog = {
  generatedAt: string;
  taxonomyVersion: string;
  coverage: { years: number[]; venues: string[] };
  coverageStatus: CoverageStatus[];
  priorityTopics: string[];
  stats: { papers: number; abstracts: number; pdfs: number; analyzed: number; semanticSummaries: number; abstractGroundedSummaries: number; titleOnlySummaries: number; sessionPapers: number; sessions: number; trackPapers: number; tracks: number };
  papers: Paper[];
};
type DataUpdateStatus = {
  state: "idle" | "running" | "success" | "error";
  stage: string;
  message: string;
  years: number[];
  startedAt: string | null;
  finishedAt: string | null;
  stats: Catalog["stats"] | null;
};
type View = "library" | "topics" | "teams" | "compare" | "seminar" | "data";

const VIEW_LABELS: Record<View, string> = {
  library: "论文库",
  topics: "方向图谱",
  teams: "团队脉络",
  compare: "论文对比",
  seminar: "研读列表",
  data: "数据中心",
};

const TOPIC_META: Record<string, { code: string; note: string; color: string }> = {
  "智能手机安全": { code: "MOB", note: "系统、App、权限、基带与移动生态", color: "mint" },
  "AIOS 安全": { code: "AOS", note: "AI/Agent 运行时、调度与隔离", color: "sky" },
  "认证安全": { code: "AUT", note: "协议与实现漏洞、状态机和逻辑缺陷", color: "amber" },
  "智能体安全": { code: "AGT", note: "工具、记忆、规划与多智能体系统", color: "violet" },
  "AI 硬件安全": { code: "AIH", note: "GPU/NPU、驱动、显存与共享资源", color: "rose" },
  "大模型安全": { code: "LLM", note: "模型、训练链路、推理与应用安全", color: "blue" },
};

const TAG_LABEL: Record<string, string> = {
  object: "对象",
  protocol: "协议",
  technique: "技术",
  threat: "威胁",
  goal: "目标",
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

function venueClass(venue: string) {
  if (venue.includes("S&P")) return "sp";
  if (venue.includes("CCS")) return "ccs";
  if (venue.includes("USENIX")) return "usenix";
  return "ndss";
}

function summaryEvidenceLabel(paper: Paper) {
  if (paper.summaryStatus === "human") return "人工审核";
  if (paper.summaryStatus === "abstract-grounded") return paper.summaryProvider.includes("chatgpt") ? "摘要驱动 · ChatGPT" : "摘要驱动 · LLM";
  if (paper.summaryStatus === "title-only") return "仅依据标题 · 证据有限";
  return "待重新生成";
}


function matchingText(paper: Paper) {
  return [paper.title, paper.authors.join(" "), paper.abstract, paper.summaryZh, paper.track, paper.session, paper.primaryTopic, paper.secondaryTopics.join(" "), paper.tags.map((tag) => tag.name).join(" ")]
    .join(" ")
    .toLowerCase();
}

const DEFAULT_SHORTLIST_GROUP = "未分组";

function normalizeShortlistGroup(value: string) {
  return value.trim().replace(/\s+/g, " ").slice(0, 40) || DEFAULT_SHORTLIST_GROUP;
}

export function CatalogApp() {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [loadError, setLoadError] = useState("");
  const [view, setView] = useState<View>("library");
  const [query, setQuery] = useState("");
  const [venue, setVenue] = useState("全部会议");
  const [year, setYear] = useState("全部年份");
  const [tracks, setTracks] = useState<string[]>([]);
  const [topics, setTopics] = useState<string[]>([]);
  const [tags, setTags] = useState<string[]>([]);
  const [focusTopics, setFocusTopics] = useState<string[] | null>(null);
  const [selectedPaper, setSelectedPaper] = useState<Paper | null>(null);
  const [page, setPage] = useState(1);
  const [shortlist, setShortlist] = useState<string[]>(() => {
    if (typeof window === "undefined") return [];
    try {
      const saved = localStorage.getItem("secatlas-shortlist");
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });
  const [shortlistGroups, setShortlistGroups] = useState<Record<string, string>>(() => {
    if (typeof window === "undefined") return {};
    try {
      const saved = localStorage.getItem("secatlas-shortlist-groups");
      const parsed = saved ? JSON.parse(saved) : {};
      return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
    } catch {
      return {};
    }
  });

  const [mobileNav, setMobileNav] = useState(false);
  const [compareIds, setCompareIds] = useState<string[]>([]);
  const [updateStatus, setUpdateStatus] = useState<DataUpdateStatus | null>(null);
  const [updateApiAvailable, setUpdateApiAvailable] = useState<boolean | null>(null);
  const [updateNoticeHidden, setUpdateNoticeHidden] = useState(false);

  useEffect(() => {
    fetch("/catalog.json")
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
      })
      .then((data: Catalog) => {
        setCatalog(data);
        const availableTopics = new Set(data.papers.map((paper) => paper.primaryTopic));
        let preferred = data.priorityTopics.filter((item) => availableTopics.has(item));
        try {
          const saved = localStorage.getItem("secatlas-focus-topics");
          const parsed = saved ? JSON.parse(saved) : null;
          if (Array.isArray(parsed)) preferred = parsed.filter((item): item is string => typeof item === "string" && availableTopics.has(item));
        } catch {
          // Use catalog defaults when browser storage is unavailable or invalid.
        }
        setFocusTopics(preferred);
      })
      .catch((error: Error) => setLoadError(error.message));

  }, []);

  useEffect(() => {
    fetch("/api/update", { cache: "no-store" })
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
      })
      .then((status: DataUpdateStatus) => {
        setUpdateStatus(status);
        setUpdateApiAvailable(true);
      })
      .catch(() => setUpdateApiAvailable(false));
  }, []);

  useEffect(() => {
    if (updateStatus?.state !== "running") return;
    let active = true;
    const poll = async () => {
      try {
        const response = await fetch("/api/update", { cache: "no-store" });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const status: DataUpdateStatus = await response.json();
        if (!active) return;
        if (status.state === "success") {
          const catalogResponse = await fetch(`/catalog.json?updated=${Date.now()}`, { cache: "no-store" });
          if (!catalogResponse.ok) throw new Error(`HTTP ${catalogResponse.status}`);
          const data: Catalog = await catalogResponse.json();
          if (!active) return;
          setCatalog(data);
        }
        setUpdateStatus(status);
      } catch (error) {
        if (!active) return;
        setUpdateStatus((current) => ({
          state: "error",
          stage: "connection",
          message: `无法读取更新状态：${error instanceof Error ? error.message : "请稍后重试"}`,
          years: current?.years ?? [],
          startedAt: current?.startedAt ?? null,
          finishedAt: new Date().toISOString(),
          stats: current?.stats ?? null,
        }));
      }
    };
    const timer = window.setInterval(poll, 1500);
    void poll();
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [updateStatus?.state]);

  useEffect(() => {
    try {
      localStorage.setItem("secatlas-shortlist", JSON.stringify(shortlist));
    } catch {
      // Non-authoritative local convenience only.
    }
  }, [shortlist]);

  useEffect(() => {
    try {
      localStorage.setItem("secatlas-shortlist-groups", JSON.stringify(shortlistGroups));
    } catch {
      // Reading-list grouping is a local convenience and does not affect catalog data.
    }
  }, [shortlistGroups]);

  useEffect(() => {
    if (focusTopics === null) return;
    try {
      localStorage.setItem("secatlas-focus-topics", JSON.stringify(focusTopics));
    } catch {
      // Personal preferences remain optional local state.
    }
  }, [focusTopics]);

  const papers = useMemo(() => catalog?.papers ?? [], [catalog]);
  const allTopics = useMemo(() => Array.from(new Set(papers.map((paper) => paper.primaryTopic))).sort(), [papers]);
  const allTags = useMemo(() => {
    const counts = new Map<string, number>();
    papers.forEach((paper) => paper.tags.forEach((item) => counts.set(item.name, (counts.get(item.name) ?? 0) + 1)));
    return Array.from(counts.entries()).sort((a, b) => b[1] - a[1]).slice(0, 80);
  }, [papers]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return papers.filter((paper) => {
      if (venue !== "全部会议" && paper.venue !== venue) return false;
      if (year !== "全部年份" && paper.year !== Number(year)) return false;
      if (tracks.length && !tracks.includes(paper.track)) return false;
      if (topics.length && !topics.includes(paper.primaryTopic)) return false;
      if (tags.length && !paper.tags.some((item) => tags.includes(item.name))) return false;
      return !needle || matchingText(paper).includes(needle);
    });
  }, [papers, query, venue, year, tracks, topics, tags]);

  const topicCounts = useMemo(() => {
    const counts = new Map<string, number>();
    papers.forEach((paper) => counts.set(paper.primaryTopic, (counts.get(paper.primaryTopic) ?? 0) + 1));
    return counts;
  }, [papers]);

  const shortlistPapers = useMemo(() => papers.filter((paper) => shortlist.includes(paper.id)), [papers, shortlist]);
  const shortlistGroupNames = useMemo(() => {
    const used = shortlist.map((id) => shortlistGroups[id] || DEFAULT_SHORTLIST_GROUP);
    const names = Array.from(new Set([DEFAULT_SHORTLIST_GROUP, ...used]));
    return names.sort((a, b) => {
      if (a === DEFAULT_SHORTLIST_GROUP) return -1;
      if (b === DEFAULT_SHORTLIST_GROUP) return 1;
      return a.localeCompare(b, "zh-CN");
    });
  }, [shortlist, shortlistGroups]);
  const comparePapers = useMemo(() => compareIds.map((id) => papers.find((paper) => paper.id === id)).filter((paper): paper is Paper => Boolean(paper)), [papers, compareIds]);

  function saveToShortlist(id: string, value: string) {
    const group = normalizeShortlistGroup(value);
    setShortlist((current) => (current.includes(id) ? current : [...current, id]));
    setShortlistGroups((current) => ({ ...current, [id]: group }));
  }

  function removeFromShortlist(id: string) {
    setShortlist((current) => current.filter((item) => item !== id));
    setShortlistGroups((current) => {
      const next = { ...current };
      delete next[id];
      return next;
    });
  }

  function setPaperShortlistGroup(id: string, value: string) {
    setShortlistGroups((current) => ({ ...current, [id]: normalizeShortlistGroup(value) }));
  }

  function toggleCompare(id: string) {
    setCompareIds((current) => {
      if (current.includes(id)) return current.filter((item) => item !== id);
      return current.length >= 3 ? [...current.slice(1), id] : [...current, id];
    });
  }

  function jumpToTopic(value: string) {
    setTopics([value]);
    setPage(1);
    setView("library");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function exportPapers(items: Paper[], scopeLabel: string) {
    downloadPaperWorkbook(items, scopeLabel);
  }

  function exportShortlist() {
    downloadPaperWorkbook(shortlistPapers, "研读列表", shortlistGroups);
  }

  async function startDataUpdate() {
    setUpdateNoticeHidden(false);
    try {
      const response = await fetch("/api/update", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scope: "smart" }),
      });
      const status = await response.json();
      if (!response.ok && response.status !== 409) {
        throw new Error(status.error || `HTTP ${response.status}`);
      }
      setUpdateStatus(status);
      setUpdateApiAvailable(true);
    } catch (error) {
      setUpdateStatus({
        state: "error",
        stage: "connection",
        message: `无法启动更新：${error instanceof Error ? error.message : "请确认本地服务正在运行"}`,
        years: updateStatus?.years ?? [],
        startedAt: null,
        finishedAt: new Date().toISOString(),
        stats: catalog?.stats ?? null,
      });
    }
  }

  if (!catalog && !loadError) {
    return (
      <main className="loading-screen" role="status">
        <div className="brand-mark">S</div>
        <p>正在装载论文图谱</p>
        <span>四大会 · 2023—2026</span>
      </main>
    );
  }

  if (loadError || !catalog) {
    return (
      <main className="loading-screen error-screen">
        <div className="brand-mark">!</div>
        <h1>论文数据尚未生成</h1>
        <p>请先运行本地数据导出，再刷新页面。</p>
        <code>python -m pipeline export --format web --output public/catalog.json</code>
      </main>
    );
  }

  const coverageText = `${Math.min(...catalog.coverage.years)}—${Math.max(...catalog.coverage.years)}`;
  const activeFocusTopics = focusTopics ?? catalog.priorityTopics;

  return (
    <div className="app-shell">
      <aside className={`side-nav ${mobileNav ? "open" : ""}`}>
        <div className="brand">
          <div className="brand-mark">S</div>
          <div><strong>SecAtlas</strong><span>四大会论文图谱</span></div>
        </div>
        <nav aria-label="主要功能">
          {(Object.keys(VIEW_LABELS) as View[]).map((item) => (
            <button
              key={item}
              className={view === item ? "active" : ""}
              onClick={() => { setView(item); setMobileNav(false); }}
            >
              <span className="nav-dot" />
              {VIEW_LABELS[item]}
              {item === "seminar" && shortlist.length > 0 && <em>{shortlist.length}</em>}{item === "compare" && compareIds.length > 0 && <em>{compareIds.length}</em>}
            </button>
          ))}
        </nav>
        <div className="coverage-card">
          <span className="status-dot" />
          <div><strong>本地论文库</strong><small>{coverageText} · {fmt(catalog.stats.papers)} 篇</small></div>
        </div>
        <p className="side-foot">Taxonomy {catalog.taxonomyVersion}</p>
      </aside>

      <div className="main-column">
        <header className="topbar">
          <button className="menu-button" aria-label="打开导航" onClick={() => setMobileNav(!mobileNav)}>☰</button>
          <div className="global-search">
            <span aria-hidden="true">⌕</span>
            <input
              aria-label="搜索论文、作者、Track、摘要和标签"
              title="匹配标题、作者、英文摘要、中文概述、Track、Session、Topic 和标签；不检索 PDF 全文"
              placeholder="搜索标题、作者、摘要、Track、Session、Topic 或标签…"
              value={query}
              onChange={(event) => { setQuery(event.target.value); setPage(1); }}
              onFocus={() => setView("library")}
            />
            <kbd>/</kbd>
          </div>
          <div className="top-actions">
            <button
              className={`update-button ${updateStatus?.state === "running" ? "running" : ""}`}
              onClick={startDataUpdate}
              disabled={updateApiAvailable !== true || updateStatus?.state === "running"}
              title={updateApiAvailable === false ? "请使用本地服务启动网站后更新" : "自动回补上一年并收集当年最新论文"}
            >
              <span aria-hidden="true">↻</span>
              {updateStatus?.state === "running" ? "正在更新" : "更新数据"}
            </button>
            <button className="shortlist-button" onClick={() => setView("seminar")}>研读列表 <b>{shortlist.length}</b></button>
          </div>
        </header>

        {updateStatus && updateStatus.state !== "idle" && !updateNoticeHidden && (
          <div className={`update-status ${updateStatus.state}`} role={updateStatus.state === "error" ? "alert" : "status"} aria-live="polite">
            <span className="update-indicator" aria-hidden="true" />
            <div>
              <strong>
                {updateStatus.state === "running" ? "正在更新数据" : updateStatus.state === "success" ? "更新完成" : "更新未完成"}
                {updateStatus.years.length > 0 && ` · ${Math.min(...updateStatus.years)}—${Math.max(...updateStatus.years)}`}
              </strong>
              <span>{updateStatus.message}</span>
            </div>
            {updateStatus.state !== "running" && (
              <button className="update-dismiss" onClick={() => setUpdateNoticeHidden(true)}>关闭</button>
            )}
          </div>
        )}

        <main className="content">
          {view === "library" && (
            <LibraryView
              catalog={catalog}
              filtered={filtered}
              query={query}
              page={page}
              setPage={setPage}
              venue={venue}
              setVenue={(value) => { setVenue(value); setPage(1); }}
              year={year}
              setYear={(value) => { setYear(value); setPage(1); }}
              tracks={tracks}
              setTracks={(values) => { setTracks(values); setPage(1); }}
              topics={topics}
              setTopics={(values) => { setTopics(values); setPage(1); }}
              tags={tags}
              setTags={(values) => { setTags(values); setPage(1); }}
              allTopics={allTopics}
              allTags={allTags}
              topicCounts={topicCounts}
              exportPapers={exportPapers}
              focusTopics={activeFocusTopics}
              setFocusTopics={setFocusTopics}
              shortlist={shortlist}
              shortlistGroups={shortlistGroups}
              shortlistGroupNames={shortlistGroupNames}
              compareIds={compareIds}
              toggleCompare={toggleCompare}
              saveToShortlist={saveToShortlist}
              setSelectedPaper={setSelectedPaper}
              jumpToTopic={jumpToTopic}
            />
          )}
          {view === "topics" && <TopicsView catalog={catalog} topics={activeFocusTopics} topicCounts={topicCounts} jumpToTopic={jumpToTopic} setSelectedPaper={setSelectedPaper} />}
          {view === "teams" && <TeamsView papers={papers} allTopics={allTopics} focusTopics={activeFocusTopics} setSelectedPaper={setSelectedPaper} />}
          {view === "compare" && <CompareView papers={comparePapers} remove={toggleCompare} jumpToLibrary={() => setView("library")} setSelectedPaper={setSelectedPaper} />}
          {view === "seminar" && <SeminarView papers={shortlistPapers} paperGroups={shortlistGroups} groupNames={shortlistGroupNames} setPaperGroup={setPaperShortlistGroup} removeFromShortlist={removeFromShortlist} setSelectedPaper={setSelectedPaper} exportShortlist={exportShortlist} jumpToLibrary={() => setView("library")} />}
          {view === "data" && <DataView catalog={catalog} />}
        </main>
      </div>

      {selectedPaper && (
        <PaperDrawer
          paper={selectedPaper}
          shortlisted={shortlist.includes(selectedPaper.id)}
          shortlistGroup={shortlistGroups[selectedPaper.id] || DEFAULT_SHORTLIST_GROUP}
          suggestedGroup={suggestedShortlistGroup(selectedPaper, { query, topics, tags, tracks })}
          shortlistGroupNames={shortlistGroupNames}
          close={() => setSelectedPaper(null)}
          saveToShortlist={(group) => saveToShortlist(selectedPaper.id, group)}
          compared={compareIds.includes(selectedPaper.id)}
          toggleCompare={() => toggleCompare(selectedPaper.id)}
        />
      )}
    </div>
  );
}

type LibraryProps = {
  catalog: Catalog;
  filtered: Paper[];
  query: string;
  page: number;
  setPage: (page: number) => void;
  venue: string;
  setVenue: (value: string) => void;
  year: string;
  setYear: (value: string) => void;
  tracks: string[];
  setTracks: (values: string[]) => void;
  topics: string[];
  setTopics: (values: string[]) => void;
  tags: string[];
  setTags: (values: string[]) => void;
  allTopics: string[];
  allTags: [string, number][];
  topicCounts: Map<string, number>;
  exportPapers: (papers: Paper[], scopeLabel: string) => void;
  focusTopics: string[];
  setFocusTopics: (topics: string[]) => void;
  shortlist: string[];
  shortlistGroups: Record<string, string>;
  shortlistGroupNames: string[];
  compareIds: string[];
  toggleCompare: (id: string) => void;
  saveToShortlist: (id: string, group: string) => void;
  setSelectedPaper: (paper: Paper) => void;
  jumpToTopic: (topic: string) => void;
};

function ChoiceChip({ label, active, count, removable = false, onClick }: { label: string; active: boolean; count?: number; removable?: boolean; onClick: () => void }) {
  return (
    <button className={`filter-chip ${active ? "active" : ""} ${active && removable ? "removable" : ""}`} aria-label={active && removable ? `移除筛选：${label}` : undefined} aria-pressed={active} onClick={onClick}>
      <span>{label}</span>{count !== undefined && <small>{fmt(count)}</small>}{active && removable && <span className="chip-remove" aria-hidden="true">×</span>}
    </button>
  );
}

function suggestedShortlistGroup(paper: Paper, context: { query: string; topics: string[]; tags: string[]; tracks: string[] }) {
  const matchedTopic = context.topics.find((item) => item === paper.primaryTopic);
  if (matchedTopic) return normalizeShortlistGroup(matchedTopic);
  const matchedTag = context.tags.find((item) => paper.tags.some((tag) => tag.name === item));
  if (matchedTag) return normalizeShortlistGroup(matchedTag);
  if (context.query.trim()) return normalizeShortlistGroup(context.query);
  const matchedTrack = context.tracks.find((item) => item === paper.track);
  if (matchedTrack) return normalizeShortlistGroup(matchedTrack);
  return normalizeShortlistGroup(paper.primaryTopic);
}

function ReadingListPicker({ paperTitle, shortlisted, currentGroup, suggestedGroup, groups, onConfirm }: {
  paperTitle: string;
  shortlisted: boolean;
  currentGroup: string;
  suggestedGroup: string;
  groups: string[];
  onConfirm: (group: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState("");
  const [group, setGroup] = useState(currentGroup || suggestedGroup || DEFAULT_SHORTLIST_GROUP);
  const choices = Array.from(new Set([group, currentGroup, suggestedGroup, ...groups].filter(Boolean)));

  function openPicker() {
    setGroup(shortlisted ? currentGroup : suggestedGroup);
    setCreating(false);
    setOpen(true);
  }

  function beginCreating() {
    setDraft(group === DEFAULT_SHORTLIST_GROUP ? suggestedGroup : group);
    setCreating(true);
  }

  return (
    <div className="reading-list-picker">
      <button
        type="button"
        className={`save-button ${shortlisted ? "saved" : ""}`}
        aria-expanded={open}
        aria-haspopup="dialog"
        title={shortlisted ? `当前分组：${currentGroup}` : `建议分组：${suggestedGroup}`}
        onClick={openPicker}
      >
        {shortlisted ? `已加入 · ${currentGroup}` : "加入研读列表"}
      </button>
      {open && (
        <div className="reading-list-popover" role="dialog" aria-label={`将 ${paperTitle} 加入研读列表`} onKeyDown={(event) => { if (event.key === "Escape") setOpen(false); }}>
          <div className="reading-list-popover-head">
            <strong>{shortlisted ? "调整研读分组" : "加入研读列表"}</strong>
            <button type="button" aria-label="关闭分组选择" onClick={() => setOpen(false)}>×</button>
          </div>
          <p>{shortlisted ? "选择新的研读主题后保存。" : "已根据当前筛选条件建议分组，你可以直接修改。"}</p>
          <label className="reading-list-field">
            <span>研读分组</span>
            <select autoFocus value={group} onChange={(event) => setGroup(event.target.value)}>
              {choices.map((choice) => <option key={choice} value={choice}>{choice}</option>)}
            </select>
          </label>
          <button type="button" className="new-group-button" onClick={beginCreating}>新建分组</button>
          {creating && (
            <form className="group-create" onSubmit={(event) => { event.preventDefault(); setGroup(normalizeShortlistGroup(draft)); setCreating(false); }}>
              <input autoFocus value={draft} maxLength={40} onChange={(event) => setDraft(event.target.value)} aria-label="新分组名称" placeholder="例如：CI/CD Actions" />
              <button type="submit">使用此分组</button>
              <button type="button" onClick={() => setCreating(false)}>取消</button>
            </form>
          )}
          <div className="reading-list-actions">
            <button type="button" className="primary-button" onClick={() => { onConfirm(group); setOpen(false); }}>{shortlisted ? "保存分组" : "加入研读列表"}</button>
            <button type="button" className="quiet-button" onClick={() => setOpen(false)}>取消</button>
          </div>
        </div>
      )}
    </div>
  );
}
function LibraryView(props: LibraryProps) {
  const pageSize = 18;
  const pageCount = Math.max(1, Math.ceil(props.filtered.length / pageSize));
  const visible = props.filtered.slice((props.page - 1) * pageSize, props.page * pageSize);
  const coverageYears = [...props.catalog.coverage.years].sort((a, b) => b - a);
  const [coverageYear, setCoverageYear] = useState(coverageYears[0]);
  const [focusEditorOpen, setFocusEditorOpen] = useState(false);
  const [showAllTracks, setShowAllTracks] = useState(false);
  const [showAllTopics, setShowAllTopics] = useState(false);
  const [showAllTags, setShowAllTags] = useState(false);
  const coverageVenues = Array.from(new Set([...props.catalog.coverageStatus.map((item) => item.venue), ...props.catalog.coverage.venues]));
  const coverageItems: CoverageStatus[] = coverageVenues.map((venueName) => {
    const published = props.catalog.coverageStatus.find((item) => item.year === coverageYear && item.venue === venueName);
    if (published) return published;
    const venuePapers = props.catalog.papers.filter((paper) => paper.year === coverageYear && paper.venue === venueName);
    return {
      venue: venueName,
      year: coverageYear,
      state: venuePapers.length ? "complete" : "awaiting",
      label: venuePapers.length ? "本地库已收录" : "暂无可核验记录",
      publishedCount: venuePapers.length || null,
      collectedCount: venuePapers.length,
      sourceUrl: venuePapers[0]?.venueUrl ?? "#",
      note: venuePapers.length ? `本地库收录 ${venuePapers.length} 篇。` : "本地库暂无该会议记录。",
    };
  });
  const compactTopics = Array.from(new Set([...props.focusTopics, ...props.topics])).filter((item) => props.allTopics.includes(item));
  const visibleTopics = showAllTopics ? props.allTopics : compactTopics;
  const compactTags = props.allTags.slice(0, 16);
  const selectedTags = props.allTags.filter(([item]) => props.tags.includes(item));
  const visibleTags = showAllTags ? props.allTags : Array.from(new Map([...compactTags, ...selectedTags]).entries());
  const trackOptions = useMemo(() => {
    const counts = new Map<string, number>();
    props.catalog.papers.forEach((paper) => {
      if (!paper.track) return;
      if (props.venue !== "全部会议" && paper.venue !== props.venue) return;
      if (props.year !== "全部年份" && paper.year !== Number(props.year)) return;
      counts.set(paper.track, (counts.get(paper.track) ?? 0) + 1);
    });
    return Array.from(counts.entries())
      .map(([track, count]) => ({ track, count }))
      .sort((a, b) => b.count - a.count || a.track.localeCompare(b.track, "en"));
  }, [props.catalog.papers, props.venue, props.year]);
  const compactTracks = trackOptions.slice(0, 16);
  const selectedTracks = props.tracks.map((value) => trackOptions.find((item) => item.track === value) ?? { track: value, count: 0 });
  const collapsedTracks = Array.from(new Map([...compactTracks, ...selectedTracks].map((item) => [item.track, item])).values());
  const visibleTracks = showAllTracks ? trackOptions : collapsedTracks;
  const trackPaperCount = trackOptions.reduce((total, item) => total + item.count, 0);
  const hasFilters = props.venue !== "全部会议" || props.year !== "全部年份" || props.tracks.length > 0 || props.topics.length > 0 || props.tags.length > 0;
  const selectionScope = (label: string, values: string[]) => values.length ? `${label}-${values.length <= 2 ? values.join("+") : `${values[0]}等${values.length}项`}` : "";
  const exportScope = [selectionScope("Topic", props.topics), props.year === "全部年份" ? "" : props.year, props.venue === "全部会议" ? "" : props.venue, selectionScope("Track", props.tracks), selectionScope("标签", props.tags)].filter(Boolean).join("-") || "全部论文";
  const filterSummary = [props.venue === "全部会议" ? "" : props.venue, props.year === "全部年份" ? "" : props.year, props.tracks.length ? `Track：${props.tracks.join("、")}` : "", props.topics.length ? `Topic：${props.topics.join("、")}` : "", props.tags.length ? `标签：${props.tags.join("、")}` : ""].filter(Boolean).join(" · ");
  const paperSectionTitle = props.topics.length === 0 ? "论文库" : props.topics.length === 1 ? props.topics[0] : `已选 ${props.topics.length} 个 Topic`;

  function toggleFocus(item: string) {
    props.setFocusTopics(props.focusTopics.includes(item) ? props.focusTopics.filter((topic) => topic !== item) : [...props.focusTopics, item]);
  }

  function toggleSelection(values: string[], value: string, onChange: (next: string[]) => void) {
    onChange(values.includes(value) ? values.filter((item) => item !== value) : [...values, value]);
  }

  function clearFilters() {
    props.setVenue("全部会议");
    props.setYear("全部年份");
    props.setTracks([]);
    props.setTopics([]);
    props.setTags([]);
  }

  return (
    <>

      <section className="latest-coverage" aria-labelledby="latest-heading">
        <div className="latest-heading">
          <div><h2 id="latest-heading">{coverageYear} 年四大会收录</h2><p>切换年份查看各会议论文数量；2026 年同时标明官网公开进度。</p></div>
          <div className="year-switcher" aria-label="选择收录年份">
            {coverageYears.map((item) => <ChoiceChip key={item} label={String(item)} active={coverageYear === item} onClick={() => setCoverageYear(item)} />)}
          </div>
        </div>
        <div className="coverage-list">
          {coverageItems.map((item) => (
            <a href={item.sourceUrl} target={item.sourceUrl === "#" ? undefined : "_blank"} rel="noreferrer" key={`${item.year}-${item.venue}`} className={`coverage-item ${item.state}`} title={item.note}>
              <span>{item.venue}</span>
              <strong>{item.state === "awaiting" ? "等待论文列表" : `${fmt(item.collectedCount)}${item.publishedCount && item.publishedCount !== item.collectedCount ? ` / ${fmt(item.publishedCount)}` : ""} 篇`}</strong>
              <small>{item.label}</small>
            </a>
          ))}
        </div>
      </section>

      <section className="focus-section" aria-labelledby="focus-heading">
        <div className="section-heading compact">
          <div><h2 id="focus-heading">常用研究方向</h2><p>个人偏好只影响快捷入口，不参与 Topic 判定。</p></div>
          <button className="quiet-button" aria-expanded={focusEditorOpen} onClick={() => setFocusEditorOpen(!focusEditorOpen)}>{focusEditorOpen ? "收起设置" : "设置方向"}</button>
        </div>
        {focusEditorOpen && (
          <div className="focus-editor">
            <div className="focus-options">
              {props.allTopics.map((item) => <ChoiceChip key={item} label={item} active={props.focusTopics.includes(item)} count={props.topicCounts.get(item) ?? 0} onClick={() => toggleFocus(item)} />)}
            </div>
            <button className="text-link" onClick={() => props.setFocusTopics(props.catalog.priorityTopics)}>恢复当前默认方向</button>
          </div>
        )}
        {props.focusTopics.length ? (
          <div className="topic-strip">
            {props.focusTopics.map((item) => {
              const meta = TOPIC_META[item] ?? { code: "SEC", note: "重点安全方向", color: "mint" };
              return (
                <button className={`topic-card ${meta.color}`} key={item} onClick={() => props.jumpToTopic(item)}>
                  <span className="topic-code">{meta.code}</span>
                  <strong>{item}</strong>
                  <b>{fmt(props.topicCounts.get(item) ?? 0)}</b>
                </button>
              );
            })}
          </div>
        ) : <p className="focus-empty">尚未选择常用方向，点击“设置方向”添加。</p>}
      </section>

      <section className="paper-section">
        <div className="section-heading">
          <h2>{paperSectionTitle}</h2>
          <div className="section-actions">
            <p><strong>{fmt(props.filtered.length)}</strong> 篇匹配论文</p>

            <button className="export-button" disabled={!props.filtered.length} onClick={() => props.exportPapers(props.filtered, exportScope)}>导出当前结果 Excel</button>
          </div>
        </div>
        <div className="filter-panel" aria-label="论文筛选">
          <div className="filter-row">
            <strong>会议</strong>
            <div className="filter-choices">
              <ChoiceChip label="全部" active={props.venue === "全部会议"} onClick={() => props.setVenue("全部会议")} />
              {props.catalog.coverage.venues.map((item) => <ChoiceChip key={item} label={item} active={props.venue === item} count={props.catalog.papers.filter((paper) => paper.venue === item).length} onClick={() => props.setVenue(item)} />)}
            </div>
          </div>
          <div className="filter-row">
            <strong>年份</strong>
            <div className="filter-choices">
              <ChoiceChip label="全部" active={props.year === "全部年份"} onClick={() => props.setYear("全部年份")} />
              {coverageYears.map((item) => <ChoiceChip key={item} label={String(item)} active={props.year === String(item)} count={props.catalog.papers.filter((paper) => paper.year === item).length} onClick={() => props.setYear(String(item))} />)}
            </div>
          </div>
          <div className="filter-row track-filter-row">
            <strong>Track</strong>
            <div className={`filter-choices track-choices ${showAllTracks ? "expanded" : ""}`}>
              <ChoiceChip label="全部" active={props.tracks.length === 0} onClick={() => props.setTracks([])} />
              {visibleTracks.map((item) => <ChoiceChip key={item.track} label={item.track} active={props.tracks.includes(item.track)} removable count={item.count} onClick={() => toggleSelection(props.tracks, item.track, props.setTracks)} />)}
              {trackOptions.length > collapsedTracks.length && <button className="filter-more" onClick={() => setShowAllTracks(!showAllTracks)}>{showAllTracks ? "收起 Track" : `更多 Track（${trackOptions.length - collapsedTracks.length}）`}</button>}
              <span className="track-coverage">{trackOptions.length ? `${fmt(trackPaperCount)} 篇 · ${fmt(trackOptions.length)} 个归一化方向` : "当前范围暂无 Track"}</span>
            </div>
          </div>
          <div className="filter-row">
            <strong>Topic</strong>
            <div className="filter-choices">
              <ChoiceChip label="全部" active={props.topics.length === 0} onClick={() => props.setTopics([])} />
              {visibleTopics.map((item) => <ChoiceChip key={item} label={item} active={props.topics.includes(item)} removable count={props.topicCounts.get(item) ?? 0} onClick={() => toggleSelection(props.topics, item, props.setTopics)} />)}
              {props.allTopics.length > compactTopics.length && <button className="filter-more" onClick={() => setShowAllTopics(!showAllTopics)}>{showAllTopics ? "收起 Topic" : `更多 Topic（${props.allTopics.length - compactTopics.length}）`}</button>}
            </div>
          </div>
          <div className="filter-row">
            <strong>标签</strong>
            <div className="filter-choices">
              <ChoiceChip label="全部" active={props.tags.length === 0} onClick={() => props.setTags([])} />
              {visibleTags.map(([item, count]) => <ChoiceChip key={item} label={item} active={props.tags.includes(item)} removable count={count} onClick={() => toggleSelection(props.tags, item, props.setTags)} />)}
              {props.allTags.length > compactTags.length && <button className="filter-more" onClick={() => setShowAllTags(!showAllTags)}>{showAllTags ? "收起标签" : `更多标签（${props.allTags.length - compactTags.length}）`}</button>}
            </div>
          </div>
          {hasFilters && <div className="filter-summary"><span>当前筛选：{filterSummary}</span><button className="clear-button" onClick={clearFilters}>清空筛选</button></div>}
        </div>

        <div className="paper-list">
          {visible.map((paper) => (
            <PaperCard
              key={paper.id}
              paper={paper}
              shortlisted={props.shortlist.includes(paper.id)}
              shortlistGroup={props.shortlistGroups[paper.id] || DEFAULT_SHORTLIST_GROUP}
              suggestedGroup={suggestedShortlistGroup(paper, props)}
              shortlistGroupNames={props.shortlistGroupNames}
              compared={props.compareIds.includes(paper.id)}
              toggleCompare={() => props.toggleCompare(paper.id)}
              saveToShortlist={(group) => props.saveToShortlist(paper.id, group)}
              open={() => props.setSelectedPaper(paper)}
            />
          ))}
          {visible.length === 0 && <div className="empty-state"><span>⌕</span><h3>没有找到匹配论文</h3><p>试试减少筛选条件，或搜索更短的关键词。</p></div>}
        </div>

        {pageCount > 1 && (
          <div className="pagination">
            <button disabled={props.page === 1} onClick={() => props.setPage(props.page - 1)}>上一页</button>
            <span>第 {props.page} / {pageCount} 页</span>
            <button disabled={props.page === pageCount} onClick={() => props.setPage(props.page + 1)}>下一页</button>
          </div>
        )}
      </section>
    </>
  );
}

function PaperCard({ paper, shortlisted, shortlistGroup, suggestedGroup, shortlistGroupNames, compared, toggleCompare, saveToShortlist, open }: { paper: Paper; shortlisted: boolean; shortlistGroup: string; suggestedGroup: string; shortlistGroupNames: string[]; compared: boolean; toggleCompare: () => void; saveToShortlist: (group: string) => void; open: () => void }) {
  return (
    <article className="paper-card">
      <div className="paper-index"><span className={`venue-mark ${venueClass(paper.venue)}`}>{paper.venue.replace(" Security", "")}</span><small>{paper.year}</small></div>
      <div className="paper-body">
        <button className="paper-title" onClick={open}>{paper.title}</button>
        <p className="authors">{paper.authors.slice(0, 6).join(" · ")}{paper.authors.length > 6 && ` · +${paper.authors.length - 6}`}</p>
        <p className="paper-summary">{paper.summaryZh || "中文概述待生成；英文摘要和来源信息可在详情中查看。"}</p>
        <div className="paper-meta">
          {paper.track && <span className="track-chip" title="跨会议、跨年份归一化 Track">{paper.track}</span>}
          <button className="topic-pill" onClick={open}>{paper.primaryTopic}</button>
          {paper.tags.slice(0, 4).map((item) => <span className="tag" key={item.name}>{item.name}</span>)}
          {!paper.abstract && <span className="missing-chip">摘要待补</span>}
        </div>
      </div>
      <div className="paper-actions">
        <ReadingListPicker paperTitle={paper.title} shortlisted={shortlisted} currentGroup={shortlistGroup} suggestedGroup={suggestedGroup} groups={shortlistGroupNames} onConfirm={saveToShortlist} />
        <button className={`compare-button ${compared ? "selected" : ""}`} onClick={toggleCompare}>{compared ? "已加入对比" : "加入对比"}</button>
      </div>
    </article>
  );
}

function TopicsView({ catalog, topics, topicCounts, jumpToTopic, setSelectedPaper }: { catalog: Catalog; topics: string[]; topicCounts: Map<string, number>; jumpToTopic: (topic: string) => void; setSelectedPaper: (paper: Paper) => void }) {
  const years = catalog.coverage.years;
  return (
    <section className="inner-view">
      <div className="view-intro"><h1>重点方向演化</h1><p>按出版年度观察论文数量与问题重心。分类为机器候选，可在后续人工审核流程中修正。</p></div>
      <div className="timeline-grid">
        {topics.map((topic) => {
          const meta = TOPIC_META[topic];
          const topicPapers = catalog.papers.filter((paper) => paper.primaryTopic === topic);
          const counts = years.map((year) => topicPapers.filter((paper) => paper.year === year).length);
          const max = Math.max(...counts, 1);
          return (
            <article className="timeline-card" key={topic}>
              <div className="timeline-head"><span className={`topic-code ${meta?.color ?? "mint"}`}>{meta?.code ?? "SEC"}</span><div><h2>{topic}</h2><p>{meta?.note}</p></div><strong>{topicCounts.get(topic) ?? 0}</strong></div>
              <div className="bars">
                {years.map((year, index) => <div key={year}><span><i style={{ width: `${Math.max(5, (counts[index] / max) * 100)}%` }} /></span><b>{year}</b><em>{counts[index]}</em></div>)}
              </div>
              <div className="representative-list">
                {topicPapers.slice(0, 3).map((paper) => <button key={paper.id} onClick={() => setSelectedPaper(paper)}><span>{paper.year}</span>{paper.title}</button>)}
              </div>
              <button className="text-link" onClick={() => jumpToTopic(topic)}>查看全部 {topicCounts.get(topic) ?? 0} 篇 →</button>
            </article>
          );
        })}
      </div>
    </section>
  );
}

type TeamGroup = {
  anchor: string;
  members: string[];
  papers: Paper[];
  topTopic: string;
  topicCounts: Map<string, number>;
};

function buildGroups(papers: Paper[]): TeamGroup[] {
  const byAuthor = new Map<string, Paper[]>();
  papers.forEach((paper) => paper.authors.forEach((author) => byAuthor.set(author, [...(byAuthor.get(author) ?? []), paper])));
  const candidates = Array.from(byAuthor.entries()).filter(([, items]) => items.length >= 3).sort((a, b) => b[1].length - a[1].length);
  const groups: TeamGroup[] = [];
  for (const [anchor, items] of candidates) {
    if (groups.length >= 120 || new Set(items.map((paper) => paper.year)).size < 2) continue;
    const coauthors = new Map<string, number>();
    items.forEach((paper) => paper.authors.forEach((author) => { if (author !== anchor) coauthors.set(author, (coauthors.get(author) ?? 0) + 1); }));
    const members = [anchor, ...Array.from(coauthors.entries()).filter(([, count]) => count >= 2).sort((a, b) => b[1] - a[1]).slice(0, 7).map(([name]) => name)];
    if (members.length < 2) continue;
    const duplicate = groups.some((group) => {
      const overlap = members.filter((member) => group.members.includes(member)).length;
      return overlap >= 3 && overlap / Math.min(members.length, group.members.length) >= 0.6;
    });
    if (duplicate) continue;
    const topics = new Map<string, number>();
    items.forEach((paper) => topics.set(paper.primaryTopic, (topics.get(paper.primaryTopic) ?? 0) + 1));
    const topTopic = Array.from(topics.entries()).sort((a, b) => b[1] - a[1])[0]?.[0] ?? "综合安全研究";
    groups.push({ anchor, members, papers: items, topTopic, topicCounts: topics });
  }
  return groups;
}

function TeamsView({ papers, allTopics, focusTopics, setSelectedPaper }: { papers: Paper[]; allTopics: string[]; focusTopics: string[]; setSelectedPaper: (paper: Paper) => void }) {
  const groups = useMemo(() => buildGroups(papers), [papers]);
  const coverageYears = useMemo(() => Array.from(new Set(papers.map((paper) => paper.year))).sort(), [papers]);
  const [teamTopic, setTeamTopic] = useState("全部方向");
  const [visibleCount, setVisibleCount] = useState(24);
  const orderedTopics = useMemo(() => Array.from(new Set([...focusTopics, ...allTopics])), [focusTopics, allTopics]);
  const groupTopicCounts = useMemo(() => new Map(orderedTopics.map((topic) => [topic, groups.filter((group) => group.topicCounts.has(topic)).length])), [groups, orderedTopics]);
  const filteredGroups = useMemo(() => groups
    .filter((group) => teamTopic === "全部方向" || group.topicCounts.has(teamTopic))
    .sort((a, b) => teamTopic === "全部方向" ? b.papers.length - a.papers.length : (b.topicCounts.get(teamTopic) ?? 0) - (a.topicCounts.get(teamTopic) ?? 0)), [groups, teamTopic]);

  function selectTeamTopic(value: string) {
    setTeamTopic(value);
    setVisibleCount(24);
  }

  return (
    <section className="inner-view">
      <div className="view-intro"><h1>持续研究团队线索</h1><p>依据跨年度共同作者关系生成候选团队，并可按研究方向查看持续工作。结果是论文选择线索，不代表已核实的机构或实验室归属。</p></div>
      <div className="team-toolbar">
        <div><strong>{fmt(filteredGroups.length)} 组</strong><span>{teamTopic === "全部方向" ? `共构建 ${fmt(groups.length)} 个跨年合作组` : `包含“${teamTopic}”论文的合作组`}</span></div>
        <div className="team-filter" aria-label="按研究方向筛选团队">
          <ChoiceChip label="全部方向" active={teamTopic === "全部方向"} count={groups.length} onClick={() => selectTeamTopic("全部方向")} />
          {orderedTopics.map((topic) => <ChoiceChip key={topic} label={topic} active={teamTopic === topic} count={groupTopicCounts.get(topic) ?? 0} onClick={() => selectTeamTopic(topic)} />)}
        </div>
      </div>
      <div className="method-note"><strong>算法口径</strong><span>核心作者 ≥ 3 篇 · 跨至少 2 年 · 合作者共同出现 ≥ 2 次 · 相似成员组去重 · 最多保留 120 组</span></div>
      {filteredGroups.length ? (
        <>
          <div className="team-grid">
            {filteredGroups.slice(0, visibleCount).map((group) => {
              const matchedPapers = teamTopic === "全部方向" ? group.papers : group.papers.filter((paper) => paper.primaryTopic === teamTopic);
              const years = Array.from(new Set(group.papers.map((paper) => paper.year))).sort();
              return (
                <article className="team-card" key={group.anchor}>
                  <div className="team-title"><div className="avatar-stack">{group.members.slice(0, 3).map((member) => <span key={member}>{initials(member)}</span>)}</div><div><h2>{group.anchor} 合作组</h2><p>算法推断 · 待人工确认</p></div></div>
                  <div className="team-focus"><span>{teamTopic === "全部方向" ? "主要方向" : "当前方向"}</span><strong>{teamTopic === "全部方向" ? group.topTopic : `${teamTopic} · ${matchedPapers.length} 篇`}</strong></div>
                  <div className="team-stats"><div><b>{group.papers.length}</b><span>全部论文</span></div><div><b>{years.join("—")}</b><span>活跃年度</span></div></div>
                  <div className="team-yearline">{coverageYears.map((year) => <span key={year}><b>{matchedPapers.filter((paper) => paper.year === year).length}</b><small>{year}</small></span>)}</div>
                  <div className="member-list">{group.members.map((member) => <span key={member}>{member}</span>)}</div>
                  <div className="team-papers">{matchedPapers.slice(0, 3).map((paper) => <button key={paper.id} onClick={() => setSelectedPaper(paper)}>{paper.title}</button>)}</div>
                </article>
              );
            })}
          </div>
          {visibleCount < filteredGroups.length && <div className="load-more"><button className="primary-button" onClick={() => setVisibleCount((count) => count + 24)}>显示更多团队</button><span>已显示 {Math.min(visibleCount, filteredGroups.length)} / {filteredGroups.length} 组</span></div>}
        </>
      ) : <div className="empty-state"><span>⌕</span><h3>这个方向暂未形成跨年合作组</h3><p>可切换到其他方向，或在论文库按作者继续查找。</p></div>}
    </section>
  );
}
type SeminarViewProps = {
  papers: Paper[];
  paperGroups: Record<string, string>;
  groupNames: string[];
  setPaperGroup: (id: string, value: string) => void;
  removeFromShortlist: (id: string) => void;
  setSelectedPaper: (paper: Paper) => void;
  exportShortlist: () => void;
  jumpToLibrary: () => void;
};

function SeminarView({ papers, paperGroups, groupNames, setPaperGroup, removeFromShortlist, setSelectedPaper, exportShortlist, jumpToLibrary }: SeminarViewProps) {
  const groups = Array.from(new Set(papers.map((paper) => paperGroups[paper.id] || DEFAULT_SHORTLIST_GROUP)))
    .map((name) => ({ name, papers: papers.filter((paper) => (paperGroups[paper.id] || DEFAULT_SHORTLIST_GROUP) === name) }));
  return (
    <section className="inner-view">
      <div className="view-intro split">
        <div><h1>论文研读列表</h1><p>按自定义研读主题组织。Topic 与 Track 保留为论文属性，不再决定列表归类；研读列表只保存在当前浏览器。</p></div>
        <div className="view-intro-actions">{papers.length > 0 && <button className="primary-button" onClick={exportShortlist}>导出 Excel</button>}</div>
      </div>
      {papers.length === 0 ? (
        <div className="empty-state seminar-empty"><span>＋</span><h3>研读列表还是空的</h3><p>在论文库中点击“加入研读列表”，把计划深入阅读或对比分析的论文放进来。</p><button className="primary-button" onClick={jumpToLibrary}>去论文库挑选</button></div>
      ) : (
        <div className="seminar-groups">
          {groups.map((group) => (
            <article key={group.name}>
              <div className="seminar-group-head"><div><span>研读主题</span><h2>{group.name}</h2></div><b>{group.papers.length} 篇</b></div>
              {group.papers.map((paper, index) => (
                <div className="seminar-paper" key={paper.id}>
                  <span className="order">{String(index + 1).padStart(2, "0")}</span>
                  <button onClick={() => setSelectedPaper(paper)}><strong>{paper.title}</strong><small>{paper.venue} · {paper.year}{paper.track ? ` · ${paper.track}` : ""} · {paper.authors.slice(0, 3).join(", ")}</small></button>
                  <label className="paper-group-select"><span>分组</span><select value={group.name} onChange={(event) => setPaperGroup(paper.id, event.target.value)} aria-label={`修改 ${paper.title} 的研读分组`}>{groupNames.map((name) => <option key={name} value={name}>{name}</option>)}</select></label>
                  <button className="remove-button" onClick={() => removeFromShortlist(paper.id)}>移除</button>
                </div>
              ))}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function CompareView({ papers, remove, jumpToLibrary, setSelectedPaper }: { papers: Paper[]; remove: (id: string) => void; jumpToLibrary: () => void; setSelectedPaper: (paper: Paper) => void }) {
  const commonTags = papers.length >= 2
    ? papers[0].tags.map((tag) => tag.name).filter((name) => papers.slice(1).every((paper) => paper.tags.some((tag) => tag.name === name)))
    : [];
  const sameTopic = papers.length >= 2 && papers.every((paper) => paper.primaryTopic === papers[0].primaryTopic);
  const tagText = (paper: Paper, types: string[]) => {
    const values = paper.tags.filter((tag) => types.includes(tag.type)).map((tag) => tag.name);
    return values.length ? values.join(" · ") : "未提取到明确标签";
  };

  return (
    <section className="inner-view">
      <div className="view-intro split"><div><h1>论文区别对比</h1><p>把 2–3 篇论文放到同一组，用统一维度比较研究对象、方法、威胁和贡献线索。当前结论来自结构化字段，需结合原文复核。</p></div>{papers.length < 3 && <button className="primary-button" onClick={jumpToLibrary}>继续选择论文</button>}</div>
      {papers.length < 2 ? (
        <div className="empty-state seminar-empty"><span>⇄</span><h3>至少选择两篇论文</h3><p>在论文库点击“加入对比”，最多可以并排比较三篇。</p><button className="primary-button" onClick={jumpToLibrary}>去选择论文</button></div>
      ) : (
        <>
          <div className="comparison-insight">
            <div><span>共同点</span><strong>{sameTopic ? `同属 ${papers[0].primaryTopic}` : "跨 Topic 对比"}</strong><p>{commonTags.length ? `共同标签：${commonTags.join("、")}` : "暂无共同的受控标签，适合用于观察问题设定差异。"}</p></div>
            <div><span>阅读建议</span><strong>{papers[0].year === papers[1].year ? "同年横向比较" : "跨年演化比较"}</strong><p>优先核对威胁模型、目标对象、实验基线与评估指标，机器概述不作为结论证据。</p></div>
          </div>
          <div className={`compare-table compare-cols-${papers.length}`}>
            <div className="compare-row compare-head-row"><div className="compare-label">对比论文</div>{papers.map((paper) => <article key={paper.id}><button className="compare-remove" onClick={() => remove(paper.id)}>移除</button><span className={`venue-mark ${venueClass(paper.venue)}`}>{paper.venue} · {paper.year}</span><button className="compare-title" onClick={() => setSelectedPaper(paper)}>{paper.title}</button><small>{paper.authors.slice(0, 3).join(" · ")}</small></article>)}</div>
            <CompareRow label="主 Topic" papers={papers} render={(paper) => paper.primaryTopic} />
            <CompareRow label="归一化 Track" papers={papers} render={(paper) => paper.track || "尚未归一化"} />
            <CompareRow label="官方 Session" papers={papers} render={(paper) => paper.session || "官网未提供或尚未安排"} />
            <CompareRow label="辅 Topic" papers={papers} render={(paper) => paper.secondaryTopics.join(" · ") || "—"} />
            <CompareRow label="研究对象" papers={papers} render={(paper) => tagText(paper, ["object"])} />
            <CompareRow label="协议与技术" papers={papers} render={(paper) => tagText(paper, ["protocol", "technique"])} />
            <CompareRow label="威胁与目标" papers={papers} render={(paper) => tagText(paper, ["threat", "goal"])} />
            <CompareRow label="中文概述" papers={papers} render={(paper) => paper.summaryZh || "待生成"} long />
            <CompareRow label="摘要证据" papers={papers} render={(paper) => paper.abstract ? `${paper.abstract.slice(0, 360)}${paper.abstract.length > 360 ? "…" : ""}` : "摘要待补"} long />
          </div>
        </>
      )}
    </section>
  );
}

function CompareRow({ label, papers, render, long = false }: { label: string; papers: Paper[]; render: (paper: Paper) => string; long?: boolean }) {
  return <div className={`compare-row ${long ? "long" : ""}`}><div className="compare-label">{label}</div>{papers.map((paper) => <div key={paper.id}>{render(paper)}</div>)}</div>;
}

function DataView({ catalog }: { catalog: Catalog }) {
  const metrics = [
    ["论文全集", catalog.stats.papers, catalog.stats.papers],
    ["英文摘要", catalog.stats.abstracts, catalog.stats.papers],
    ["开放 PDF", catalog.stats.pdfs, catalog.stats.papers],
    ["归一化 Track", catalog.stats.trackPapers, catalog.stats.papers],
    ["Topic 已分析", catalog.stats.analyzed, catalog.stats.papers],
    ["语义中文概述", catalog.stats.semanticSummaries ?? 0, catalog.stats.papers],
  ] as const;
  return (
    <section className="inner-view">
      <div className="view-intro"><h1>数据完整性与来源</h1><p>会议归属以 DBLP 会议卷为发现层，出版方页面提供权威落点，OpenAlex 用于补充摘要和开放版本。</p></div>
      <div className="quality-grid">{metrics.map(([label, value, total]) => { const percent = Math.round((value / total) * 100); return <article key={label}><span>{label}</span><strong>{fmt(value)}</strong><div><i style={{ width: `${percent}%` }} /></div><small>{percent}% 覆盖</small></article>; })}</div>
      <div className="source-table">
        <div className="source-head"><span>数据层</span><span>职责</span><span>当前状态</span></div>
        <div><strong>会议官网 / 出版方</strong><span>保留官方 Session，并生成跨会议、跨年份的 Track</span><em className="good">{fmt(catalog.stats.tracks)} 个归一化 Track</em></div>
        <div><strong>DBLP</strong><span>按会议卷发现全集、标题、作者与 DOI</span><em className="good">已出版会议卷已同步</em></div>
        <div><strong>OpenAlex</strong><span>英文摘要与开放 PDF 补全</span><em className="working">持续补全</em></div>
        <div><strong>受控分类器</strong><span>Topic、对象、协议、技术和威胁标签</span><em className="review">待人工复核</em></div>
        <div><strong>飞书适配器</strong><span>生成智能表格所需记录载荷</span><em>接口已预留</em></div>
      </div>
      <div className="data-foot"><div><span>最近生成</span><strong>{new Date(catalog.generatedAt).toLocaleString("zh-CN")}</strong></div><div><span>分类体系</span><strong>{catalog.taxonomyVersion}</strong></div><div><span>运行模式</span><strong>Local-first · SQLite</strong></div></div>
    </section>
  );
}

function PaperDrawer({ paper, shortlisted, shortlistGroup, suggestedGroup, shortlistGroupNames, compared, close, saveToShortlist, toggleCompare }: { paper: Paper; shortlisted: boolean; shortlistGroup: string; suggestedGroup: string; shortlistGroupNames: string[]; compared: boolean; close: () => void; saveToShortlist: (group: string) => void; toggleCompare: () => void }) {
  return (
    <div className="drawer-layer" role="dialog" aria-modal="true" aria-label={paper.title}>
      <button className="drawer-backdrop" aria-label="关闭详情" onClick={close} />
      <aside className="paper-drawer">
        <div className="drawer-top"><span className={`venue-mark ${venueClass(paper.venue)}`}>{paper.venue}</span><button onClick={close} aria-label="关闭">×</button></div>
        <div className="drawer-scroll">
          <span className="drawer-year">{paper.year} · {paper.primaryTopic}</span>
          <h2>{paper.title}</h2>
          <p className="drawer-authors">{paper.authors.join(" · ")}</p>
          <div className="drawer-actions"><ReadingListPicker paperTitle={paper.title} shortlisted={shortlisted} currentGroup={shortlistGroup} suggestedGroup={suggestedGroup} groups={shortlistGroupNames} onConfirm={saveToShortlist} /><button className={`drawer-compare ${compared ? "selected" : ""}`} onClick={toggleCompare}>{compared ? "已加入对比" : "加入论文对比"}</button>{paper.pdfUrl && <a href={paper.pdfUrl} target="_blank" rel="noreferrer">打开 PDF ↗</a>}{paper.sourceUrl && <a href={paper.sourceUrl} target="_blank" rel="noreferrer">论文页面 ↗</a>}</div>
          <section><h3>中文概述 <span>{summaryEvidenceLabel(paper)}</span></h3><p className={`zh-summary ${paper.summaryZh ? "" : "muted"}`}>{paper.summaryZh || "中文概述待重新生成；当前规则分类结果不再作为论文概述展示。"}</p></section>
          <section><h3>英文摘要 <span>原文</span></h3><p className={`abstract-text ${paper.abstract ? "" : "muted"}`}>{paper.abstract || "当前来源尚未提供摘要，后续采集任务会继续补全。"}</p></section>
          <section><h3>Topic 与标签</h3><div className="drawer-topics"><strong>{paper.primaryTopic}</strong>{paper.secondaryTopics.map((item) => <span key={item}>{item}</span>)}</div><div className="tag-groups">{paper.tags.map((item) => <span key={item.name}><small>{TAG_LABEL[item.type] ?? item.type}</small>{item.name}</span>)}</div></section>
          <section className="provenance"><h3>数据溯源</h3><dl><div><dt>会议</dt><dd>{paper.venueName}</dd></div><div><dt>归一化 Track</dt><dd>{paper.track || "尚未归一化"}</dd></div><div><dt>官方 Session</dt><dd>{paper.session || "官网未提供或尚未安排"}</dd></div><div><dt>DOI</dt><dd>{paper.doi || "未提供"}</dd></div><div><dt>分析置信度</dt><dd>{paper.confidence ? `${Math.round(paper.confidence * 100)}%` : "待分析"}</dd></div></dl></section>
        </div>
      </aside>
    </div>
  );
}













