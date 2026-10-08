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
  displaySourceTitle,
  WikiSourceItem,
} from "@/lib/wiki-store";
import { wikiTypeGroupLabel } from "@/components/wiki/wiki-type-badge";

const STATUS_DOT: Record<string, string> = {
  seed: "bg-[#a8977e]",
  developing: "bg-[#d4872e]",
  mature: "bg-[#2e8b8b]",
  evergreen: "bg-[#3a8a3f]",
};

/** Normalizes Vietnamese diacritics / tones for accent-insensitive search */
export function removeVietnameseTones(str: string): string {
  return str
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/đ/g, "d")
    .replace(/Đ/g, "d")
    .toLowerCase();
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
  onSearch,
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
  /** Opens the global search dialog (header search icon). */
  onSearch?: () => void;
}) {
  const pathname = usePathname();
  const { t } = useI18n();

  const effectivePagesUrl = pagesUrl || "/api/wiki/pages";
  const initialPages = React.useMemo(() => getCachedPages(effectivePagesUrl), [effectivePagesUrl]);
  const [pages, setPages] = React.useState<WikiPageSummary[]>(initialPages || []);
  const [loading, setLoading] = React.useState(!initialPages || initialPages.length === 0);

  const initialSources = React.useMemo(() => getCachedSources(), []);
  const [sources, setSources] = React.useState<WikiSourceItem[]>(initialSources || []);

  // Global Wiki Store subscription
  const {
    search,
    setSearch,
    docFilter,
    setDocFilter,
    collapsedSections,
    toggleSection,
    treeCollapsed: collapsed,
    setTreeCollapsed: setCollapsed,
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

  const byTitle = (a: WikiPageSummary, b: WikiPageSummary) => a.title.localeCompare(b.title, "vi", { numeric: true });

  /** Pages eligible for the tree (system pages hidden; project pages hidden in scope mode). */
  const basePages = React.useMemo(
    () =>
      pages.filter(
        (p) =>
          p.page_type !== "index" &&
          p.page_type !== "log" &&
          p.page_type !== "hot" &&
          !(groupByScope && (p.scope_type || "global") === "project"),
      ),
    [pages, groupByScope],
  );

  const docIdOf = React.useCallback((p: WikiPageSummary) => getDocInfoForPage(p)?.id ?? "other", [getDocInfoForPage]);

  /** Documents that own at least one page — options for the document select. */
  const docOptions = React.useMemo(() => {
    const counts = new Map<string, number>();
    for (const p of basePages) {
      const k = docIdOf(p);
      counts.set(k, (counts.get(k) ?? 0) + 1);
    }
    const out = sources
      .filter((s) => counts.has(s.id))
      .map((s) => ({ id: s.id, title: displaySourceTitle(s), count: counts.get(s.id) ?? 0 }));
    if (counts.has("other")) {
      out.push({ id: "other", title: "Tài liệu khác / Kiến thức chung", count: counts.get("other") ?? 0 });
    }
    return out;
  }, [basePages, sources, docIdOf]);

  // Ignore a stale document filter (source removed or not visible to this user)
  const effectiveDocFilter = docOptions.some((d) => d.id === docFilter) ? docFilter : "";

  const visible = React.useMemo(
    () =>
      basePages.filter((p) => {
        if (effectiveDocFilter && docIdOf(p) !== effectiveDocFilter) return false;
        if (debouncedSearch) {
          const doc = getDocInfoForPage(p);
          if (!matchesSearch(p, debouncedSearch, doc?.title || doc?.file_name)) return false;
        }
        return true;
      }),
    [basePages, effectiveDocFilter, debouncedSearch, docIdOf, getDocInfoForPage, matchesSearch],
  );

  const isFiltered = Boolean(debouncedSearch.trim() || effectiveDocFilter);
  const currentSlug = activeSlug ?? pathname.replace(/^\/wiki\//, "");

  type TreeItem = { page: WikiPageSummary; overview?: boolean };
  type TreeSection = { key: string; label: string; items: TreeItem[]; sourceId?: string };

  /**
   * One document selected → sections by kind (overview / articles / other types).
   * All documents → one section per document (overview first, then articles in natural order).
   */
  const sections = React.useMemo<TreeSection[]>(() => {
    const byDoc = new Map<string, WikiPageSummary[]>();
    for (const p of visible) {
      const k = docIdOf(p);
      if (!byDoc.has(k)) byDoc.set(k, []);
      byDoc.get(k)!.push(p);
    }

    if (effectiveDocFilter || byDoc.size <= 1) {
      const overview: WikiPageSummary[] = [];
      const articles: WikiPageSummary[] = [];
      const other = new Map<string, WikiPageSummary[]>();
      for (const p of visible) {
        if (isArticlePage(p)) articles.push(p);
        else if (["summary", "overview", "source"].includes(p.page_type)) overview.push(p);
        else {
          const label = wikiTypeGroupLabel(p.page_type);
          if (!other.has(label)) other.set(label, []);
          other.get(label)!.push(p);
        }
      }
      const out: TreeSection[] = [];
      if (overview.length) {
        out.push({
          key: "t:overview",
          label: "Tổng quan văn bản",
          items: overview.sort(byTitle).map((page) => ({ page, overview: true })),
        });
      }
      if (articles.length) {
        out.push({ key: "t:articles", label: "Điều khoản", items: articles.sort(byTitle).map((page) => ({ page })) });
      }
      for (const [label, list] of [...other].sort((a, b) => a[0].localeCompare(b[0], "vi"))) {
        out.push({ key: `t:${label}`, label, items: list.sort(byTitle).map((page) => ({ page })) });
      }
      return out;
    }

    const order = docOptions.map((d) => d.id);
    return [...byDoc]
      .sort((a, b) => order.indexOf(a[0]) - order.indexOf(b[0]))
      .map(([id, list]) => {
        const overview = list.filter((p) => !isArticlePage(p)).sort(byTitle);
        const articles = list.filter(isArticlePage).sort(byTitle);
        return {
          key: `d:${id}`,
          label: docOptions.find((d) => d.id === id)?.title ?? id,
          sourceId: id === "other" ? undefined : id,
          items: [...overview.map((page) => ({ page, overview: true })), ...articles.map((page) => ({ page }))],
        };
      });
  }, [visible, effectiveDocFilter, docIdOf, docOptions]);

  const isSectionOpen = (key: string) => Boolean(debouncedSearch.trim()) || !collapsedSections.has(key);

  // Keep the section holding the active page open
  React.useEffect(() => {
    const sec = sections.find((s) => s.items.some((i) => i.page.slug === currentSlug));
    if (sec && wikiStore.collapsedSections.has(sec.key)) queueMicrotask(() => toggleSection(sec.key));
  }, [sections, currentSlug, toggleSection]);

  const createScope = activeScope ?? { scope_type: "global", scope_id: null };
  const createMode = onCreatePage && getCreateModeForScope ? getCreateModeForScope(createScope) : null;

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

  const ICON_BTN =
    "shrink-0 p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent/60 transition-colors cursor-pointer";

  if (collapsed) {
    return (
      <div className="w-11 border-r border-border bg-card/30 flex flex-col items-center pt-3 gap-1 shrink-0">
        <button onClick={() => setCollapsed(false)} className={cn(ICON_BTN, "p-1.5")} title="Mở danh mục">
          <span className="material-symbols-outlined block" style={{ fontSize: 18 }}>left_panel_open</span>
        </button>
        <button
          onClick={() => {
            setCollapsed(false);
            requestAnimationFrame(() => searchInputRef.current?.focus());
          }}
          className={cn(ICON_BTN, "p-1.5")}
          title="Lọc trang"
        >
          <span className="material-symbols-outlined block" style={{ fontSize: 18 }}>filter_list</span>
        </button>
      </div>
    );
  }

  const selectedDoc = docOptions.find((d) => d.id === effectiveDocFilter);

  return (
    <aside className="w-64 xl:w-72 shrink-0 border-r border-border bg-card/30 flex flex-col overflow-hidden">
      <div className="px-3 pt-3 pb-2.5 space-y-2 border-b border-border">
        {/* Header: back to index + quick actions */}
        <div className="flex items-center gap-0.5">
          <Link
            href="/wiki"
            className="mr-auto inline-flex items-center gap-1 px-1 py-0.5 rounded-md text-sm font-semibold text-foreground hover:text-primary transition-colors"
            title="Về trang Wiki"
          >
            <span className="material-symbols-outlined" style={{ fontSize: 18 }}>arrow_back</span>
            Wiki
          </Link>
          {onSearch && (
            <button type="button" onClick={onSearch} className={ICON_BTN} title="Tìm kiếm (Ctrl+K)">
              <span className="material-symbols-outlined block" style={{ fontSize: 17 }}>search</span>
            </button>
          )}
          <Link href="/wiki/graph" className={ICON_BTN} title="Xem sơ đồ">
            <span className="material-symbols-outlined block" style={{ fontSize: 17 }}>hub</span>
          </Link>
          {createMode && (
            <button
              type="button"
              onClick={() => onCreatePage!(createScope)}
              className={ICON_BTN}
              title={createMode === "direct" ? "Tạo trang mới" : "Đề xuất trang mới (cần duyệt)"}
            >
              <span className="material-symbols-outlined block" style={{ fontSize: 17 }}>add</span>
            </button>
          )}
          <span
            className="mx-1 px-1.5 py-px rounded-full bg-muted text-[11px] font-medium text-muted-foreground tabular-nums"
            title={isFiltered ? `${visible.length} / ${basePages.length} trang` : `${basePages.length} trang`}
          >
            {isFiltered ? `${visible.length}/${basePages.length}` : basePages.length}
          </span>
          <button type="button" onClick={() => setCollapsed(true)} className={ICON_BTN} title="Thu gọn danh mục">
            <span className="material-symbols-outlined block" style={{ fontSize: 17 }}>left_panel_close</span>
          </button>
        </div>

        {/* Quick filter */}
        <div className="flex items-center gap-1.5 bg-background border border-border rounded-md px-2 h-8 focus-within:border-primary/60 focus-within:ring-2 focus-within:ring-primary/10 transition-all">
          <span className="material-symbols-outlined text-muted-foreground/70 shrink-0" style={{ fontSize: 15 }}>
            filter_list
          </span>
          <input
            ref={searchInputRef}
            type="text"
            placeholder="Lọc trang..."
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
              title="Xóa bộ lọc"
            >
              <span className="material-symbols-outlined block" style={{ fontSize: 14 }}>close</span>
            </button>
          )}
        </div>

        {/* Document filter */}
        {docOptions.length > 1 && (
          <div className="flex items-center gap-1">
            <select
              value={effectiveDocFilter}
              onChange={(e) => setDocFilter(e.target.value)}
              className="flex-1 min-w-0 h-8 px-2 text-xs rounded-md border border-border bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20 cursor-pointer truncate"
              title={selectedDoc?.title ?? "Tất cả văn bản"}
            >
              <option value="">Tất cả văn bản ({basePages.length})</option>
              {docOptions.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.title} ({d.count})
                </option>
              ))}
            </select>
            {selectedDoc && selectedDoc.id !== "other" && (
              <Link
                href={`/wiki/source/${selectedDoc.id}`}
                onClick={(e) => handleNavClick(e, `source/${selectedDoc.id}`)}
                className={ICON_BTN}
                title="Mở văn bản gốc"
              >
                <span className="material-symbols-outlined block" style={{ fontSize: 16 }}>open_in_new</span>
              </Link>
            )}
          </div>
        )}
      </div>

      {/* Sections */}
      <div ref={treeScrollRef} onScroll={handleTreeScroll} className="flex-1 overflow-y-auto px-2 py-2">
        {loading ? (
          <div className="px-1 space-y-2 mt-1">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="h-7 rounded-md bg-muted animate-pulse" style={{ opacity: 1 - i * 0.1 }} />
            ))}
          </div>
        ) : sections.length === 0 ? (
          renderEmpty()
        ) : (
          sections.map((sec) => {
            const open = isSectionOpen(sec.key);
            return (
              <div key={sec.key} className="mb-1.5">
                <div className="group flex items-center gap-1 pr-1">
                  <button
                    type="button"
                    onClick={() => toggleSection(sec.key)}
                    aria-expanded={open}
                    className="flex-1 min-w-0 flex items-center gap-1 px-1 py-1.5 text-left cursor-pointer"
                    title={sec.label}
                  >
                    <span
                      className={cn(
                        "material-symbols-outlined shrink-0 text-muted-foreground/70 transition-transform",
                        open && "rotate-90",
                      )}
                      style={{ fontSize: 15 }}
                    >
                      chevron_right
                    </span>
                    <span className="flex-1 truncate text-[11px] font-semibold uppercase tracking-wide text-muted-foreground group-hover:text-foreground">
                      {sec.label}
                    </span>
                  </button>
                  {sec.sourceId && (
                    <Link
                      href={`/wiki/source/${sec.sourceId}`}
                      onClick={(e) => handleNavClick(e, `source/${sec.sourceId}`)}
                      className="shrink-0 p-0.5 rounded text-muted-foreground hover:text-primary opacity-0 group-hover:opacity-100 focus-visible:opacity-100 transition-opacity"
                      title="Mở văn bản gốc"
                    >
                      <span className="material-symbols-outlined block" style={{ fontSize: 14 }}>open_in_new</span>
                    </Link>
                  )}
                  <span className="shrink-0 text-[10px] text-muted-foreground tabular-nums">{sec.items.length}</span>
                </div>
                {open && (
                  <div className="space-y-px">
                    {sec.items.map((it) =>
                      renderPageItem(it.page, {
                        overview: it.overview,
                        label: sec.sourceId && it.overview ? "Tổng quan văn bản" : undefined,
                      }),
                    )}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </aside>
  );
}
