"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { WikiPageSummary } from "@/types/wiki";
import { useI18n } from "@/lib/i18n";
import {
  wikiStore,
  useWikiStore,
  getCachedPages,
  setCachedPages,
  removeCachedPage,
  getCachedSources,
  setCachedSources,
  getDocForPage,
  computeSourceStats,
  displaySourceTitle,
  WikiSourceItem,
} from "@/lib/wiki-store";
import { parseSourceLegalMeta } from "@/components/knowledge/knowledge-table/utils";

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

const STATUS_DOT: Record<string, string> = {
  seed: "bg-[#a8977e]",
  developing: "bg-[#d4872e]",
  mature: "bg-[#2e8b8b]",
  evergreen: "bg-[#3a8a3f]",
};

const CATEGORY_OPTIONS = [
  { id: "all", label: "Tất cả" },
  { id: "articles", label: "Điều" },
  { id: "overview", label: "Tổng quan" },
] as const;

/** Normalizes Vietnamese diacritics / tones for accent-insensitive search */
export function removeVietnameseTones(str: string): string {
  return str
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
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

function isArticlePage(p: WikiPageSummary): boolean {
  return p.title.startsWith("Điều ");
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
  /** When true, group pages by scope (headers only shown when more than one scope is visible). */
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
  const { t } = useI18n();

  const effectivePagesUrl = pagesUrl || "/api/wiki/pages";
  const initialPages = React.useMemo(() => getCachedPages(effectivePagesUrl), [effectivePagesUrl]);
  const [pages, setPages] = React.useState<WikiPageSummary[]>(initialPages || []);
  const [loading, setLoading] = React.useState(!initialPages || initialPages.length === 0);

  const initialSources = React.useMemo(() => getCachedSources(), []);
  const [sources, setSources] = React.useState<WikiSourceItem[]>(initialSources || []);

  const [collapsed, setCollapsed] = React.useState(false);

  // Global Wiki Store subscription
  const {
    categoryFilter,
    groupByDocument,
    search,
    expandedDocuments,
    expandedScopes,
    setCategoryFilter,
    setGroupByDocument,
    setSearch,
    setExpandedDocuments,
    setExpandedScopes,
    resetFilters,
  } = useWikiStore();

  // Two-stage delete
  const [armedSlug, setArmedSlug] = React.useState<string | null>(null);
  const [deletingSlug, setDeletingSlug] = React.useState<string | null>(null);

  const debouncedSearch = useDebounce(search, 150);

  const treeScrollRef = React.useRef<HTMLDivElement>(null);
  const searchInputRef = React.useRef<HTMLInputElement>(null);

  // Restore scroll position on mount
  React.useEffect(() => {
    if (treeScrollRef.current && wikiStore.sidebarScrollTop > 0) {
      treeScrollRef.current.scrollTop = wikiStore.sidebarScrollTop;
    }
  }, []);

  const handleTreeScroll = React.useCallback(() => {
    if (treeScrollRef.current) {
      wikiStore.sidebarScrollTop = treeScrollRef.current.scrollTop;
    }
  }, []);

  const loadPages = React.useCallback(() => {
    const url = pagesUrl || "/api/wiki/pages";
    api<WikiPageSummary[]>(url)
      .then((data) => {
        const list = Array.isArray(data) ? data : [];
        setPages(list);
        setCachedPages(url, list);
      })
      .catch(() => {
        if (!getCachedPages(url)) setPages([]);
      })
      .finally(() => setLoading(false));
  }, [pagesUrl]);

  React.useEffect(() => {
    loadPages();
  }, [loadPages]);

  React.useEffect(() => {
    api<{ items: WikiSourceItem[] }>("/api/sources?status=ready&page_size=1000")
      .then((data) => {
        const items = data.items || [];
        setSources(items);
        setCachedSources(items);
      })
      .catch(() => {
        if (!initialSources) setSources([]);
      });
  }, [initialSources]);

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
      removeCachedPage(slug);
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
    (p: WikiPageSummary) => getDocForPage(p, sources),
    [sources]
  );

  /** Accent-insensitive and multi-field search matcher */
  const matchesSearch = React.useCallback(
    (p: WikiPageSummary, query: string, docTitle?: string): boolean => {
      if (!query) return true;
      const rawQ = query.trim().toLowerCase();
      const normQ = removeVietnameseTones(rawQ);

      const fields = [p.title, p.slug, p.summary, docTitle];
      for (const f of fields) {
        if (!f) continue;
        const raw = f.toLowerCase();
        if (raw.includes(rawQ) || removeVietnameseTones(raw).includes(normQ)) return true;
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
    const aIsOverview = !isArticlePage(a);
    const bIsOverview = !isArticlePage(b);
    if (aIsOverview && !bIsOverview) return -1;
    if (!aIsOverview && bIsOverview) return 1;
    return a.title.localeCompare(b.title, "vi", { numeric: true });
  }, []);

  /** Filtered list of pages based on Search and Category */
  const filtered = React.useMemo(() => {
    return pages.filter((p) => {
      if (p.page_type === "index" || p.page_type === "log" || p.page_type === "hot") {
        return false;
      }

      const isArticle = isArticlePage(p);
      if (categoryFilter === "articles" && !isArticle) return false;
      if (categoryFilter === "overview" && isArticle) return false;

      if (debouncedSearch) {
        const doc = getDocInfoForPage(p);
        if (!matchesSearch(p, debouncedSearch, doc?.title || doc?.file_name)) {
          return false;
        }
      }

      return true;
    });
  }, [pages, debouncedSearch, categoryFilter, getDocInfoForPage, matchesSearch]);

  const sourceStats = React.useMemo(() => computeSourceStats(pages, sources), [pages, sources]);
  const totalCount = sourceStats.totalCount;
  const categoryCounts: Record<(typeof CATEGORY_OPTIONS)[number]["id"], number> = {
    all: totalCount,
    articles: sourceStats.articlesCount,
    overview: sourceStats.overviewsCount,
  };

  const isFiltered = Boolean(debouncedSearch.trim() || categoryFilter !== "all");

  const currentSlug = activeSlug ?? pathname.replace(/^\/wiki\//, "");

  // Auto-expand the document folder corresponding to the active page
  React.useEffect(() => {
    if (!currentSlug || pages.length === 0) return;
    const activePage = pages.find((p) => p.slug === currentSlug);
    if (activePage) {
      const doc = getDocInfoForPage(activePage);
      const docKey = doc ? doc.id : "other";
      queueMicrotask(() => {
        setExpandedDocuments((prev) => {
          if (prev.has(docKey)) return prev;
          const next = new Set(prev);
          next.add(docKey);
          return next;
        });
      });
    }
  }, [currentSlug, pages, getDocInfoForPage, setExpandedDocuments]);

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
    source?: WikiSourceItem;
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
          title: displaySourceTitle(s),
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
          (!isArticlePage(p) && !targetGroup.overviewPage);

        if (isOverview && !targetGroup.overviewPage) {
          targetGroup.overviewPage = p;
        } else if (isArticlePage(p)) {
          targetGroup.articles.push(p);
        } else {
          targetGroup.otherPages.push(p);
        }
      }

      if (otherGroup.total > 0) {
        groupMap.set("other", otherGroup);
      }

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

  const activeScopeKey = React.useMemo(() => {
    if (!activeScope) return null;
    return activeScope.scope_id ? `${activeScope.scope_type}:${activeScope.scope_id}` : activeScope.scope_type;
  }, [activeScope]);

  // Scope headers are noise when only one scope is visible — render its pages directly.
  const showScopeHeaders = groupByScope && scopeGrouped.length > 1;

  React.useEffect(() => {
    if (!showScopeHeaders) return;
    queueMicrotask(() => {
      setExpandedScopes((prev) => {
        const next = new Set(prev);
        next.add("global");
        if (activeScopeKey) next.add(activeScopeKey);
        if (activeSlug) {
          for (const b of scopeGrouped) {
            if (b.pages.some((p) => p.slug === activeSlug)) {
              next.add(b.key);
            }
          }
        }
        return next;
      });
    });
  }, [showScopeHeaders, scopeGrouped, activeScopeKey, activeSlug, setExpandedScopes]);

  const toggleScope = (key: string) => {
    setExpandedScopes((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  // Auto-scroll active item into view
  React.useEffect(() => {
    if (!currentSlug || !treeScrollRef.current) return;
    const activeEl = treeScrollRef.current.querySelector(`[data-slug="${currentSlug}"]`);
    if (activeEl) {
      activeEl.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }, [currentSlug]);

  const handleNavClick = (e: React.MouseEvent, slug: string) => {
    if (onPageSelect && !e.ctrlKey && !e.metaKey && !e.shiftKey && e.button === 0) {
      e.preventDefault();
      onPageSelect(slug);
    }
  };

  // Renders one leaf row (page link + delete button)
  const renderPageItem = (
    page: WikiPageSummary,
    opts: { label?: string; overview?: boolean } = {},
  ) => {
    const isActive = page.slug === currentSlug;
    const isArmed = armedSlug === page.slug;
    const isDeleting = deletingSlug === page.slug;
    const linkSuffix = linkQueryParams
      ? linkQueryParams
      : page.scope_type && page.scope_type !== "global" && page.scope_id
        ? `?scopeType=${page.scope_type}&scopeId=${page.scope_id}`
        : "";

    return (
      <div
        key={pageKey(page)}
        data-slug={page.slug}
        className={cn(
          "group relative flex items-center rounded-md transition-colors",
          isActive ? "bg-primary/10" : "hover:bg-accent/60",
        )}
      >
        {isActive && <span className="absolute left-0 top-1 bottom-1 w-0.5 rounded-full bg-primary" />}
        <Link
          href={`/wiki/${page.slug}${linkSuffix}`}
          onClick={(e) => handleNavClick(e, page.slug)}
          className={cn(
            "flex-1 flex items-center gap-2 pl-2.5 pr-1 py-1 text-xs min-w-0",
            isActive ? "text-primary font-medium" : "text-muted-foreground hover:text-foreground",
          )}
          title={page.summary || page.title}
        >
          {opts.overview ? (
            <span className="material-symbols-outlined shrink-0 text-primary/80" style={{ fontSize: 14 }}>
              menu_book
            </span>
          ) : (
            <span className={cn("w-1.5 h-1.5 rounded-full shrink-0 opacity-70", STATUS_DOT[page.status || "seed"])} />
          )}
          <span className="truncate">{opts.label || page.title}</span>
        </Link>

        {isDeleting ? (
          <span className="material-symbols-outlined text-destructive animate-pulse mr-1.5" style={{ fontSize: 14 }}>
            progress_activity
          </span>
        ) : isArmed ? (
          <button
            onClick={(e) => {
              e.stopPropagation();
              handleDelete(page);
            }}
            className="shrink-0 mr-1 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-destructive text-destructive-foreground hover:bg-destructive/90 transition-colors cursor-pointer"
            title={`Bấm lần nữa để xóa "${page.title}"`}
          >
            Xóa?
          </button>
        ) : (
          <button
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              handleDelete(page);
            }}
            className="shrink-0 mr-1 p-0.5 rounded opacity-0 group-hover:opacity-100 focus-visible:opacity-100 text-muted-foreground hover:text-destructive transition-opacity cursor-pointer"
            title={`Xóa "${page.title}"`}
          >
            <span className="material-symbols-outlined" style={{ fontSize: 14 }}>delete</span>
          </button>
        )}
      </div>
    );
  };

  const renderEmpty = () => (
    <div className="px-4 py-10 text-center">
      <span className="material-symbols-outlined text-muted-foreground/40 text-2xl mb-1.5 block">
        search_off
      </span>
      <p className="text-xs text-foreground font-medium mb-0.5">{t("wiki.noPages")}</p>
      <p className="text-[11px] text-muted-foreground mb-3">{t("wiki.noPagesDesc")}</p>
      {isFiltered && (
        <button
          type="button"
          onClick={resetFilters}
          className="inline-flex items-center gap-1 px-2.5 py-1 text-[11px] font-medium rounded-md bg-primary/10 hover:bg-primary/20 text-primary transition-colors cursor-pointer"
        >
          <span className="material-symbols-outlined" style={{ fontSize: 13 }}>restart_alt</span>
          {t("wiki.reset")}
        </button>
      )}
    </div>
  );

  /** Renders a list of pages, either grouped by Document accordion or flat */
  const renderPagesList = (pageList: WikiPageSummary[]) => {
    if (pageList.length === 0) return renderEmpty();

    if (groupByDocument && sources.length > 0) {
      const docGroups = groupPagesByDocument(pageList);
      return (
        <div className="space-y-px">
          {docGroups.map((group) => {
            const isExpanded = isDocExpanded(group.id);
            const hasActivePage =
              group.overviewPage?.slug === currentSlug ||
              group.articles.some((a) => a.slug === currentSlug) ||
              group.otherPages.some((o) => o.slug === currentSlug);
            const legalMeta = group.source ? parseSourceLegalMeta(group.source) : null;
            const subtitle = legalMeta
              ? [legalMeta.docNumber, legalMeta.badgeLabel].filter(Boolean).join(" · ")
              : "Chưa gắn văn bản nguồn";

            return (
              <div key={group.key}>
                {/* Document folder header */}
                <div
                  className={cn(
                    "group flex items-start gap-1.5 pl-1 pr-1.5 py-1.5 rounded-md transition-colors",
                    hasActivePage && !isExpanded ? "bg-primary/5" : "hover:bg-accent/60",
                  )}
                >
                  <button
                    type="button"
                    onClick={() => toggleDocument(group.id)}
                    aria-expanded={isExpanded}
                    className="flex-1 flex items-start gap-1.5 min-w-0 text-left cursor-pointer"
                    title={group.title}
                  >
                    <span
                      className={cn(
                        "material-symbols-outlined shrink-0 text-muted-foreground/70 transition-transform mt-0.5",
                        isExpanded && "rotate-90",
                      )}
                      style={{ fontSize: 16 }}
                    >
                      chevron_right
                    </span>
                    <span
                      className="material-symbols-outlined shrink-0 mt-0.5"
                      style={{ fontSize: 15, color: legalMeta?.badgeColor }}
                    >
                      {group.id === "other" ? "folder" : legalMeta?.icon || "description"}
                    </span>
                    <span className="flex-1 min-w-0">
                      <span
                        className={cn(
                          "block truncate text-xs leading-5",
                          hasActivePage ? "text-primary font-semibold" : "text-foreground font-medium",
                        )}
                      >
                        {group.title}
                      </span>
                      <span className="block truncate text-[10px] leading-4 text-muted-foreground font-mono">
                        {subtitle}
                      </span>
                    </span>
                  </button>
                  {group.source && (
                    <Link
                      href={`/wiki/source/${group.source.id}`}
                      onClick={(e) => handleNavClick(e, `source/${group.source!.id}`)}
                      className="shrink-0 mt-0.5 p-0.5 rounded text-muted-foreground hover:text-primary opacity-0 group-hover:opacity-100 focus-visible:opacity-100 transition-opacity"
                      title="Mở văn bản gốc"
                    >
                      <span className="material-symbols-outlined" style={{ fontSize: 14 }}>open_in_new</span>
                    </Link>
                  )}
                  <span className="shrink-0 mt-0.5 text-[10px] text-muted-foreground tabular-nums min-w-5 text-right leading-5">
                    {group.total}
                  </span>
                </div>

                {/* Document articles list */}
                {isExpanded && (
                  <div className="ml-[18px] mb-1 pl-1.5 border-l border-border/60 space-y-px">
                    {group.overviewPage &&
                      renderPageItem(group.overviewPage, { label: "Tổng quan văn bản", overview: true })}
                    {group.articles.map((page) => renderPageItem(page, { label: page.title.split(" - ")[0] }))}
                    {group.otherPages.map((page) => renderPageItem(page))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      );
    }

    const sorted = [...pageList].sort(naturalSortPages);
    return <div className="space-y-px">{sorted.map((page) => renderPageItem(page))}</div>;
  };

  const renderScopeBuckets = () =>
    scopeGrouped.map((bucket) => {
      const scopeExpanded = expandedScopes.has(bucket.key);
      const isActive = activeScopeKey === bucket.key;
      const scopeHref =
        bucket.scope_type === "global"
          ? "/wiki"
          : bucket.scope_id
            ? `/wiki?scope_type=${bucket.scope_type}&scope_id=${bucket.scope_id}`
            : `/wiki?scope_type=${bucket.scope_type}`;
      const createMode =
        onCreatePage && getCreateModeForScope
          ? getCreateModeForScope({ scope_type: bucket.scope_type, scope_id: bucket.scope_id })
          : null;
      return (
        <div key={bucket.key} className="mb-2">
          <div
            className={cn(
              "flex items-center gap-1 pr-1 rounded-md transition-colors",
              isActive ? "bg-accent/50" : "hover:bg-accent/30",
            )}
          >
            <button
              onClick={() => toggleScope(bucket.key)}
              className="shrink-0 p-1 text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
              title={scopeExpanded ? "Thu gọn" : "Mở rộng"}
            >
              <span
                className={cn("material-symbols-outlined transition-transform block", scopeExpanded && "rotate-90")}
                style={{ fontSize: 16 }}
              >
                chevron_right
              </span>
            </button>
            <Link href={scopeHref} className="flex-1 flex items-center gap-2 py-1.5 min-w-0">
              <span className="material-symbols-outlined text-muted-foreground" style={{ fontSize: 14 }}>
                {SCOPE_ICONS[bucket.scope_type] ?? "tune"}
              </span>
              <span
                className={cn(
                  "text-[11px] font-semibold uppercase tracking-wide flex-1 truncate",
                  isActive ? "text-primary" : "text-foreground",
                )}
              >
                {bucket.label}
              </span>
              <span className="text-[10px] text-muted-foreground tabular-nums">{bucket.total}</span>
            </Link>
            {createMode && (
              <button
                type="button"
                onClick={() => onCreatePage!({ scope_type: bucket.scope_type, scope_id: bucket.scope_id })}
                className="shrink-0 w-5 h-5 flex items-center justify-center rounded text-muted-foreground hover:text-foreground hover:bg-accent transition-colors cursor-pointer"
                title={createMode === "direct" ? `Tạo trang trong ${bucket.label}` : `Đề xuất trang trong ${bucket.label}`}
                aria-label={`Tạo trang trong ${bucket.label}`}
              >
                <span className="material-symbols-outlined" style={{ fontSize: 14 }}>add</span>
              </button>
            )}
          </div>
          {scopeExpanded && <div className="ml-2 mt-0.5">{renderPagesList(bucket.pages)}</div>}
        </div>
      );
    });

  if (collapsed) {
    return (
      <div className="w-11 border-r border-border bg-card/30 flex flex-col items-center pt-3 gap-1 shrink-0">
        <button
          onClick={() => setCollapsed(false)}
          className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent/60 transition-colors cursor-pointer"
          title="Mở danh mục"
        >
          <span className="material-symbols-outlined" style={{ fontSize: 18 }}>left_panel_open</span>
        </button>
        <button
          onClick={() => {
            setCollapsed(false);
            requestAnimationFrame(() => searchInputRef.current?.focus());
          }}
          className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent/60 transition-colors cursor-pointer"
          title="Tìm trong danh mục"
        >
          <span className="material-symbols-outlined" style={{ fontSize: 18 }}>search</span>
        </button>
      </div>
    );
  }

  const hasExpandedDocs = groupByDocument && expandedDocuments.size > 0 && !debouncedSearch.trim();

  return (
    <aside className="w-64 xl:w-72 shrink-0 border-r border-border bg-card/30 flex flex-col overflow-hidden">
      {/* Toolbar: search + category + status */}
      <div className="px-3 pt-3 pb-2 space-y-2 border-b border-border">
        <div className="flex items-center gap-1">
          <div className="flex-1 flex items-center gap-1.5 bg-background border border-border rounded-lg px-2 h-8 focus-within:border-primary/60 focus-within:ring-2 focus-within:ring-primary/10 transition-all">
            <span className="material-symbols-outlined text-muted-foreground/70 shrink-0" style={{ fontSize: 16 }}>
              search
            </span>
            <input
              ref={searchInputRef}
              type="text"
              placeholder={t("wiki.searchPlaceholder")}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Escape") setSearch("");
              }}
              className="flex-1 text-xs bg-transparent outline-none text-foreground placeholder:text-muted-foreground/60 min-w-0"
            />
            {search && (
              <button
                type="button"
                onClick={() => setSearch("")}
                className="text-muted-foreground hover:text-foreground rounded transition-colors shrink-0 cursor-pointer"
                title="Xóa tìm kiếm"
              >
                <span className="material-symbols-outlined block" style={{ fontSize: 14 }}>close</span>
              </button>
            )}
          </div>
          <button
            type="button"
            onClick={() => setCollapsed(true)}
            className="shrink-0 p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent/60 transition-colors cursor-pointer"
            title="Thu gọn danh mục"
          >
            <span className="material-symbols-outlined block" style={{ fontSize: 16 }}>left_panel_close</span>
          </button>
        </div>

        {/* Category segmented control */}
        <div className="grid grid-cols-3 p-0.5 bg-muted/60 rounded-lg" role="tablist">
          {CATEGORY_OPTIONS.map((opt) => {
            const active = categoryFilter === opt.id;
            return (
              <button
                key={opt.id}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => setCategoryFilter(opt.id)}
                className={cn(
                  "flex items-center justify-center gap-1 px-1 py-1 rounded-md text-[11px] transition-all cursor-pointer min-w-0",
                  active
                    ? "bg-background text-foreground font-semibold shadow-xs"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                <span className="truncate">{opt.label}</span>
                <span className="text-[10px] tabular-nums opacity-60">{categoryCounts[opt.id]}</span>
              </button>
            );
          })}
        </div>

        {/* Status line */}
        <div className="flex items-center gap-2 h-5 text-[11px] text-muted-foreground">
          <span className="flex-1 truncate tabular-nums">
            {isFiltered ? (
              <>
                <span className="text-primary font-semibold">{filtered.length}</span> / {totalCount} trang
              </>
            ) : (
              <>
                {totalCount} trang · {sources.length} văn bản
              </>
            )}
          </span>
          {isFiltered && (
            <button
              type="button"
              onClick={resetFilters}
              className="text-primary hover:underline font-medium cursor-pointer"
            >
              Bỏ lọc
            </button>
          )}
          {hasExpandedDocs && (
            <button
              type="button"
              onClick={() => setExpandedDocuments(new Set())}
              className="p-0.5 rounded hover:bg-accent/60 hover:text-foreground transition-colors cursor-pointer"
              title="Thu gọn tất cả văn bản"
            >
              <span className="material-symbols-outlined block" style={{ fontSize: 15 }}>unfold_less</span>
            </button>
          )}
          <button
            type="button"
            onClick={() => setGroupByDocument(!groupByDocument)}
            className="p-0.5 rounded hover:bg-accent/60 hover:text-foreground transition-colors cursor-pointer"
            title={groupByDocument ? "Xem danh sách phẳng" : "Gom theo văn bản"}
          >
            <span className="material-symbols-outlined block" style={{ fontSize: 15 }}>
              {groupByDocument ? "format_list_bulleted" : "account_tree"}
            </span>
          </button>
        </div>
      </div>

      {/* Tree List */}
      <div ref={treeScrollRef} onScroll={handleTreeScroll} className="flex-1 overflow-y-auto px-1.5 py-1.5">
        {loading ? (
          <div className="px-1.5 space-y-2 mt-1">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="h-8 rounded-md bg-muted animate-pulse" style={{ opacity: 1 - i * 0.1 }} />
            ))}
          </div>
        ) : !groupByScope ? (
          renderPagesList(filtered)
        ) : showScopeHeaders ? (
          renderScopeBuckets()
        ) : (
          renderPagesList(scopeGrouped[0]?.pages ?? [])
        )}
      </div>
    </aside>
  );
}
