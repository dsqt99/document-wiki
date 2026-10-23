"use client";

import { useEffect, useMemo, useRef, useState, type MouseEvent as ReactMouseEvent } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { encodeSlugPath, WIKI_PAGES_URL } from "@/components/wiki/wiki-pages-loader";
import { wikiTypeGroupLabel } from "@/components/wiki/wiki-type-badge";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import {
  displaySourceTitle,
  getCachedPages,
  getCachedSources,
  getDocForPage,
  removeCachedPage,
  setCachedPages,
  setCachedSources,
  useWikiStore,
  wikiStore,
  type WikiSourceItem,
} from "@/lib/wiki-store";
import type { WikiPageSummary, WikiScope } from "@/types/wiki";

type CreateMode = "direct" | "propose";

type Props = {
  activeSlug?: string;
  onDeleted?: (slug: string) => void;
  pagesUrl?: string;
  linkQueryParams?: string;
  onPageSelect?: (slug: string, page?: WikiPageSummary) => void;
  /** Fill an overlay without the standalone tree's collapse strip or border. */
  presentation?: "sidebar" | "overlay";
  groupByScope?: boolean;
  activeScope?: WikiScope;
  getCreateModeForScope?: (scopeType: string, scopeId: string | null) => CreateMode | null;
  onCreatePage?: (scopeType: string, scopeId: string | null) => void;
  onSearch?: () => void;
};

/** NFD, drop combining marks, map đ/Đ to d, lowercase. */
export function removeVietnameseTones(str: string): string {
  return (str ?? "")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[đĐ]/g, "d")
    .toLowerCase();
}

const HIDDEN_TYPES = new Set(["index", "log", "hot"]);
const OVERVIEW_TYPES = new Set(["summary", "overview", "source"]);
const OTHER_DOC = "other";
const OTHER_DOC_LABEL = "Tài liệu khác / Kiến thức chung";
const OVERVIEW_LABEL = "Tổng quan văn bản";

const byTitle = (a: WikiPageSummary, b: WikiPageSummary) =>
  (a.title || a.slug).localeCompare(b.title || b.slug, "vi", { numeric: true });

const isArticle = (p: WikiPageSummary) => (p.title ?? "").startsWith("Điều ");
/** A document's overview page: an overview-typed page, or a non-article page titled "Tổng quan …". */
const isOverview = (p: WikiPageSummary) =>
  OVERVIEW_TYPES.has(p.page_type) || (!isArticle(p) && /tổng quan/i.test(p.title ?? ""));

type DocOption = { id: string; title: string; count: number };

type Section = {
  key: string;
  label: string;
  icon?: string;
  docId?: string;
  pages: WikiPageSummary[];
  /** Overview pages inside a document section are labelled generically. */
  overviewLabel?: boolean;
};

/** Build the matcher for the (already debounced) filter text. */
function buildMatcher(raw: string, docTitleOf: (p: WikiPageSummary) => string): ((p: WikiPageSummary) => boolean) | null {
  const q = removeVietnameseTones(raw.trim());
  if (!q) return null;
  // "12", "12a", "điều 12", "dieu 12a" → exact article-number match on the title.
  const art = /^(?:dieu\s*)?(\d+[a-z]?)$/.exec(q);
  if (art) {
    const num = art[1];
    const re = new RegExp(`^dieu\\s+${num}(?![0-9a-z])`);
    return (p) => re.test(removeVietnameseTones(p.title ?? ""));
  }
  return (p) =>
    removeVietnameseTones(p.title ?? "").includes(q) ||
    removeVietnameseTones(p.slug).includes(q) ||
    removeVietnameseTones(p.summary ?? "").includes(q) ||
    removeVietnameseTones(docTitleOf(p)).includes(q);
}

