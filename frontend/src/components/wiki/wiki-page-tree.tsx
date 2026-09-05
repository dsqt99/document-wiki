"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { WikiPageSummary } from "@/types/wiki";
import { wikiTypeIcon, wikiTypeColor, wikiTypeGroupLabel } from "./wiki-type-badge";

const GROUP_ORDER = ["entity", "concept", "topic", "source"];

// Scope type ordering for grouped view: global → department → project.
const SCOPE_TYPE_ORDER: Record<string, number> = {
  global: 0,
  department: 1,
  project: 2,
};

const SCOPE_ICONS: Record<string, string> = {
  global: "public",
  department: "corporate_fare",
  project: "folder_special",
};

/** Normalizes Vietnamese diacritics / tones for accent-insensitive search */
export function removeVietnameseTones(str: string): string {
  return str
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/đ/g, "d")
    .replace(/Đ/g, "d")
    .toLowerCase();
}

function scopeGroupKey(p: WikiPageSummary): string {
  const st = p.scope_type || "global";
  return p.scope_id ? `${st}:${p.scope_id}` : st;
}

function scopeGroupLabel(p: WikiPageSummary): string {
  const st = p.scope_type || "global";
  if (st === "global") return "Global";
  return p.scope_name || (st === "department" ? "Department" : "Workspace");
}

function pageKey(p: WikiPageSummary): string {
  return `${p.slug}-${p.scope_type || "global"}-${p.scope_id ?? "none"}`;
}

function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = React.useState(value);
  React.useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

