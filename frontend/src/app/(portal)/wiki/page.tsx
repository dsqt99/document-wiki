"use client";

import React from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { WikiPageSummary, WikiScope } from "@/types/wiki";
import { WikiHeaderBar } from "@/components/wiki/wiki-header-bar";
import { WikiContent } from "@/components/wiki/wiki-content";
import { wikiTypeGroupLabel } from "@/components/wiki/wiki-type-badge";
import { WikiStatusBadge } from "@/components/wiki/wiki-status-badge";
import { WikiSearchDialog } from "@/components/wiki/wiki-search-dialog";
import { WikiCreatePageDialog } from "@/components/wiki/wiki-create-page-dialog";
import {
  FacetGroup,
  STATUS_LABEL_VI,
  STATUS_ORDER,
  countFacet,
} from "@/components/wiki/wiki-facets";
import { EmptyState } from "@/components/shared/empty-state";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";
import { WikiSourceItem, displaySourceTitle } from "@/lib/wiki-store";

const WORKSPACE_ROLE_LEVEL: Record<string, number> = {
  viewer: 0,
  contributor: 1,
  editor: 2,
  admin: 3,
};
function roleAtLeast(role: string | null, min: string): boolean {
  if (!role) return false;
  return (WORKSPACE_ROLE_LEVEL[role] ?? -1) >= (WORKSPACE_ROLE_LEVEL[min] ?? 999);
}

const PAGE_CHUNK = 50;
const NEW_WINDOW_MS = 7 * 24 * 3600 * 1000;

type SortKey = "updated_desc" | "updated_asc" | "title" | "sources";
type ScopeFilter = "all" | "global" | "department";
type FacetKey = "dept" | "status" | "kt" | "type" | "source";

function pageHref(p: WikiPageSummary): string {
  return p.scope_type && p.scope_type !== "global" && p.scope_id
    ? `/wiki/${p.slug}?scopeType=${p.scope_type}&scopeId=${p.scope_id}`
    : `/wiki/${p.slug}`;
}

function deptKey(p: WikiPageSummary): string {
  const st = p.scope_type || "global";
  return st === "global" ? "global" : `${st}:${p.scope_id ?? ""}`;
}

function scopeLabel(p: WikiPageSummary): string {
  const st = p.scope_type || "global";
  if (st === "global") return "Toàn công ty";
  return p.scope_name || (st === "department" ? "Phòng ban" : st);
}