export function WikiPageTree({
  activeSlug,
  onDeleted,
  pagesUrl = WIKI_PAGES_URL,
  linkQueryParams = "",
  onPageSelect,
  groupByScope = false,
  activeScope,
  getCreateModeForScope,
  onCreatePage,
  onSearch,
  presentation = "sidebar",
}: Props) {
  const { t } = useI18n();
  const store = useWikiStore();
  const { search, docFilter, collapsedSections, treeCollapsed, setSearch, setDocFilter, toggleSection, setTreeCollapsed, resetFilters } =
    store;
  const collapsed = presentation === "sidebar" && treeCollapsed;

  const [pagesState, setPagesState] = useState<{ url: string; list: WikiPageSummary[] | null }>(() => ({
    url: pagesUrl,
    list: getCachedPages(pagesUrl),
  }));
  const [sources, setSources] = useState<WikiSourceItem[]>(() => getCachedSources() ?? []);
  const [reloadTick, setReloadTick] = useState(0);
  const [debounced, setDebounced] = useState(search);
  const [armed, setArmed] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [focusFilter, setFocusFilter] = useState(false);

  const listRef = useRef<HTMLDivElement>(null);
  const filterRef = useRef<HTMLInputElement>(null);

  const pages = pagesState.url === pagesUrl ? pagesState.list : getCachedPages(pagesUrl);

  // Page list: cached copy first, then refresh from the server.
  useEffect(() => {
    let cancelled = false;
    api<WikiPageSummary[]>(pagesUrl)
      .then((res) => {
        if (cancelled) return;
        const list = Array.isArray(res) ? res : [];
        setCachedPages(pagesUrl, list);
        setPagesState({ url: pagesUrl, list });
      })
      .catch(() => {
        if (!cancelled) setPagesState((prev) => (prev.url === pagesUrl && prev.list ? prev : { url: pagesUrl, list: [] }));
      });
    return () => {
      cancelled = true;
    };
  }, [pagesUrl, reloadTick]);

  // Source documents (for grouping by document).
  useEffect(() => {
    let cancelled = false;
    api<{ items?: WikiSourceItem[] }>("/api/sources?page_size=1000")
      .then((res) => {
        if (cancelled) return;
        const items = Array.isArray(res?.items) ? res.items : [];
        setCachedSources(items);
        setSources(items);
      })
      .catch(() => {
        /* keep whatever was cached */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Filtering runs on a 150ms-debounced copy of the store value.
  useEffect(() => {
    const id = setTimeout(() => setDebounced(search), 150);
    return () => clearTimeout(id);
  }, [search]);

  // Restore the list scroll position whenever the list (re)appears.
  useEffect(() => {
    if (!collapsed && listRef.current) listRef.current.scrollTop = wikiStore.sidebarScrollTop;
  }, [collapsed]);

  // Focus the filter after expanding from the collapsed strip.
  useEffect(() => {
    if (!focusFilter || collapsed) return;
    const id = setTimeout(() => {
      filterRef.current?.focus();
      setFocusFilter(false);
    }, 0);
    return () => clearTimeout(id);
  }, [focusFilter, collapsed]);

  // Clicking anywhere outside the armed row disarms the delete.
  useEffect(() => {
    if (!armed) return;
    const onDown = (e: MouseEvent) => {
      const row = (e.target as HTMLElement | null)?.closest?.("[data-tree-row]");
      if (!row || row.getAttribute("data-tree-row") !== armed) setArmed(null);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [armed]);

  // Keep the active row visible when the selection changes after the first
  // render; the initial load keeps the list at its top (or restored) position.
  const initialSlug = useRef(activeSlug);
  useEffect(() => {
    if (!activeSlug || !listRef.current) return;
    if (activeSlug === initialSlug.current) return;
    initialSlug.current = undefined;
    const el = listRef.current.querySelector<HTMLElement>(`[data-tree-row="${CSS.escape(activeSlug)}"]`);
    el?.scrollIntoView({ block: "nearest" });
  }, [activeSlug, pages]);

  const basePages = useMemo(
    () =>
      (pages ?? []).filter(
        (p) => !HIDDEN_TYPES.has(p.page_type) && !(groupByScope && p.scope_type === "project"),
      ),
    [pages, groupByScope],
  );

  const docOfPage = useMemo(() => {
    const m = new Map<string, WikiSourceItem | null>();
    for (const p of basePages) {
      const sourceId = p.source_ids?.[0];
      // Explicit source context must work while source labels are still loading,
      // including documents no longer returned by the ready-sources endpoint.
      m.set(p.slug, sourceId
        ? sources.find((source) => source.id === sourceId) ?? { id: sourceId, title: "Văn bản nguồn", status: "ready" }
        : getDocForPage(p, sources));
    }
    return m;
  }, [basePages, sources]);

  const docOptions = useMemo<DocOption[]>(() => {
    const counts = new Map<string, DocOption>();
    let other = 0;
    for (const p of basePages) {
      const d = docOfPage.get(p.slug);
      if (!d) {
        other += 1;
        continue;
      }
      const cur = counts.get(d.id);
      if (cur) cur.count += 1;
      else counts.set(d.id, { id: d.id, title: displaySourceTitle(d), count: 1 });
    }
    const list = [...counts.values()].sort((a, b) => a.title.localeCompare(b.title, "vi"));
    if (other > 0) list.push({ id: OTHER_DOC, title: OTHER_DOC_LABEL, count: other });
    return list;
  }, [basePages, docOfPage]);

  const activeDoc = docOptions.some((o) => o.id === docFilter) ? docFilter : "";
  const query = debounced.trim();
  const isFiltering = !!query || !!activeDoc;

  const visible = useMemo(() => {
    const docTitleOf = (p: WikiPageSummary) => {
      const d = docOfPage.get(p.slug);
      return d ? displaySourceTitle(d) : "";
    };
    const match = buildMatcher(query, docTitleOf);
    return basePages.filter((p) => {
      if (activeDoc) {
        const d = docOfPage.get(p.slug);
        if (activeDoc === OTHER_DOC ? !!d : d?.id !== activeDoc) return false;
      }
      return match ? match(p) : true;
    });
  }, [basePages, docOfPage, activeDoc, query]);

  const sections = useMemo<Section[]>(() => {
    const singleDoc = !!activeDoc || docOptions.length <= 1;
    if (singleDoc) {
      const overview: WikiPageSummary[] = [];
      const articles: WikiPageSummary[] = [];
      const rest = new Map<string, WikiPageSummary[]>();
      for (const p of visible) {
        if (isOverview(p)) overview.push(p);
        else if (isArticle(p)) articles.push(p);
        else {
          const label = wikiTypeGroupLabel(p.page_type);
          const list = rest.get(label) ?? [];
          list.push(p);
          rest.set(label, list);
        }
      }
      const realDoc = activeDoc && activeDoc !== OTHER_DOC ? activeDoc : docOptions.length === 1 && docOptions[0].id !== OTHER_DOC ? docOptions[0].id : undefined;
      const out: Section[] = [];
      if (overview.length) out.push({ key: "overview", label: OVERVIEW_LABEL, icon: "menu_book", docId: realDoc, pages: overview.sort(byTitle) });
      if (articles.length) out.push({ key: "articles", label: "Điều khoản", pages: articles.sort(byTitle) });
      [...rest.entries()]
        .sort((a, b) => a[0].localeCompare(b[0], "vi"))
        .forEach(([label, list]) => out.push({ key: `type:${label}`, label, pages: list.sort(byTitle) }));
      return out;
    }
    const byDoc = new Map<string, WikiPageSummary[]>();
    for (const p of visible) {
      const id = docOfPage.get(p.slug)?.id ?? OTHER_DOC;
      const list = byDoc.get(id) ?? [];
      list.push(p);
      byDoc.set(id, list);
    }
    const rankOf = (p: WikiPageSummary) => (isOverview(p) ? 0 : isArticle(p) ? 1 : 2);
    return docOptions
      .filter((o) => byDoc.has(o.id))
      .map((o) => {
        const list = (byDoc.get(o.id) ?? []).sort((a, b) => rankOf(a) - rankOf(b) || byTitle(a, b));
        const isDoc = o.id !== OTHER_DOC;
        return {
          key: `doc:${o.id}`,
          label: o.title,
          docId: isDoc ? o.id : undefined,
          pages: list,
          overviewLabel: isDoc,
        };
      });
  }, [visible, activeDoc, docOptions, docOfPage]);

  const createScopeType = activeScope?.scope_type ?? "global";
  const createScopeId = activeScope?.scope_id ?? null;
  const createMode = getCreateModeForScope ? getCreateModeForScope(createScopeType, createScopeId) : null;

  const pageHref = (p: WikiPageSummary) => {
    const params = new URLSearchParams(linkQueryParams.replace(/^\?/, ""));
    if (p.scope_type) {
      params.delete("scopeType");
      params.delete("scopeId");
      if (p.scope_type !== "global") {
        params.set("scopeType", p.scope_type);
        if (p.scope_id) params.set("scopeId", p.scope_id);
      }
    }
    const query = params.toString();
    return `/wiki/${encodeSlugPath(p.slug)}${query ? `?${query}` : ""}`;
  };

  const onRowClick = (e: ReactMouseEvent<HTMLAnchorElement>, page: WikiPageSummary) => {
    if (!onPageSelect || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    onPageSelect(page.slug, page);
  };

  const doDelete = async (p: WikiPageSummary) => {
    setDeleting(p.slug);
    const qs =
      p.scope_type && p.scope_type !== "global"
        ? `?scope_type=${encodeURIComponent(p.scope_type)}&scope_id=${encodeURIComponent(p.scope_id ?? "")}`
        : "";
    try {
      await api(`/api/wiki/pages/${encodeSlugPath(p.slug)}${qs}`, { method: "DELETE" });
      removeCachedPage(p.slug);
      // Detail cache entries are keyed "slug:scopeType:scopeId"; drop those too.
      for (const key of [...wikiStore.pageDetailCache.keys()]) {
        if (key.startsWith(`${p.slug}:`)) wikiStore.pageDetailCache.delete(key);
      }
      setPagesState((prev) => ({ url: prev.url, list: (prev.list ?? []).filter((x) => x.slug !== p.slug) }));
      setReloadTick((n) => n + 1);
      onDeleted?.(p.slug);
    } catch (err) {
      console.error("Failed to delete wiki page", err);
    } finally {
      setDeleting(null);
      setArmed(null);
    }
  };

  if (collapsed) {
    return (
      <aside className="flex h-full w-11 shrink-0 flex-col items-center gap-1 border-r bg-muted/30 py-3">
        <Tooltip>
          <TooltipTrigger
            render={
              <button
                type="button"
                aria-label="Mở danh mục"
                onClick={() => setTreeCollapsed(false)}
                className="flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
              />
            }
          >
            <span className="material-symbols-outlined" style={{ fontSize: 20 }}>
              left_panel_open
            </span>
          </TooltipTrigger>
          <TooltipContent side="right">Mở danh mục</TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger
            render={
              <button
                type="button"
                aria-label="Lọc trang"
                onClick={() => {
                  setTreeCollapsed(false);
                  setFocusFilter(true);
                }}
                className="flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
              />
            }
          >
            <span className="material-symbols-outlined" style={{ fontSize: 20 }}>
              filter_list
            </span>
          </TooltipTrigger>
          <TooltipContent side="right">Lọc trang</TooltipContent>
        </Tooltip>
      </aside>
    );
  }

  const total = basePages.length;
  const shown = visible.length;

  return (
    <aside className={cn("flex h-full min-h-0 shrink-0 flex-col bg-muted/30", presentation === "overlay" ? "w-full" : "w-64 border-r lg:w-72")}>
      {/* header */}
      <div className="flex items-center gap-1 px-3 pt-3 pb-2">
        <Tooltip>
          <TooltipTrigger
            render={
              <Link
                href="/knowledge?tab=wiki"
                className="flex items-center gap-1 rounded-md px-1 py-0.5 text-sm font-semibold hover:bg-muted"
              />
            }
          >
            <span className="material-symbols-outlined" style={{ fontSize: 18 }}>
              arrow_back
            </span>
            Wiki
          </TooltipTrigger>
          <TooltipContent>Về Kho tri thức</TooltipContent>
        </Tooltip>
        <div className="ml-auto flex items-center gap-0.5">
          <HeaderButton icon="search" tip="Tìm kiếm (Ctrl+K)" onClick={onSearch} />
          <Tooltip>
            <TooltipTrigger
              render={
                <Link
                  href="/wiki/graph"
                  aria-label="Xem sơ đồ"
                  className="flex h-8 w-[25px] items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
                />
              }
            >
              <span className="material-symbols-outlined" style={{ fontSize: 17 }}>
                hub
              </span>
            </TooltipTrigger>
            <TooltipContent>Xem sơ đồ</TooltipContent>
          </Tooltip>
          {createMode && (
            <HeaderButton
              icon="add"
              tip={createMode === "direct" ? "Tạo trang mới" : "Đề xuất trang mới (cần duyệt)"}
              onClick={() => onCreatePage?.(createScopeType, createScopeId)}
            />
          )}
          <Tooltip>
            <TooltipTrigger
              render={
                <span className="cursor-default rounded-lg bg-muted px-1.5 py-px text-[11px] font-medium text-muted-foreground tabular-nums" />
              }
            >
              {isFiltering ? `${shown}/${total}` : total}
            </TooltipTrigger>
            <TooltipContent>{isFiltering ? `${shown} / ${total} trang` : `${total} trang`}</TooltipContent>
          </Tooltip>
          {presentation === "sidebar" && <HeaderButton icon="left_panel_close" tip="Thu gọn danh mục" onClick={() => setTreeCollapsed(true)} />}
        </div>
      </div>

      {/* filter */}
      <div className="border-b px-3 pb-2.5">
        <div className="relative">
          <span
            className="material-symbols-outlined pointer-events-none absolute top-1/2 left-2 -translate-y-1/2 text-muted-foreground"
            style={{ fontSize: 16 }}
          >
            filter_list
          </span>
          <input
            ref={filterRef}
            aria-label="Lọc trang trong danh mục"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape" && presentation === "sidebar") {
                e.preventDefault();
                setSearch("");
              }
            }}
            placeholder="Lọc trang..."
            className="h-8 w-full rounded-[10px] border bg-background pr-7 pl-[29px] text-xs outline-none focus:border-primary"
          />
          {search && (
            <Tooltip>
              <TooltipTrigger
                render={
                  <button
                    type="button"
                    aria-label="Xóa bộ lọc"
                    onClick={() => setSearch("")}
                    className="absolute top-1/2 right-1.5 flex -translate-y-1/2 items-center text-muted-foreground hover:text-foreground"
                  />
                }
              >
                <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
                  close
                </span>
              </TooltipTrigger>
              <TooltipContent>Xóa bộ lọc</TooltipContent>
            </Tooltip>
          )}
        </div>

        {docOptions.length > 0 && (
          <div className="mt-2 flex items-center gap-1">
            <Select value={activeDoc || "__all__"} onValueChange={(v) => setDocFilter(!v || v === "__all__" ? "" : String(v))}>
              <SelectTrigger aria-label="Văn bản trong danh mục" size="sm" className="h-8! min-w-0 flex-1 text-[13px]">
                <SelectValue>
                  {() => {
                    const o = docOptions.find((x) => x.id === activeDoc);
                    return o ? `${o.title} (${o.count})` : `Tất cả văn bản (${total})`;
                  }}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__all__">Tất cả văn bản ({total})</SelectItem>
                {docOptions.map((o) => (
                  <SelectItem key={o.id} value={o.id}>
                    {o.title} ({o.count})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {activeDoc && activeDoc !== OTHER_DOC && (
              <Tooltip>
                <TooltipTrigger
                  render={
                    <Link
                      href={`/wiki/source/${encodeURIComponent(activeDoc)}${linkQueryParams}`}
                      onClick={(e) => {
                        if (!onPageSelect || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
                        e.preventDefault();
                        onPageSelect(`source/${activeDoc}`);
                      }}
                      aria-label="Mở văn bản gốc"
                      className="flex size-8 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
                    />
                  }
                >
                  <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
                    open_in_new
                  </span>
                </TooltipTrigger>
                <TooltipContent>Mở văn bản gốc</TooltipContent>
              </Tooltip>
            )}
          </div>
        )}
      </div>

      {/* list */}
      <div
        ref={listRef}
        onScroll={(e) => {
          wikiStore.sidebarScrollTop = e.currentTarget.scrollTop;
        }}
        className="min-h-0 flex-1 overflow-y-auto px-2 pt-2 pb-4"
      >
        {pages === null ? (
          <div className="space-y-2 px-1 pt-1">
            {Array.from({ length: 8 }, (_, i) => (
              <div key={i} className="h-6 animate-pulse rounded bg-muted" style={{ width: `${60 + ((i * 13) % 35)}%` }} />
            ))}
          </div>
        ) : sections.length === 0 ? (
          <div className="flex flex-col items-center px-3 py-10 text-center">
            <span className="material-symbols-outlined text-muted-foreground" style={{ fontSize: 32 }}>
              search_off
            </span>
            <p className="mt-2 text-sm font-medium">{t("wiki.noPages", "Không tìm thấy trang nào")}</p>
            <p className="mt-1 text-xs text-muted-foreground">{t("wiki.noPagesDesc", "Thử thay đổi từ khóa hoặc bộ lọc")}</p>
            {(isFiltering || !!search) && (
              <Button variant="outline" size="sm" className="mt-3" onClick={resetFilters}>
                <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
                  restart_alt
                </span>
                {t("wiki.reset", "Đặt lại bộ lọc")}
              </Button>
            )}
          </div>
        ) : (
          sections.map((sec) => {
            const hasActive = !!activeSlug && sec.pages.some((p) => p.slug === activeSlug);
            const open = !!query || hasActive || !collapsedSections.has(sec.key);
            return (
              <div key={sec.key} className="mb-1.5">
                <div className="group flex items-center gap-1 px-1 py-1.5 hover:bg-muted/60">
                  <button
                    type="button"
                    onClick={() => toggleSection(sec.key)}
                    className="flex min-w-0 flex-1 items-center gap-1 text-left text-[11px] font-semibold tracking-wide text-muted-foreground uppercase"
                  >
                    <span
                      className={cn("material-symbols-outlined shrink-0 transition-transform", open && "rotate-90")}
                      style={{ fontSize: 16 }}
                    >
                      chevron_right
                    </span>
                    {sec.icon && (
                      <span className="material-symbols-outlined shrink-0" style={{ fontSize: 14 }}>
                        {sec.icon}
                      </span>
                    )}
                    <span className="truncate">{sec.label}</span>
                  </button>
                  {sec.docId && (
                    <Tooltip>
                      <TooltipTrigger
                        render={
                          <Link
                            href={`/wiki/source/${encodeURIComponent(sec.docId)}`}
                            onClick={(e) => {
                              if (!onPageSelect || !sec.docId || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
                              e.preventDefault();
                              onPageSelect(`source/${sec.docId}`);
                            }}
                            aria-label="Mở văn bản gốc"
                            className="hidden shrink-0 items-center text-muted-foreground group-hover:flex hover:text-primary"
                          />
                        }
                      >
                        <span className="material-symbols-outlined" style={{ fontSize: 14 }}>
                          open_in_new
                        </span>
                      </TooltipTrigger>
                      <TooltipContent>Mở văn bản gốc</TooltipContent>
                    </Tooltip>
                  )}
                  <span className="shrink-0 text-[11px] text-muted-foreground tabular-nums">{sec.pages.length}</span>
                </div>
                {open && (
                  <ul className="space-y-px">
                    {sec.pages.map((p) => {
                      const isActive = p.slug === activeSlug;
                      const isArmed = armed === p.slug;
                      const asOverview = !!sec.overviewLabel && isOverview(p);
                      const label = asOverview ? OVERVIEW_LABEL : p.title || p.slug;
                      return (
                        <li
                          key={`${p.slug}:${p.scope_type ?? ""}:${p.scope_id ?? ""}`}
                          data-tree-row={p.slug}
                          className={cn(
                            "group/row relative flex items-center rounded-md",
                            isActive ? "bg-primary/10 text-primary" : "hover:bg-muted",
                          )}
                        >
                          {isActive && <span className="absolute top-1 bottom-1 left-0 w-0.5 rounded-full bg-primary" />}
                          <Link
                            href={pageHref(p)}
                            title={p.summary || p.title}
                            onClick={(e) => onRowClick(e, p)}
                            aria-current={isActive ? "page" : undefined}
                            className="flex min-w-0 flex-1 items-center gap-2 py-1.5 pr-1 pl-2.5 text-xs leading-4 text-foreground/75"
                          >
                            {asOverview ? (
                              <span
                                aria-hidden
                                className="material-symbols-outlined w-3.5 shrink-0 text-blue-500"
                                style={{ fontSize: 14 }}
                              >
                                chrome_reader_mode
                              </span>
                            ) : (
                              <span
                                aria-hidden
                                className="size-1.5 shrink-0 rounded-full bg-muted-foreground/40"
                              />
                            )}
                            <span className={cn("truncate", isActive && "font-medium")}>{label}</span>
                          </Link>
                          <div className="flex shrink-0 items-center pr-1">
                            {deleting === p.slug ? (
                              <span
                                className="material-symbols-outlined animate-spin text-muted-foreground"
                                style={{ fontSize: 14 }}
                              >
                                progress_activity
                              </span>
                            ) : isArmed ? (
                              <Tooltip>
                                <TooltipTrigger
                                  render={
                                    <button
                                      type="button"
                                      onClick={() => doDelete(p)}
                                      className="rounded px-1.5 py-0.5 text-[11px] font-semibold text-destructive hover:bg-destructive/10"
                                    />
                                  }
                                >
                                  Xóa?
                                </TooltipTrigger>
                                <TooltipContent>{`Bấm lần nữa để xóa "${p.title}"`}</TooltipContent>
                              </Tooltip>
                            ) : (
                              <Tooltip>
                                <TooltipTrigger
                                  render={
                                    <button
                                      type="button"
                                      aria-label={`Xóa "${p.title}"`}
                                      onClick={() => setArmed(p.slug)}
                                      className="flex size-6 items-center justify-center rounded text-muted-foreground opacity-100 group-hover/row:opacity-100 focus:opacity-100 md:opacity-0 hover:text-destructive"
                                    />
                                  }
                                >
                                  <span className="material-symbols-outlined" style={{ fontSize: 14 }}>
                                    delete
                                  </span>
                                </TooltipTrigger>
                                <TooltipContent>{`Xóa "${p.title}"`}</TooltipContent>
                              </Tooltip>
                            )}
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>
            );
          })
        )}
      </div>
    </aside>
  );
}

function HeaderButton({ icon, tip, onClick }: { icon: string; tip: string; onClick?: () => void }) {
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <button
            type="button"
            aria-label={tip}
            onClick={onClick}
            className="flex h-8 w-[25px] items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
          />
        }
      >
        <span className="material-symbols-outlined" style={{ fontSize: 17 }}>
          {icon}
        </span>
      </TooltipTrigger>
      <TooltipContent>{tip}</TooltipContent>
    </Tooltip>
  );
}