export function WikiPageTree({
  activeSlug,
  onDeleted,
  pagesUrl,
  linkQueryParams,
  onPageSelect,
  groupByScope = false,
  activeScope,
  getCreateModeForScope,
  onCreatePage,
}: {
  activeSlug?: string;
  onDeleted?: () => void;
  /** Override the API URL to load pages from (default: /api/wiki/pages) */
  pagesUrl?: string;
  /** Query params to append to page links (e.g. "?scopeType=project&scopeId=xxx") */
  linkQueryParams?: string;
  /** If provided, clicks call this instead of navigating via Link */
  onPageSelect?: (slug: string) => void;
  /** When true, render a 2-level tree: scope → page_type → pages (used in /wiki). */
  groupByScope?: boolean;
  /** Auto-expand the bucket matching this scope (used together with groupByScope). */
  activeScope?: { scope_type: string; scope_id: string | null };
  /** Optional: return which create flow ("direct" | "propose" | null) applies for a scope.
   *  When provided AND non-null, the tree shows a `+` button on that scope's header. */
  getCreateModeForScope?: (scope: { scope_type: string; scope_id: string | null }) => "direct" | "propose" | null;
  /** Called when the user clicks the per-scope `+` button. */
  onCreatePage?: (scope: { scope_type: string; scope_id: string | null }) => void;
}) {
  const pathname = usePathname();
  const [pages, setPages] = React.useState<WikiPageSummary[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [search, setSearch] = React.useState("");
  const [collapsed, setCollapsed] = React.useState(false);

  // Filters & grouping states
  const [selectedSourceId, setSelectedSourceId] = React.useState<string | null>(null);
  const [categoryFilter, setCategoryFilter] = React.useState<"all" | "articles" | "overview">("all");
  const [groupByDocument, setGroupByDocument] = React.useState<boolean>(true);
  const [expandedDocuments, setExpandedDocuments] = React.useState<Set<string>>(new Set());

  // Two-stage delete
  const [armedSlug, setArmedSlug] = React.useState<string | null>(null);
  const [deletingSlug, setDeletingSlug] = React.useState<string | null>(null);

  // Sources section
  const [sources, setSources] = React.useState<{ id: string; title: string; file_name?: string; status: string; source_type?: string }[]>([]);
  const [sourcesLoading, setSourcesLoading] = React.useState(true);
  const [sourcesCollapsed, setSourcesCollapsed] = React.useState(false);

  const debouncedSearch = useDebounce(search, 150);

  const loadPages = React.useCallback(() => {
    const url = pagesUrl || "/api/wiki/pages";
    api<WikiPageSummary[]>(url)
      .then((data) => setPages(Array.isArray(data) ? data : []))
      .catch(() => setPages([]))
      .finally(() => setLoading(false));
  }, [pagesUrl]);

  React.useEffect(() => {
    loadPages();
  }, [loadPages]);

  React.useEffect(() => {
    api<{ items: { id: string; title: string; file_name?: string; status: string; source_type?: string }[] }>("/api/sources?status=ready&page_size=1000")
      .then((data) => setSources(data.items || []))
      .catch(() => setSources([]))
      .finally(() => setSourcesLoading(false));
  }, []);

  const handleDelete = async (page: WikiPageSummary) => {
    const slug = page.slug;
    if (armedSlug !== slug) {
      setArmedSlug(slug);
      return;
    }
    setArmedSlug(null);
    setDeletingSlug(slug);
    try {
      const scopeQs =
        page.scope_type && page.scope_type !== "global" && page.scope_id
          ? `?scope_type=${page.scope_type}&scope_id=${page.scope_id}`
          : "";
      await api(`/api/wiki/pages/${encodeURIComponent(slug)}${scopeQs}`, {
        method: "DELETE",
      });
      loadPages();
      onDeleted?.();
    } catch (err) {
      console.error("Delete failed:", err);
    } finally {
      setDeletingSlug(null);
    }
  };

  // Click outside armed row → disarm
  React.useEffect(() => {
    if (!armedSlug) return;
    const handler = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (!target.closest(`[data-slug="${armedSlug}"]`)) {
        setArmedSlug(null);
      }
    };
    document.addEventListener("click", handler, true);
    return () => document.removeEventListener("click", handler, true);
  }, [armedSlug]);

  /** Maps a page to its corresponding source document (if any) */
  const getDocInfoForPage = React.useCallback(
    (p: WikiPageSummary) => {
      if (sources.length === 0) return null;
      // 1. Check explicit source_ids
      if (p.source_ids && p.source_ids.length > 0) {
        for (const sid of p.source_ids) {
          const src = sources.find((s) => s.id === sid);
          if (src) return src;
        }
      }
      // 2. Check title suffix: " - [Doc Title]"
      for (const src of sources) {
        const srcTitle = src.title || src.file_name;
        if (srcTitle && p.title.endsWith(` - ${srcTitle}`)) {
          return src;
        }
        if (srcTitle && (p.title === srcTitle || p.slug === src.id)) {
          return src;
        }
      }
      return null;
    },
    [sources]
  );

  /** Accent-insensitive and multi-field search matcher */
  const matchesSearch = React.useCallback(
    (p: WikiPageSummary, query: string, docTitle?: string): boolean => {
      if (!query) return true;
      const rawQ = query.trim().toLowerCase();
      const normQ = removeVietnameseTones(rawQ);

      const titleRaw = p.title.toLowerCase();
      const titleNorm = removeVietnameseTones(titleRaw);
      if (titleRaw.includes(rawQ) || titleNorm.includes(normQ)) return true;

      const slugRaw = p.slug.toLowerCase();
      const slugNorm = removeVietnameseTones(slugRaw);
      if (slugRaw.includes(rawQ) || slugNorm.includes(normQ)) return true;

      if (p.summary) {
        const sumRaw = p.summary.toLowerCase();
        const sumNorm = removeVietnameseTones(sumRaw);
        if (sumRaw.includes(rawQ) || sumNorm.includes(normQ)) return true;
      }

      if (docTitle) {
        const docRaw = docTitle.toLowerCase();
        const docNorm = removeVietnameseTones(docRaw);
        if (docRaw.includes(rawQ) || docNorm.includes(normQ)) return true;
      }

      // Match article number directly (e.g. searching "12" or "12a" matches "Điều 12: ...")
      const m = p.title.match(/Điều\s+(\d+[a-z]?)/i);
      if (m && m[1].toLowerCase() === rawQ) return true;

      return false;
    },
    []
  );

  /** Natural sorting: overview pages first, then articles sorted numerically (Điều 1, Điều 2, Điều 10...) */
  const naturalSortPages = React.useCallback((a: WikiPageSummary, b: WikiPageSummary) => {
    const aIsOverview = !a.title.startsWith("Điều ");
    const bIsOverview = !b.title.startsWith("Điều ");
    if (aIsOverview && !bIsOverview) return -1;
    if (!aIsOverview && bIsOverview) return 1;
    return a.title.localeCompare(b.title, "vi", { numeric: true });
  }, []);

  /** Filtered list of pages based on Search, Category, and Document filter */
  const filtered = React.useMemo(() => {
    return pages.filter((p) => {
      if (p.page_type === "index" || p.page_type === "log" || p.page_type === "hot") {
        return false;
      }

      // Category filter
      const isArticle = p.title.startsWith("Điều ");
      if (categoryFilter === "articles" && !isArticle) return false;
      if (categoryFilter === "overview" && isArticle) return false;

      // Source / Document filter
      const doc = getDocInfoForPage(p);
      if (selectedSourceId) {
        if (selectedSourceId === "other") {
          if (doc) return false;
        } else {
          if (!doc || doc.id !== selectedSourceId) return false;
        }
      }

      // Accent-insensitive text search
      if (debouncedSearch) {
        if (!matchesSearch(p, debouncedSearch, doc?.title || doc?.file_name)) {
          return false;
        }
      }

      return true;
    });
  }, [pages, debouncedSearch, categoryFilter, selectedSourceId, getDocInfoForPage, matchesSearch]);

  /** Document statistics for dropdown selector and category tabs */
  const sourceStats = React.useMemo(() => {
    const counts = new Map<string, number>();
    let otherCount = 0;
    let articlesCount = 0;
    let overviewsCount = 0;

    for (const p of pages) {
      if (p.page_type === "index" || p.page_type === "log" || p.page_type === "hot") continue;
      if (p.title.startsWith("Điều ")) {
        articlesCount++;
      } else {
        overviewsCount++;
      }

      const doc = getDocInfoForPage(p);
      if (doc) {
        counts.set(doc.id, (counts.get(doc.id) || 0) + 1);
      } else {
        otherCount++;
      }
    }

    return {
      sources: sources.map((s) => ({
        id: s.id,
        title: s.title || s.file_name || "Untitled",
        count: counts.get(s.id) || 0,
      })),
      otherCount,
      articlesCount,
      overviewsCount,
    };
  }, [pages, sources, getDocInfoForPage]);

  const totalCount = React.useMemo(
    () => pages.filter((p) => p.page_type !== "index" && p.page_type !== "log" && p.page_type !== "hot").length,
    [pages]
  );

  const currentSlug = activeSlug ?? pathname.replace(/^\/wiki\//, "");

  // Auto-expand the document folder corresponding to the active page
  React.useEffect(() => {
    if (!currentSlug || pages.length === 0) return;
    const activePage = pages.find((p) => p.slug === currentSlug);
    if (activePage) {
      const doc = getDocInfoForPage(activePage);
      const docKey = doc ? doc.id : "other";
      setExpandedDocuments((prev) => new Set([...prev, docKey]));
    }
  }, [currentSlug, pages, getDocInfoForPage]);

  // Toggle expand/collapse for a document folder
  const toggleDocument = (docId: string) => {
    setExpandedDocuments((prev) => {
      const next = new Set(prev);
      if (next.has(docId)) next.delete(docId);
      else next.add(docId);
      return next;
    });
  };

  const isDocExpanded = (docId: string) => {
    if (debouncedSearch.trim()) return true; // auto-expand on active search
    return expandedDocuments.has(docId);
  };

  /** Groups a list of pages by their parent Document */
  type DocGroup = {
    key: string;
    id: string;
    title: string;
    source?: (typeof sources)[0];
    overviewPage?: WikiPageSummary;
    articles: WikiPageSummary[];
    otherPages: WikiPageSummary[];
    total: number;
  };

  const groupPagesByDocument = React.useCallback(
    (pageList: WikiPageSummary[]): DocGroup[] => {
      const groupMap = new Map<string, DocGroup>();

      for (const s of sources) {
        groupMap.set(s.id, {
          key: s.id,
          id: s.id,
          title: s.title || s.file_name || "Untitled",
          source: s,
          overviewPage: undefined,
          articles: [],
          otherPages: [],
          total: 0,
        });
      }

      const otherGroup: DocGroup = {
        key: "other",
        id: "other",
        title: "Tài liệu khác / Kiến thức chung",
        overviewPage: undefined,
        articles: [],
        otherPages: [],
        total: 0,
      };

      for (const p of pageList) {
        const doc = getDocInfoForPage(p);
        const targetGroup = doc ? groupMap.get(doc.id) || otherGroup : otherGroup;

        targetGroup.total += 1;
        const docTitle = doc?.title || doc?.file_name;

        const isOverview =
          (docTitle && (p.title === docTitle || p.slug === doc?.id)) ||
          (!p.title.startsWith("Điều ") && !targetGroup.overviewPage);

        if (isOverview && !targetGroup.overviewPage) {
          targetGroup.overviewPage = p;
        } else if (p.title.startsWith("Điều ")) {
          targetGroup.articles.push(p);
        } else {
          targetGroup.otherPages.push(p);
        }
      }

      if (otherGroup.total > 0) {
        groupMap.set("other", otherGroup);
      }

      // Sort articles in each group numerically
      for (const g of groupMap.values()) {
        g.articles.sort((a, b) => a.title.localeCompare(b.title, "vi", { numeric: true }));
        g.otherPages.sort((a, b) => a.title.localeCompare(b.title, "vi", { numeric: true }));
      }

      return Array.from(groupMap.values()).filter((g) => g.total > 0);
    },
    [sources, getDocInfoForPage]
  );

  // Scope grouping (used when groupByScope=true)
  const scopeGrouped = React.useMemo(() => {
    type ScopeBucket = {
      key: string;
      label: string;
      scope_type: string;
      scope_id: string | null;
      pages: WikiPageSummary[];
      total: number;
    };
    const map = new Map<string, ScopeBucket>();
    for (const p of filtered) {
      if (p.page_type === "index" || p.page_type === "log" || p.page_type === "hot") continue;
      if ((p.scope_type || "global") === "project") continue;
      const k = scopeGroupKey(p);
      let bucket = map.get(k);
      if (!bucket) {
        bucket = {
          key: k,
          label: scopeGroupLabel(p),
          scope_type: p.scope_type || "global",
          scope_id: p.scope_id ?? null,
          pages: [],
          total: 0,
        };
        map.set(k, bucket);
      }
      bucket.pages.push(p);
      bucket.total += 1;
    }

    return Array.from(map.values()).sort((a, b) => {
      const ao = SCOPE_TYPE_ORDER[a.scope_type] ?? 99;
      const bo = SCOPE_TYPE_ORDER[b.scope_type] ?? 99;
      if (ao !== bo) return ao - bo;
      return a.label.localeCompare(b.label);
    });
  }, [filtered]);

  // Expanded state for scope-level headers in groupByScope mode
  const [expandedScopes, setExpandedScopes] = React.useState<Set<string>>(new Set(["global"]));
  const activeScopeKey = React.useMemo(() => {
    if (!activeScope) return null;
    return activeScope.scope_id ? `${activeScope.scope_type}:${activeScope.scope_id}` : activeScope.scope_type;
  }, [activeScope]);

  React.useEffect(() => {
    if (!groupByScope || scopeGrouped.length === 0) return;
    const scopesToExpand = new Set<string>(["global"]);
    if (activeScopeKey) scopesToExpand.add(activeScopeKey);
    if (activeSlug) {
      for (const b of scopeGrouped) {
        if (b.pages.some((p) => p.slug === activeSlug)) {
          scopesToExpand.add(b.key);
        }
      }
    }
    setExpandedScopes(scopesToExpand);
  }, [groupByScope, scopeGrouped, activeScopeKey, activeSlug]);

  const toggleScope = (key: string) => {
    setExpandedScopes((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  // Renders one leaf row (page link + delete button)
  const renderPageItem = (page: WikiPageSummary, cleanTitle?: string) => {
    const isActive = page.slug === currentSlug;
    const isArmed = armedSlug === page.slug;
    const isDeleting = deletingSlug === page.slug;
    const linkSuffix = linkQueryParams
      ? linkQueryParams
      : page.scope_type && page.scope_type !== "global" && page.scope_id
        ? `?scopeType=${page.scope_type}&scopeId=${page.scope_id}`
        : "";

    const statusColors: Record<string, string> = {
      seed: "bg-[#a8977e]/20 border-[#a8977e]/50",
      developing: "bg-[#d4872e]/20 border-[#d4872e]/50",
      mature: "bg-[#2e8b8b]/20 border-[#2e8b8b]/50",
      evergreen: "bg-[#3a8a3f]/20 border-[#3a8a3f]/50",
    };
    const statusText: Record<string, string> = {
      seed: "Seed",
      developing: "Developing",
      mature: "Mature",
      evergreen: "Evergreen",
    };

    const isOverview = cleanTitle?.includes("Tổng quan");
    const displayTitle = cleanTitle || page.title;

    return (
      <div
        key={pageKey(page)}
        data-slug={page.slug}
        className={cn(
          "group flex items-center gap-1 rounded-lg mx-1 transition-all",
          isActive ? "bg-primary/10" : "hover:bg-accent/50",
        )}
      >
        {onPageSelect ? (
          <button
            onClick={() => onPageSelect(page.slug)}
            className={cn(
              "flex-1 flex items-center gap-2 px-2.5 py-1.5 text-xs min-w-0 transition-all text-left",
              isActive ? "text-primary font-medium" : "text-muted-foreground hover:text-foreground",
            )}
            title={page.summary || page.title}
          >
            {isOverview ? (
              <span className="material-symbols-outlined text-xs text-primary/80 shrink-0" style={{ fontSize: 13 }}>
                menu_book
              </span>
            ) : (
              <span
                className={cn("w-1.5 h-1.5 rounded-full shrink-0 border", statusColors[page.status || "seed"])}
                title={`Status: ${statusText[page.status || "seed"]}`}
              />
            )}
            <span className="truncate">{displayTitle}</span>
          </button>
        ) : (
          <Link
            href={`/wiki/${page.slug}${linkSuffix}`}
            className={cn(
              "flex-1 flex items-center gap-2 px-2.5 py-1.5 text-xs min-w-0 transition-all",
              isActive ? "text-primary font-medium" : "text-muted-foreground hover:text-foreground",
            )}
            title={page.summary || page.title}
          >
            {isOverview ? (
              <span className="material-symbols-outlined text-xs text-primary/80 shrink-0" style={{ fontSize: 13 }}>
                menu_book
              </span>
            ) : (
              <span
                className={cn("w-1.5 h-1.5 rounded-full shrink-0 border", statusColors[page.status || "seed"])}
                title={`Status: ${statusText[page.status || "seed"]}`}
              />
            )}
            <span className="truncate">{displayTitle}</span>
          </Link>
        )}

        {isDeleting ? (
          <span className="material-symbols-outlined text-xs text-destructive animate-pulse mr-1.5">
            progress_activity
          </span>
        ) : isArmed ? (
          <button
            onClick={(e) => {
              e.stopPropagation();
              handleDelete(page);
            }}
            className="shrink-0 mr-1 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-destructive text-destructive-foreground hover:bg-destructive/90 animate-pulse transition-colors"
            title={`Click again to confirm delete "${page.title}"`}
          >
            Confirm
          </button>
        ) : (
          <button
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              handleDelete(page);
            }}
            className="shrink-0 mr-1 opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive transition-all"
            title={`Delete "${page.title}"`}
          >
            <span className="material-symbols-outlined" style={{ fontSize: 14 }}>delete</span>
          </button>
        )}
      </div>
    );
  };

  /** Renders a list of pages, either grouped by Document accordion or flat */
  const renderPagesList = (pageList: WikiPageSummary[]) => {
    if (pageList.length === 0) {
      return (
        <div className="px-4 py-4 text-center">
          <span className="material-symbols-outlined text-muted-foreground/50 text-2xl mb-1">search_off</span>
          <p className="text-xs text-muted-foreground">Không tìm thấy trang phù hợp.</p>
        </div>
      );
    }

    if (groupByDocument && sources.length > 0) {
      const docGroups = groupPagesByDocument(pageList);
      return (
        <div className="space-y-2">
          {docGroups.map((group) => {
            const isExpanded = isDocExpanded(group.id);
            const hasActivePage =
              (group.overviewPage && group.overviewPage.slug === currentSlug) ||
              group.articles.some((a) => a.slug === currentSlug) ||
              group.otherPages.some((o) => o.slug === currentSlug);

            return (
              <div key={group.key} className="mb-1">
                {/* Document folder header */}
                <div
                  onClick={() => toggleDocument(group.id)}
                  className={cn(
                    "flex items-center gap-1.5 px-2.5 py-1.5 mx-1 rounded-lg transition-colors cursor-pointer select-none text-xs",
                    hasActivePage
                      ? "bg-primary/10 text-primary font-medium"
                      : "hover:bg-accent/40 text-foreground"
                  )}
                  title={`Bấm để ${isExpanded ? "thu gọn" : "mở rộng"} (${group.total} trang)`}
                >
                  <button
                    type="button"
                    className="p-0.5 text-muted-foreground hover:text-foreground transition-colors shrink-0"
                    onClick={(e) => {
                      e.stopPropagation();
                      toggleDocument(group.id);
                    }}
                  >
                    <span className="material-symbols-outlined text-xs">
                      {isExpanded ? "expand_more" : "chevron_right"}
                    </span>
                  </button>
                  <span
                    className="material-symbols-outlined text-primary/80 shrink-0"
                    style={{ fontSize: 15 }}
                  >
                    {group.id === "other" ? "folder" : "description"}
                  </span>
                  <span className="flex-1 truncate font-medium text-[11px]" title={group.title}>
                    {group.title}
                  </span>
                  <span className="text-[10px] text-muted-foreground tabular-nums bg-muted px-1.5 py-0.5 rounded-full shrink-0">
                    {group.total}
                  </span>
                </div>

                {/* Document articles list */}
                {isExpanded && (
                  <div className="ml-5 mt-0.5 space-y-0.5 border-l border-border/40 pl-1.5">
                    {group.overviewPage && (
                      <div className="mb-0.5">
                        {renderPageItem(group.overviewPage, "📖 Tổng quan văn bản")}
                      </div>
                    )}
                    {group.articles.map((page) => {
                      const shortTitle = page.title.split(" - ")[0];
                      return renderPageItem(page, shortTitle);
                    })}
                    {group.otherPages.map((page) => renderPageItem(page))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      );
    }

    // Flat list mode with numeric sort
    const sorted = [...pageList].sort(naturalSortPages);
    return (
      <div className="space-y-0.5">
        {sorted.map((page) => renderPageItem(page))}
      </div>
    );
  };

  if (collapsed) {
    return (
      <div className="w-10 border-r border-border bg-card/30 flex flex-col items-center pt-4 gap-3 shrink-0">
        <button
          onClick={() => setCollapsed(false)}
          className="text-muted-foreground hover:text-foreground transition-colors"
          title="Expand page tree"
        >
          <span className="material-symbols-outlined text-base">left_panel_open</span>
        </button>
      </div>
    );
  }

  return (
    <div className="w-64 xl:w-72 shrink-0 border-r border-border bg-card/30 flex flex-col overflow-hidden">
      {/* === PAGES SECTION === */}
      <div className="flex flex-col min-h-0" style={{ flex: sourcesCollapsed ? "1 1 auto" : "1 1 58%" }}>
        {/* Header */}
        <div className="flex items-center gap-2 px-4 py-3 border-b border-border">
          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex-1">
            Pages
          </span>
          <span className="text-xs text-muted-foreground tabular-nums bg-muted rounded-md px-1.5 py-0.5">
            {filtered.length} / {totalCount}
          </span>
          <button
            onClick={() => setCollapsed(true)}
            className="text-muted-foreground hover:text-foreground transition-colors"
            title="Collapse"
          >
            <span className="material-symbols-outlined text-base">left_panel_close</span>
          </button>
        </div>

        {/* Search & Filters Toolbar */}
        <div className="px-3 py-2.5 border-b border-border space-y-2 bg-muted/15">
          {/* Search Input */}
          <div className="flex items-center gap-2 bg-background border border-border rounded-lg px-2.5 py-1.5 focus-within:border-primary/50 transition-colors shadow-xs">
            <span className="material-symbols-outlined text-sm text-muted-foreground">
              search
            </span>
            <input
              type="text"
              placeholder="Tìm điều, từ khóa (vd: 12, xử phạt)..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="flex-1 text-xs bg-transparent outline-none text-foreground placeholder:text-muted-foreground"
            />
            {search && (
              <button
                onClick={() => setSearch("")}
                className="text-muted-foreground hover:text-foreground"
                title="Xóa tìm kiếm"
              >
                <span className="material-symbols-outlined text-sm">close</span>
              </button>
            )}
          </div>

          {/* Document filter dropdown (when sources exist) */}
          {sources.length > 0 && (
            <div className="relative">
              <select
                value={selectedSourceId || ""}
                onChange={(e) => setSelectedSourceId(e.target.value || null)}
                className="w-full text-xs bg-background border border-border rounded-md px-2 py-1.5 text-foreground focus:outline-none focus:border-primary/50 pr-7 appearance-none cursor-pointer truncate"
                title="Lọc theo tài liệu / văn bản"
              >
                <option value="">📂 Tất cả văn bản ({totalCount})</option>
                {sourceStats.sources.map((s) => (
                  <option key={s.id} value={s.id}>
                    📄 {s.title} ({s.count})
                  </option>
                ))}
                {sourceStats.otherCount > 0 && (
                  <option value="other">
                    📄 Khác / Chưa phân loại ({sourceStats.otherCount})
                  </option>
                )}
              </select>
              <span className="material-symbols-outlined absolute right-2 top-1/2 -translate-y-1/2 text-xs text-muted-foreground pointer-events-none">
                expand_more
              </span>
            </div>
          )}

          {/* Quick Category Filters & Group Mode Toggle */}
          <div className="flex items-center justify-between gap-1 pt-0.5">
            {/* Filter pills */}
            <div className="flex items-center gap-1 overflow-x-auto custom-scrollbar pb-0.5">
              <button
                type="button"
                onClick={() => setCategoryFilter("all")}
                className={cn(
                  "px-2 py-0.5 text-[10px] rounded-full transition-colors shrink-0",
                  categoryFilter === "all"
                    ? "bg-primary text-primary-foreground font-semibold"
                    : "bg-muted text-muted-foreground hover:text-foreground hover:bg-muted/80"
                )}
              >
                Tất cả
              </button>
              <button
                type="button"
                onClick={() => setCategoryFilter("articles")}
                className={cn(
                  "px-2 py-0.5 text-[10px] rounded-full transition-colors shrink-0",
                  categoryFilter === "articles"
                    ? "bg-primary text-primary-foreground font-semibold"
                    : "bg-muted text-muted-foreground hover:text-foreground hover:bg-muted/80"
                )}
              >
                Điều luật ({sourceStats.articlesCount})
              </button>
              <button
                type="button"
                onClick={() => setCategoryFilter("overview")}
                className={cn(
                  "px-2 py-0.5 text-[10px] rounded-full transition-colors shrink-0",
                  categoryFilter === "overview"
                    ? "bg-primary text-primary-foreground font-semibold"
                    : "bg-muted text-muted-foreground hover:text-foreground hover:bg-muted/80"
                )}
              >
                Tổng quan ({sourceStats.overviewsCount})
              </button>
            </div>

            {/* Group mode toggle button */}
            <button
              type="button"
              onClick={() => setGroupByDocument(!groupByDocument)}
              className={cn(
                "p-1 rounded text-muted-foreground hover:text-foreground transition-colors shrink-0 ml-auto",
                groupByDocument ? "text-primary bg-primary/10" : "hover:bg-muted"
              )}
              title={
                groupByDocument
                  ? "Đang gom theo văn bản (Bấm để chuyển sang danh sách phẳng)"
                  : "Đang xem danh sách phẳng (Bấm để gom theo văn bản)"
              }
            >
              <span className="material-symbols-outlined text-sm">
                {groupByDocument ? "account_tree" : "format_list_bulleted"}
              </span>
            </button>
          </div>

          {/* Active filter counter & reset button */}
          {(selectedSourceId || search || categoryFilter !== "all") && (
            <div className="flex items-center justify-between text-[11px] text-muted-foreground pt-1 border-t border-border/40">
              <span className="truncate">
                Tìm thấy <strong className="text-foreground font-semibold">{filtered.length}</strong> kết quả
              </span>
              <button
                type="button"
                onClick={() => {
                  setSearch("");
                  setSelectedSourceId(null);
                  setCategoryFilter("all");
                }}
                className="text-primary hover:underline text-[10px] font-medium shrink-0 ml-1 cursor-pointer"
              >
                Đặt lại
              </button>
            </div>
          )}
        </div>

        {/* Tree List */}
        <div className="flex-1 overflow-y-auto py-2">
          {loading ? (
            <div className="px-3 space-y-2 mt-1">
              {Array.from({ length: 6 }).map((_, i) => (
                <div
                  key={i}
                  className="h-7 rounded-md bg-muted animate-pulse"
                  style={{ opacity: 1 - i * 0.12 }}
                />
              ))}
            </div>
          ) : groupByScope ? (
            scopeGrouped.length === 0 ? (
              <div className="px-4 py-6 text-center">
                <span className="material-symbols-outlined text-muted-foreground/40 text-2xl mb-1">search_off</span>
                <p className="text-xs text-muted-foreground">Không tìm thấy bài viết nào.</p>
              </div>
            ) : (
              scopeGrouped.map((bucket) => {
                const scopeExpanded = expandedScopes.has(bucket.key);
                const isActive = activeScopeKey === bucket.key;
                const scopeHref =
                  bucket.scope_type === "global"
                    ? "/wiki"
                    : bucket.scope_id
                      ? `/wiki?scope_type=${bucket.scope_type}&scope_id=${bucket.scope_id}`
                      : `/wiki?scope_type=${bucket.scope_type}`;
                return (
                  <div key={bucket.key} className="mb-2">
                    <div
                      className={cn(
                        "flex items-center gap-1 px-1 transition-colors rounded-md",
                        isActive ? "bg-accent/50" : "hover:bg-accent/30",
                      )}
                    >
                      <button
                        onClick={() => toggleScope(bucket.key)}
                        className="shrink-0 p-1 text-muted-foreground hover:text-foreground transition-colors"
                        title={scopeExpanded ? "Collapse" : "Expand"}
                      >
                        <span className="material-symbols-outlined text-xs">
                          {scopeExpanded ? "expand_more" : "chevron_right"}
                        </span>
                      </button>
                      <Link
                        href={scopeHref}
                        className="flex-1 flex items-center gap-2 py-1.5 min-w-0 text-left"
                        title={`Open ${bucket.label} wiki`}
                      >
                        <span
                          className="material-symbols-outlined text-xs text-muted-foreground"
                          style={{ fontSize: 13 }}
                        >
                          {SCOPE_ICONS[bucket.scope_type] ?? "tune"}
                        </span>
                        <span
                          className={cn(
                            "text-xs font-semibold uppercase tracking-wide flex-1 truncate",
                            isActive ? "text-primary" : "text-foreground",
                          )}
                        >
                          {bucket.label}
                        </span>
                        <span className="text-xs text-muted-foreground tabular-nums">
                          {bucket.total}
                        </span>
                      </Link>
                      {(() => {
                        if (!onCreatePage || !getCreateModeForScope) return null;
                        const mode = getCreateModeForScope({
                          scope_type: bucket.scope_type,
                          scope_id: bucket.scope_id ?? null,
                        });
                        if (!mode) return null;
                        return (
                          <button
                            type="button"
                            onClick={(e) => {
                              e.preventDefault();
                              e.stopPropagation();
                              onCreatePage({
                                scope_type: bucket.scope_type,
                                scope_id: bucket.scope_id ?? null,
                              });
                            }}
                            className="shrink-0 mr-1 w-5 h-5 flex items-center justify-center rounded text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
                            title={
                              mode === "direct"
                                ? `New page in ${bucket.label}`
                                : `Propose new page in ${bucket.label}`
                            }
                            aria-label={`Create page in ${bucket.label}`}
                          >
                            <span className="material-symbols-outlined" style={{ fontSize: 14 }}>
                              add
                            </span>
                          </button>
                        );
                      })()}
                    </div>
                    {scopeExpanded && (
                      <div className="ml-3 mt-1 border-l border-border/30 pl-1">
                        {renderPagesList(bucket.pages)}
                      </div>
                    )}
                  </div>
                );
              })
            )
          ) : (
            renderPagesList(filtered)
          )}
        </div>
      </div>

      {/* === SOURCES SECTION === */}
      <div
        className="flex flex-col min-h-0 border-t border-border"
        style={{ flex: sourcesCollapsed ? "0 0 auto" : "1 1 42%" }}
      >
        {/* Sources header */}
        <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border">
          <button
            onClick={() => setSourcesCollapsed(!sourcesCollapsed)}
            className="text-muted-foreground hover:text-foreground transition-colors"
          >
            <span className="material-symbols-outlined text-xs">
              {sourcesCollapsed ? "chevron_right" : "expand_more"}
            </span>
          </button>
          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex-1">
            Sources
          </span>
          <span className="text-xs text-muted-foreground tabular-nums bg-muted rounded-md px-1.5 py-0.5">
            {sources.length}
          </span>
        </div>

        {/* Sources list */}
        {!sourcesCollapsed && (
          <div className="flex-1 overflow-y-auto py-1">
            {sourcesLoading ? (
              <div className="px-3 space-y-2 mt-1">
                {Array.from({ length: 3 }).map((_, i) => (
                  <div key={i} className="h-6 rounded-md bg-muted animate-pulse" style={{ opacity: 1 - i * 0.2 }} />
                ))}
              </div>
            ) : sources.length === 0 ? (
              <p className="text-[10px] text-muted-foreground px-4 py-2 italic">No sources uploaded.</p>
            ) : (
              <div className="space-y-0.5">
                {sources.map((src) => {
                  const isFiltered = selectedSourceId === src.id;
                  return (
                    <div
                      key={src.id}
                      className={cn(
                        "group flex items-center gap-1.5 px-2 py-1 mx-1 text-xs rounded-lg transition-all",
                        currentSlug === `source/${src.id}`
                          ? "bg-primary/10 text-primary font-medium"
                          : isFiltered
                            ? "bg-accent text-accent-foreground font-medium"
                            : "text-muted-foreground hover:text-foreground hover:bg-accent/50",
                      )}
                    >
                      <Link
                        href={`/wiki/source/${src.id}`}
                        className="flex-1 flex items-center gap-2 min-w-0"
                        title={src.title || src.file_name}
                      >
                        <span className="material-symbols-outlined shrink-0" style={{ fontSize: 14 }}>
                          {src.source_type === "url" ? "link" : "description"}
                        </span>
                        <span className="truncate">{src.title || src.file_name || "Untitled"}</span>
                      </Link>
                      <button
                        type="button"
                        onClick={() => {
                          setSelectedSourceId(selectedSourceId === src.id ? null : src.id);
                        }}
                        className={cn(
                          "p-1 rounded transition-colors shrink-0",
                          isFiltered
                            ? "text-primary bg-primary/20"
                            : "opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-foreground hover:bg-accent"
                        )}
                        title={isFiltered ? "Hủy lọc tài liệu này" : "Lọc bài viết theo tài liệu này"}
                      >
                        <span className="material-symbols-outlined text-[13px]">
                          filter_alt
                        </span>
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