export default function WikiIndexPage() {
  const searchParams = useSearchParams();
  const urlScopeType = searchParams.get("scope_type");
  const urlScopeId = searchParams.get("scope_id");

  const { user, getWorkspaceRole, hasPermission } = useAuth();

  const [indexMd, setIndexMd] = React.useState<string | null>(null);
  const [allPages, setAllPages] = React.useState<WikiPageSummary[]>([]);
  const [sources, setSources] = React.useState<WikiSourceItem[]>([]);
  const [searchOpen, setSearchOpen] = React.useState(false);
  const [createOpen, setCreateOpen] = React.useState(false);
  const [prefillTitle, setPrefillTitle] = React.useState("");
  const [scopes, setScopes] = React.useState<WikiScope[]>([]);

  const [viewMode, setViewMode] = React.useState<"pages" | "index">("pages");

  // List controls
  const [query, setQuery] = React.useState("");
  const [searchMode, setSearchMode] = React.useState<"title" | "content">("title");
  const [sort, setSort] = React.useState<SortKey>("updated_desc");
  const [scopeFilter, setScopeFilter] = React.useState<ScopeFilter>("all");
  const [facets, setFacets] = React.useState<Record<FacetKey, Set<string>>>(() => ({
    dept: new Set(),
    status: new Set(),
    kt: new Set(),
    type: new Set(),
    source: new Set(),
  }));
  const [shown, setShown] = React.useState(PAGE_CHUNK);

  // Content-mode (semantic) search results, in relevance order.
  // Last semantic-search response, tagged with the query it answers
  const [contentResult, setContentResult] = React.useState<{ q: string; hits: WikiPageSummary[]; error: string } | null>(
    null,
  );

  // Open the create dialog when the URL asks for it (?new=1&title=...)
  const [prevSearchParams, setPrevSearchParams] = React.useState<typeof searchParams | null>(null);
  if (searchParams !== prevSearchParams) {
    setPrevSearchParams(searchParams);
    if (searchParams.get("new") === "1") {
      setPrefillTitle(searchParams.get("title") || "");
      setCreateOpen(true);
    }
  }

  const selectedScope: WikiScope = React.useMemo(() => {
    if (urlScopeType && urlScopeType !== "global") {
      const match = scopes.find(
        (s) => s.scope_type === urlScopeType && (s.scope_id ?? null) === (urlScopeId ?? null),
      );
      if (match) return match;
      return { scope_type: urlScopeType, scope_id: urlScopeId, name: urlScopeType };
    }
    return { scope_type: "global", scope_id: null, name: "Global" };
  }, [urlScopeType, urlScopeId, scopes]);

  React.useEffect(() => {
    api<WikiScope[]>("/api/wiki/my-scopes")
      .then((s) => setScopes(Array.isArray(s) ? s : []))
      .catch(() => setScopes([]));
  }, []);

  // Loading is derived: true until the data for the current scope has arrived
  const scopeKey = `${selectedScope.scope_type}:${selectedScope.scope_id ?? ""}`;
  const [loadedScopeKey, setLoadedScopeKey] = React.useState<string | null>(null);
  const loading = loadedScopeKey !== scopeKey;
  React.useEffect(() => {
    let cancelled = false;
    const qs = selectedScope.scope_id
      ? `scope_type=${selectedScope.scope_type}&scope_id=${selectedScope.scope_id}`
      : `scope_type=${selectedScope.scope_type}`;
    Promise.all([
      api<{ content_md: string }>(`/api/wiki/index?${qs}`),
      // Global view lists every page the user can read.
      api<WikiPageSummary[]>(
        selectedScope.scope_type === "global" ? "/api/wiki/pages" : `/api/wiki/pages?${qs}`,
      ),
      api<{ items: WikiSourceItem[] }>("/api/sources?status=ready&page_size=1000"),
    ])
      .then(([idx, pages, srcData]) => {
        if (cancelled) return;
        setIndexMd(idx.content_md || null);
        setAllPages(
          Array.isArray(pages)
            ? pages.filter((p) => p.page_type !== "index" && p.page_type !== "log")
            : [],
        );
        setSources(srcData?.items || []);
      })
      .catch(() => {
        if (cancelled) return;
        setIndexMd(null);
        setAllPages([]);
        setSources([]);
      })
      .finally(() => {
        if (!cancelled) setLoadedScopeKey(scopeKey);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedScope.scope_type, selectedScope.scope_id, scopeKey]);

  React.useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setSearchOpen(true);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  // Debounced content search
  const trimmedQuery = query.trim();
  const contentActive = searchMode === "content" && !!trimmedQuery;
  const contentFresh = contentActive && contentResult?.q === trimmedQuery;
  const contentHits = contentFresh ? contentResult!.hits : null;
  const contentError = contentFresh ? contentResult!.error : "";
  const contentLoading = contentActive && !contentFresh;
  React.useEffect(() => {
    if (searchMode !== "content" || !trimmedQuery) return;
    let cancelled = false;
    const t = setTimeout(() => {
      api<WikiPageSummary[]>(`/api/wiki/search?q=${encodeURIComponent(trimmedQuery)}&limit=100`)
        .then((hits) => {
          if (!cancelled) setContentResult({ q: trimmedQuery, hits: Array.isArray(hits) ? hits : [], error: "" });
        })
        .catch((e) => {
          if (!cancelled) {
            setContentResult({ q: trimmedQuery, hits: [], error: e instanceof Error ? e.message : "Tìm kiếm thất bại" });
          }
        });
    }, 400);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [searchMode, trimmedQuery]);

  // Reset pagination whenever the result set definition changes
  const listKey = [query, searchMode, sort, scopeFilter, facets] as const;
  const [prevListKey, setPrevListKey] = React.useState(listKey);
  if (listKey.some((v, i) => v !== prevListKey[i])) {
    setPrevListKey(listKey);
    setShown(PAGE_CHUNK);
  }

  const isAdmin = user?.role === "admin";
  const getCreateModeForScope = React.useCallback(
    (scope: { scope_type: string; scope_id: string | null }): "direct" | "propose" | null => {
      if (!user) return null;
      const st = scope.scope_type;
      const sid = scope.scope_id;
      if (st === "project" && sid) {
        const role = getWorkspaceRole(sid);
        if (isAdmin || roleAtLeast(role, "editor")) return "direct";
        if (roleAtLeast(role, "contributor")) return "propose";
        return null;
      }
      if (st === "department" && sid) {
        if (isAdmin || hasPermission("wiki:write:all")) return "direct";
        if (hasPermission("wiki:write:own_dept") && user.department_ids.includes(sid)) {
          return "propose";
        }
        return null;
      }
      if (isAdmin || hasPermission("wiki:write:all")) return "direct";
      if (hasPermission("wiki:write:own_dept")) return "propose";
      return null;
    },
    [user, isAdmin, getWorkspaceRole, hasPermission],
  );
  const createMode = getCreateModeForScope(selectedScope);

  const sourceTitleById = React.useMemo(() => {
    const m = new Map<string, string>();
    for (const s of sources) m.set(s.id, displaySourceTitle(s));
    return m;
  }, [sources]);

  // Base list: title filter (client) or content hits (server, relevance order).
  const basePages = React.useMemo(() => {
    if (searchMode === "content" && trimmedQuery) {
      if (!contentHits) return [];
      // Keep only pages loaded for this scope view.
      const loaded = new Set(allPages.map((p) => `${p.slug}|${p.scope_type}|${p.scope_id ?? ""}`));
      return contentHits.filter((p) => loaded.has(`${p.slug}|${p.scope_type}|${p.scope_id ?? ""}`));
    }
    if (!trimmedQuery) return allPages;
    const q = trimmedQuery.toLowerCase();
    return allPages.filter((p) => `${p.title} ${p.slug}`.toLowerCase().includes(q));
  }, [allPages, searchMode, trimmedQuery, contentHits]);

  const scopeCounts = React.useMemo(() => {
    let global = 0;
    let department = 0;
    for (const p of basePages) {
      if (p.scope_type === "global") global += 1;
      else if (p.scope_type === "department") department += 1;
    }
    return { all: basePages.length, global, department };
  }, [basePages]);

  const scopedPages = React.useMemo(
    () => (scopeFilter === "all" ? basePages : basePages.filter((p) => p.scope_type === scopeFilter)),
    [basePages, scopeFilter],
  );

  const facetKeys: Record<FacetKey, (p: WikiPageSummary) => string[]> = React.useMemo(
    () => ({
      dept: (p) => [deptKey(p)],
      status: (p) => [p.status || "seed"],
      kt: (p) => (p.knowledge_type_slugs.length ? p.knowledge_type_slugs : ["__none"]),
      type: (p) => [p.page_type],
      source: (p) => p.source_ids.map(String),
    }),
    [],
  );

  const deptLabels = React.useMemo(() => {
    const m = new Map<string, string>();
    for (const p of allPages) {
      const k = deptKey(p);
      if (!m.has(k)) m.set(k, p.scope_type === "global" ? "Toàn công ty" : scopeLabel(p));
    }
    return m;
  }, [allPages]);

  const facetOptions = React.useMemo(
    () => ({
      dept: countFacet(scopedPages, facetKeys.dept, (k) => deptLabels.get(k) ?? k),
      status: countFacet(scopedPages, facetKeys.status, (k) => STATUS_LABEL_VI[k] ?? k, STATUS_ORDER),
      kt: countFacet(scopedPages, facetKeys.kt, (k) => (k === "__none" ? "Chưa phân loại" : k)),
      type: countFacet(scopedPages, facetKeys.type, (k) => wikiTypeGroupLabel(k)),
      source: countFacet(scopedPages, facetKeys.source, (k) => sourceTitleById.get(k) ?? "Văn bản khác"),
    }),
    [scopedPages, facetKeys, deptLabels, sourceTitleById],
  );

  const activeFacetCount = Object.values(facets).reduce((n, s) => n + s.size, 0);

  const filteredPages = React.useMemo(() => {
    let list = scopedPages;
    for (const key of Object.keys(facets) as FacetKey[]) {
      const sel = facets[key];
      if (sel.size === 0) continue;
      list = list.filter((p) => facetKeys[key](p).some((v) => sel.has(v)));
    }
    // Content search keeps relevance order unless the user picked a sort.
    if (searchMode === "content" && trimmedQuery && sort === "updated_desc") return list;
    const sorted = [...list];
    switch (sort) {
      case "updated_desc":
        sorted.sort((a, b) => b.updated_at.localeCompare(a.updated_at));
        break;
      case "updated_asc":
        sorted.sort((a, b) => a.updated_at.localeCompare(b.updated_at));
        break;
      case "title":
        sorted.sort((a, b) => a.title.localeCompare(b.title, "vi", { numeric: true }));
        break;
      case "sources":
        sorted.sort((a, b) => b.source_ids.length - a.source_ids.length);
        break;
    }
    return sorted;
  }, [scopedPages, facets, facetKeys, sort, searchMode, trimmedQuery]);

  const toggleFacet = (key: FacetKey, value: string) =>
    setFacets((prev) => {
      const next = new Set(prev[key]);
      if (next.has(value)) next.delete(value);
      else next.add(value);
      return { ...prev, [key]: next };
    });

  const clearFilters = () => {
    setFacets({ dept: new Set(), status: new Set(), kt: new Set(), type: new Set(), source: new Set() });
    setScopeFilter("all");
  };

  const copyLink = (p: WikiPageSummary) => {
    void navigator.clipboard?.writeText(`${window.location.origin}${pageHref(p)}`);
  };

  const [dialogScope, setDialogScope] = React.useState<WikiScope | null>(null);
  const dialogTargetScope: WikiScope = dialogScope ?? selectedScope;
  const dialogMode = getCreateModeForScope(dialogTargetScope);

  const [now] = React.useState(() => Date.now());

  return (
    <>
      <div className="flex flex-col gap-5">
        <WikiHeaderBar
          scope={selectedScope}
          onSearch={() => setSearchOpen(true)}
          createMode={createMode}
          onCreate={() => {
            setDialogScope(null);
            setCreateOpen(true);
          }}
        />

        {/* View tabs */}
        <div className="flex items-center gap-1 border-b border-border -mt-1">
          {(
            [
              { id: "pages", label: "Trang wiki", icon: "article", count: allPages.length },
              ...(indexMd ? [{ id: "index", label: "Mục lục tổng hợp", icon: "menu_book", count: null }] : []),
            ] as { id: typeof viewMode; label: string; icon: string; count: number | null }[]
          ).map((tab) => {
            const active = viewMode === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setViewMode(tab.id)}
                className={cn(
                  "flex items-center gap-1.5 px-3 py-2 -mb-px text-sm font-medium border-b-2 transition-colors cursor-pointer",
                  active
                    ? "border-primary text-primary"
                    : "border-transparent text-muted-foreground hover:text-foreground",
                )}
              >
                <span className="material-symbols-outlined" style={{ fontSize: 17 }}>{tab.icon}</span>
                {tab.label}
                {tab.count !== null && (
                  <span className="text-xs tabular-nums text-muted-foreground">{tab.count}</span>
                )}
              </button>
            );
          })}
          <Link
            href="/wiki/law"
            className="flex items-center gap-1.5 px-3 py-2 -mb-px text-sm font-medium border-b-2 border-transparent text-muted-foreground hover:text-foreground transition-colors"
          >
            <span className="material-symbols-outlined" style={{ fontSize: 17 }}>balance</span>
            Wiki Pháp luật
            <span className="text-xs tabular-nums text-muted-foreground">{sources.length}</span>
          </Link>
        </div>

        {loading ? (
          <div className="flex items-center justify-center h-48">
            <span className="material-symbols-outlined text-3xl text-muted-foreground animate-spin">
              progress_activity
            </span>
          </div>
        ) : viewMode === "index" && indexMd ? (
          <div className="bg-card border border-border rounded-2xl p-6 shadow-sahara max-w-4xl">
            <WikiContent markdown={indexMd} />
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_17rem] xl:grid-cols-[minmax(0,1fr)_19rem] gap-6 items-start">
            {/* Main column */}
            <div className="min-w-0 flex flex-col gap-4">
              {/* Search card */}
              <div className="bg-card border border-border rounded-xl p-3 flex flex-col sm:flex-row gap-2">
                <div className="relative flex-1">
                  <span className="material-symbols-outlined text-lg text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2">
                    {contentLoading ? "progress_activity" : "search"}
                  </span>
                  <input
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder={
                      searchMode === "content"
                        ? "Tìm trong nội dung trang (theo nghĩa)..."
                        : "Tìm theo tên trang..."
                    }
                    className="h-10 w-full pl-10 pr-8 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary/50 placeholder:text-muted-foreground/60"
                  />
                  {query && (
                    <button
                      onClick={() => setQuery("")}
                      className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground cursor-pointer"
                    >
                      <span className="material-symbols-outlined text-base">close</span>
                    </button>
                  )}
                </div>
                <div className="flex gap-2">
                  <div className="flex h-10 rounded-lg border border-border bg-muted/40 p-0.5 text-sm shrink-0">
                    {(
                      [
                        { id: "title", label: "Tên trang" },
                        { id: "content", label: "Nội dung" },
                      ] as const
                    ).map((m) => (
                      <button
                        key={m.id}
                        onClick={() => setSearchMode(m.id)}
                        className={cn(
                          "px-3 rounded-md font-medium transition-colors cursor-pointer",
                          searchMode === m.id
                            ? "bg-background text-foreground shadow-xs"
                            : "text-muted-foreground hover:text-foreground",
                        )}
                      >
                        {m.label}
                      </button>
                    ))}
                  </div>
                  <label className="flex h-10 items-center gap-2 px-3 rounded-lg border border-border bg-background text-sm shrink-0">
                    <span className="text-muted-foreground hidden md:inline">Sắp xếp</span>
                    <select
                      value={sort}
                      onChange={(e) => setSort(e.target.value as SortKey)}
                      className="bg-transparent font-medium focus:outline-none cursor-pointer"
                    >
                      <option value="updated_desc">
                        {searchMode === "content" && trimmedQuery ? "Liên quan nhất" : "Cập nhật mới nhất"}
                      </option>
                      <option value="updated_asc">Cập nhật cũ nhất</option>
                      <option value="title">Tên A → Z</option>
                      <option value="sources">Nhiều tài liệu nguồn</option>
                    </select>
                  </label>
                </div>
              </div>

              {/* Count + scope pills */}
              <div className="flex items-center gap-3 flex-wrap">
                <p className="text-sm text-muted-foreground mr-auto">
                  Trang wiki:{" "}
                  <span className="font-semibold text-foreground tabular-nums">{filteredPages.length}</span> trang
                  {contentError && <span className="ml-2 text-destructive">· {contentError}</span>}
                </p>
                <div className="flex items-center gap-1.5">
                  {(
                    [
                      { id: "all", label: "Tất cả", count: scopeCounts.all },
                      { id: "global", label: "Toàn công ty", count: scopeCounts.global },
                      { id: "department", label: "Phòng ban", count: scopeCounts.department },
                    ] as const
                  ).map((s) => {
                    const active = scopeFilter === s.id;
                    return (
                      <button
                        key={s.id}
                        onClick={() => setScopeFilter(s.id)}
                        className={cn(
                          "px-3 py-1 rounded-full text-xs font-medium border transition-colors cursor-pointer",
                          active
                            ? "bg-primary text-primary-foreground border-primary"
                            : "bg-background border-border text-muted-foreground hover:text-foreground",
                        )}
                      >
                        {s.label} <span className="tabular-nums opacity-80">({s.count})</span>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* List */}
              {filteredPages.length === 0 ? (
                <EmptyState
                  icon="search_off"
                  title="Không có trang phù hợp"
                  description={
                    contentLoading
                      ? "Đang tìm..."
                      : trimmedQuery
                        ? `Không có kết quả cho "${trimmedQuery}"`
                        : "Thử bỏ bớt bộ lọc."
                  }
                />
              ) : (
                <div className="bg-card border border-border rounded-xl divide-y divide-border">
                  {filteredPages.slice(0, shown).map((p, i) => {
                    const isNew = p.updated_at && now - new Date(p.updated_at).getTime() < NEW_WINDOW_MS;
                    return (
                      <div
                        key={`${p.slug}-${p.scope_type}-${p.scope_id ?? ""}`}
                        className="group px-5 py-4 hover:bg-muted/30 transition-colors"
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          <span className="text-sm text-muted-foreground tabular-nums shrink-0">{i + 1}.</span>
                          <Link
                            href={pageHref(p)}
                            className="font-semibold text-[15px] text-foreground hover:text-primary truncate transition-colors"
                            title={p.title}
                          >
                            {p.title}
                          </Link>
                          {isNew && (
                            <span className="shrink-0 px-1.5 py-px rounded text-[10px] font-semibold bg-emerald-500/15 text-emerald-700 dark:text-emerald-400">
                              Mới
                            </span>
                          )}
                          <button
                            type="button"
                            onClick={() => copyLink(p)}
                            title="Sao chép liên kết"
                            className="shrink-0 text-muted-foreground/60 hover:text-primary opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer"
                          >
                            <span className="material-symbols-outlined" style={{ fontSize: 16 }}>link</span>
                          </button>
                        </div>
                        {p.summary && (
                          <p className="mt-1 text-sm text-muted-foreground line-clamp-2">{p.summary}</p>
                        )}
                        <div className="mt-2.5 flex items-center gap-x-4 gap-y-1.5 flex-wrap text-xs text-muted-foreground">
                          <span className="flex items-center gap-1.5">
                            Độ hoàn thiện <WikiStatusBadge status={p.status} />
                          </span>
                          <span>
                            Phạm vi <span className="text-foreground/80 font-medium">{scopeLabel(p)}</span>
                          </span>
                          <span>
                            Cập nhật{" "}
                            <span className="text-foreground/80 font-medium">
                              {p.updated_at ? new Date(p.updated_at).toLocaleDateString("vi-VN") : "—"}
                            </span>
                          </span>
                          <span>
                            Phiên bản <span className="text-foreground/80 font-medium">v{p.version}</span>
                          </span>
                          <span>
                            Loại{" "}
                            <span className="text-foreground/80 font-medium">
                              {p.knowledge_type_slugs[0] ?? wikiTypeGroupLabel(p.page_type)}
                            </span>
                          </span>
                          {p.source_ids.length > 0 && (
                            <span className="flex items-center gap-1">
                              <span className="material-symbols-outlined" style={{ fontSize: 14 }}>description</span>
                              {p.source_ids.length} tài liệu nguồn
                            </span>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
              {filteredPages.length > shown && (
                <button
                  onClick={() => setShown((n) => n + PAGE_CHUNK)}
                  className="self-center px-4 py-1.5 rounded-lg text-sm font-medium border border-border bg-background hover:bg-muted cursor-pointer"
                >
                  Xem thêm ({filteredPages.length - shown} trang)
                </button>
              )}
            </div>

            {/* Facet sidebar */}
            <aside className="bg-card border border-border rounded-xl px-4 pt-3 pb-1 lg:sticky lg:top-0 lg:max-h-[calc(100vh-7rem)] lg:overflow-y-auto">
              <div className="flex items-center justify-between pb-2">
                <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                  Tra cứu nhanh
                </span>
                {(activeFacetCount > 0 || scopeFilter !== "all") && (
                  <button
                    onClick={clearFilters}
                    className="text-xs font-medium text-primary hover:underline cursor-pointer"
                  >
                    Xoá lọc
                  </button>
                )}
              </div>
              <FacetGroup
                title="Phòng ban / dự án"
                options={facetOptions.dept}
                selected={facets.dept}
                onToggle={(v) => toggleFacet("dept", v)}
                searchable
                searchPlaceholder="Tìm phòng ban..."
              />
              <FacetGroup
                title="Độ hoàn thiện"
                options={facetOptions.status}
                selected={facets.status}
                onToggle={(v) => toggleFacet("status", v)}
              />
              <FacetGroup
                title="Loại tri thức"
                options={facetOptions.kt}
                selected={facets.kt}
                onToggle={(v) => toggleFacet("kt", v)}
              />
              <FacetGroup
                title="Loại trang"
                options={facetOptions.type}
                selected={facets.type}
                onToggle={(v) => toggleFacet("type", v)}
                defaultOpen={false}
              />
              <FacetGroup
                title="Văn bản nguồn"
                options={facetOptions.source}
                selected={facets.source}
                onToggle={(v) => toggleFacet("source", v)}
                searchable
                searchPlaceholder="Tìm văn bản..."
                defaultOpen={false}
              />
            </aside>
          </div>
        )}
      </div>

      <WikiSearchDialog open={searchOpen} onOpenChange={setSearchOpen} />
      {dialogMode && (
        <WikiCreatePageDialog
          open={createOpen}
          onOpenChange={(o) => {
            setCreateOpen(o);
            if (!o) {
              setDialogScope(null);
              setPrefillTitle("");
            }
          }}
          mode={dialogMode}
          defaultScope={dialogTargetScope}
          scopes={scopes}
          getCreateModeForScope={(s) =>
            getCreateModeForScope({
              scope_type: s.scope_type,
              scope_id: s.scope_id ?? null,
            })
          }
          defaultTitle={prefillTitle}
        />
      )}
    </>
  );
}
