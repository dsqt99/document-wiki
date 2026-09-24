"use client";

import React from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { WikiPageSummary, WikiScope } from "@/types/wiki";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { WikiPageTree } from "@/components/wiki/wiki-page-tree";
import { WikiTopFilterBar } from "@/components/wiki/wiki-top-filter-bar";
import { WikiContent } from "@/components/wiki/wiki-content";
import { WikiTypeBadge, wikiTypeGroupLabel } from "@/components/wiki/wiki-type-badge";
import { ScopeBadge } from "@/components/shared/scope-badge";
import { WikiSearchDialog } from "@/components/wiki/wiki-search-dialog";
import { WikiScopeSwitcher } from "@/components/wiki/wiki-scope-switcher";
import { WikiCreatePageDialog } from "@/components/wiki/wiki-create-page-dialog";
import { EmptyState } from "@/components/shared/empty-state";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";
import { WikiSourceItem, computeSourceStats } from "@/lib/wiki-store";
import { parseSourceLegalMeta, LegalCategory } from "@/components/knowledge/knowledge-table/utils";
import { SourceArticlesDrawer } from "@/components/knowledge/knowledge-table/source-articles-drawer";

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

const TYPE_TABS = ["all", "entity", "concept", "topic", "source"] as const;

export default function WikiIndexPage() {
  const searchParams = useSearchParams();
  const urlScopeType = searchParams.get("scope_type");
  const urlScopeId = searchParams.get("scope_id");

  const { user, getWorkspaceRole, hasPermission } = useAuth();

  const [indexMd, setIndexMd] = React.useState<string | null>(null);
  const [allPages, setAllPages] = React.useState<WikiPageSummary[]>([]);
  const [sources, setSources] = React.useState<WikiSourceItem[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [searchOpen, setSearchOpen] = React.useState(false);
  const [createOpen, setCreateOpen] = React.useState(false);
  const [prefillTitle, setPrefillTitle] = React.useState("");
  const [activeTab, setActiveTab] = React.useState<string>("all");
  const [scopes, setScopes] = React.useState<WikiScope[]>([]);

  // View mode: library (Tủ sách) vs pages (Tất cả trang) vs index (Mục lục tổng hợp)
  const [viewMode, setViewMode] = React.useState<"library" | "pages" | "index">("library");
  const [libraryCategoryFilter, setLibraryCategoryFilter] = React.useState<LegalCategory>("all");
  const [librarySearch, setLibrarySearch] = React.useState("");
  const [selectedDrawerSource, setSelectedDrawerSource] = React.useState<WikiSourceItem | null>(null);

  React.useEffect(() => {
    if (searchParams.get("new") === "1") {
      setPrefillTitle(searchParams.get("title") || "");
      setCreateOpen(true);
    }
  }, [searchParams]);

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

  React.useEffect(() => {
    setLoading(true);
    const qs = selectedScope.scope_id
      ? `scope_type=${selectedScope.scope_type}&scope_id=${selectedScope.scope_id}`
      : `scope_type=${selectedScope.scope_type}`;
    Promise.all([
      api<{ content_md: string }>(`/api/wiki/index?${qs}`),
      api<WikiPageSummary[]>(`/api/wiki/pages?${qs}`),
      api<{ items: WikiSourceItem[] }>("/api/sources?status=ready&page_size=1000"),
    ])
      .then(([idx, pages, srcData]) => {
        setIndexMd(idx.content_md || null);
        const filtered = Array.isArray(pages)
          ? pages.filter((p) => p.page_type !== "index" && p.page_type !== "log")
          : [];
        setAllPages(filtered);
        setSources(srcData?.items || []);
      })
      .catch(() => {
        setIndexMd(null);
        setAllPages([]);
        setSources([]);
      })
      .finally(() => setLoading(false));
  }, [selectedScope.scope_type, selectedScope.scope_id]);

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
        if (
          hasPermission("wiki:write:own_dept") &&
          user.department_ids.includes(sid)
        ) {
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

  const [dialogScope, setDialogScope] = React.useState<WikiScope | null>(null);
  const dialogTargetScope: WikiScope = dialogScope ?? selectedScope;
  const dialogMode = getCreateModeForScope(dialogTargetScope);

  // Stats
  const totalPages = allPages.length;
  const typeCounts = React.useMemo(() => {
    const c: Record<string, number> = {};
    for (const p of allPages) c[p.page_type] = (c[p.page_type] ?? 0) + 1;
    return c;
  }, [allPages]);
  const lastUpdated = allPages[0]?.updated_at;

  const sourceStats = React.useMemo(() => {
    return computeSourceStats(allPages, sources);
  }, [allPages, sources]);

  const sourceArticleCountMap = React.useMemo(() => {
    const map = new Map<string, number>();
    for (const s of sourceStats.sources) {
      map.set(s.id, s.count);
    }
    return map;
  }, [sourceStats]);

  const categoryCounts = React.useMemo(() => {
    const counts: Record<LegalCategory, number> = {
      all: sources.length,
      luat: 0,
      nghi_dinh: 0,
      thong_tu: 0,
      vbhn: 0,
      quyet_dinh: 0,
      other: 0,
      khac: 0,
    };
    for (const s of sources) {
      const meta = parseSourceLegalMeta(s);
      counts[meta.category] = (counts[meta.category] || 0) + 1;
    }
    return counts;
  }, [sources]);

  const filteredLibrarySources = React.useMemo(() => {
    let list = sources;
    if (libraryCategoryFilter !== "all") {
      list = list.filter((s) => {
        const meta = parseSourceLegalMeta(s);
        return meta.category === libraryCategoryFilter;
      });
    }
    if (librarySearch.trim()) {
      const q = librarySearch.trim().toLowerCase();
      list = list.filter((s) => {
        const meta = parseSourceLegalMeta(s);
        const text = `${s.title || ""} ${s.file_name || ""} ${meta.docNumber || ""} ${meta.authority || ""}`.toLowerCase();
        return text.includes(q);
      });
    }
    return list;
  }, [sources, libraryCategoryFilter, librarySearch]);

  const displayPages = React.useMemo(() => {
    const list = activeTab === "all"
      ? allPages
      : allPages.filter((p) => p.page_type === activeTab);
    return list.slice(0, 36);
  }, [allPages, activeTab]);

  return (
    <>
      <PageHeader
        title="Knowledge Wiki"
        description="Tra cứu và tổng hợp tri thức chuẩn hóa từ các văn bản quy phạm pháp luật."
        action={
          <div className="flex items-center gap-2">
            <WikiScopeSwitcher current={selectedScope} />
            <Button
              variant="outline"
              onClick={() => setSearchOpen(true)}
              className="gap-2"
            >
              <span className="material-symbols-outlined text-base">search</span>
              Search
              <kbd className="hidden sm:inline-block ml-1 px-1.5 py-0.5 rounded border border-border text-xs font-mono text-muted-foreground">
                ⌘K
              </kbd>
            </Button>
            {createMode && (
              <Button
                variant="outline"
                onClick={() => {
                  setDialogScope(null);
                  setCreateOpen(true);
                }}
                className="gap-2"
                title={
                  createMode === "direct"
                    ? `Create a new page in ${selectedScope.name}`
                    : `Propose a new page in ${selectedScope.name} (reviewer approves)`
                }
              >
                <span className="material-symbols-outlined text-base">add</span>
                {createMode === "direct" ? "New page" : "Propose page"}
              </Button>
            )}
            {user && (
              <Link
                href="/wiki/review"
                className="inline-flex h-8 items-center gap-1.5 px-2.5 rounded-lg text-sm font-medium border border-border bg-background hover:bg-muted transition-colors"
                title="Drafts you authored and drafts waiting for your review"
              >
                <span className="material-symbols-outlined" style={{ fontSize: 16 }}>edit_note</span>
                Contributions
              </Link>
            )}
            <Link
              href="/wiki/graph"
              className="inline-flex h-8 items-center gap-1.5 px-2.5 rounded-lg text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
            >
              <span className="material-symbols-outlined" style={{ fontSize: 16 }}>hub</span>
              Graph View
            </Link>
          </div>
        }
      />

      <div className="flex-1 flex gap-0 -mx-6 md:-mx-8 lg:-mx-10 -mb-6 md:-mb-8 lg:-mb-10 min-h-0 border-t border-border">
        {/* Page Tree */}
        <WikiPageTree
          groupByScope
          activeScope={{
            scope_type: selectedScope.scope_type,
            scope_id: selectedScope.scope_id,
          }}
          getCreateModeForScope={(scope) =>
            getCreateModeForScope({
              scope_type: scope.scope_type,
              scope_id: scope.scope_id,
            })
          }
          onCreatePage={(scope) => {
            const match = scopes.find(
              (s) =>
                s.scope_type === scope.scope_type &&
                (s.scope_id ?? null) === (scope.scope_id ?? null),
            );
            setDialogScope(
              match ?? {
                scope_type: scope.scope_type,
                scope_id: scope.scope_id,
                name: scope.scope_type,
              },
            );
            setCreateOpen(true);
          }}
        />

        {/* Content Area */}
        <div className="flex-1 overflow-y-auto min-w-0">
          <WikiTopFilterBar pages={allPages} />

          <div className="px-8 py-6">
            {loading ? (
              <div className="flex items-center justify-center h-48">
                <span className="material-symbols-outlined text-3xl text-muted-foreground animate-spin">
                  progress_activity
                </span>
              </div>
            ) : (
              <>
                {/* Stats Bar */}
                {totalPages > 0 && (
                  <div className="flex flex-wrap items-center gap-3 mb-6">
                    <div className="flex items-center gap-2 bg-card border border-border rounded-xl px-4 py-2.5 shadow-sahara">
                      <span className="material-symbols-outlined text-base text-primary">local_library</span>
                      <span className="text-sm font-bold text-foreground">{sources.length}</span>
                      <span className="text-xs text-muted-foreground">Văn bản</span>
                    </div>

                    <div className="flex items-center gap-2 bg-card border border-border rounded-xl px-4 py-2.5 shadow-sahara">
                      <span className="material-symbols-outlined text-base text-primary">article</span>
                      <span className="text-sm font-bold text-foreground">{totalPages}</span>
                      <span className="text-xs text-muted-foreground">Trang Wiki</span>
                    </div>

                    <div className="flex items-center gap-2 bg-card border border-border rounded-xl px-3 py-2.5 shadow-sahara">
                      <span className="material-symbols-outlined text-base text-emerald-500">gavel</span>
                      <span className="text-xs font-semibold text-foreground">{sourceStats.articlesCount}</span>
                      <span className="text-xs text-muted-foreground">Điều khoản</span>
                    </div>

                    {lastUpdated && (
                      <div className="flex items-center gap-2 bg-card border border-border rounded-xl px-4 py-2.5 shadow-sahara ml-auto">
                        <span className="material-symbols-outlined text-base text-muted-foreground">schedule</span>
                        <span className="text-xs text-muted-foreground">
                          Cập nhật {new Date(lastUpdated).toLocaleDateString("vi-VN")}
                        </span>
                      </div>
                    )}
                  </div>
                )}

                {/* View Mode Switcher Tabs */}
                <div className="flex items-center gap-2 border-b border-border mb-6">
                  <button
                    onClick={() => setViewMode("library")}
                    className={cn(
                      "flex items-center gap-2 px-4 py-3 text-xs font-semibold border-b-2 transition-all cursor-pointer",
                      viewMode === "library"
                        ? "border-primary text-primary"
                        : "border-transparent text-muted-foreground hover:text-foreground"
                    )}
                  >
                    <span className="material-symbols-outlined text-[17px]">local_library</span>
                    <span>Tủ sách Văn bản pháp luật</span>
                    <span className={cn(
                      "px-1.5 py-0.2 rounded-full text-[10px] font-bold tabular-nums",
                      viewMode === "library" ? "bg-primary/15 text-primary" : "bg-muted text-muted-foreground"
                    )}>
                      {sources.length}
                    </span>
                  </button>

                  <button
                    onClick={() => setViewMode("pages")}
                    className={cn(
                      "flex items-center gap-2 px-4 py-3 text-xs font-semibold border-b-2 transition-all cursor-pointer",
                      viewMode === "pages"
                        ? "border-primary text-primary"
                        : "border-transparent text-muted-foreground hover:text-foreground"
                    )}
                  >
                    <span className="material-symbols-outlined text-[17px]">format_list_bulleted</span>
                    <span>Tất cả trang Wiki</span>
                    <span className={cn(
                      "px-1.5 py-0.2 rounded-full text-[10px] font-bold tabular-nums",
                      viewMode === "pages" ? "bg-primary/15 text-primary" : "bg-muted text-muted-foreground"
                    )}>
                      {totalPages}
                    </span>
                  </button>

                  {indexMd && (
                    <button
                      onClick={() => setViewMode("index")}
                      className={cn(
                        "flex items-center gap-2 px-4 py-3 text-xs font-semibold border-b-2 transition-all cursor-pointer",
                        viewMode === "index"
                          ? "border-primary text-primary"
                          : "border-transparent text-muted-foreground hover:text-foreground"
                      )}
                    >
                      <span className="material-symbols-outlined text-[17px]">menu_book</span>
                      <span>Mục lục tổng hợp (Markdown)</span>
                    </button>
                  )}
                </div>

                {/* VIEW 1: TỦ SÁCH VĂN BẢN (LIBRARY) */}
                {viewMode === "library" && (
                  <div className="space-y-5">
                    {/* Filters & Search Bar */}
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      {/* Legal Category Filter Pills */}
                      <div className="flex items-center gap-1.5 overflow-x-auto pb-1 scrollbar-none">
                        {(
                          [
                            { id: "all", label: "Tất cả", icon: "library_books" },
                            { id: "luat", label: "Luật", icon: "gavel" },
                            { id: "nghi_dinh", label: "Nghị định", icon: "policy" },
                            { id: "thong_tu", label: "Thông tư", icon: "description" },
                            { id: "vbhn", label: "Văn bản hợp nhất", icon: "integration_instructions" },
                            { id: "quyet_dinh", label: "Quyết định", icon: "verified" },
                          ] as const
                        ).map((tab) => {
                          const count = categoryCounts[tab.id] ?? 0;
                          if (tab.id !== "all" && count === 0) return null;
                          const active = libraryCategoryFilter === tab.id;
                          return (
                            <button
                              key={tab.id}
                              type="button"
                              onClick={() => setLibraryCategoryFilter(tab.id)}
                              className={cn(
                                "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-all cursor-pointer shrink-0 shadow-2xs",
                                active
                                  ? "bg-primary text-primary-foreground border-primary font-semibold shadow-xs"
                                  : "bg-card border-border text-muted-foreground hover:text-foreground hover:bg-secondary/70"
                              )}
                            >
                              <span className="material-symbols-outlined text-[14px]">{tab.icon}</span>
                              <span>{tab.label}</span>
                              <span
                                className={cn(
                                  "px-1.5 py-0.2 rounded-full text-[10px] tabular-nums font-semibold",
                                  active
                                    ? "bg-primary-foreground/20 text-primary-foreground"
                                    : "bg-muted text-muted-foreground"
                                )}
                              >
                                {count}
                              </span>
                            </button>
                          );
                        })}
                      </div>

                      {/* Search in Library */}
                      <div className="relative min-w-[240px] max-w-[320px]">
                        <span className="material-symbols-outlined text-sm text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2">
                          search
                        </span>
                        <input
                          type="text"
                          value={librarySearch}
                          onChange={(e) => setLibrarySearch(e.target.value)}
                          placeholder="Tìm theo số hiệu, tên văn bản..."
                          className="h-8 w-full pl-9 pr-8 text-xs rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary/50 placeholder:text-muted-foreground/60"
                        />
                        {librarySearch && (
                          <button
                            onClick={() => setLibrarySearch("")}
                            className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                          >
                            <span className="material-symbols-outlined text-xs">close</span>
                          </button>
                        )}
                      </div>
                    </div>

                    {/* Cards Grid */}
                    {filteredLibrarySources.length === 0 ? (
                      <EmptyState
                        icon="search_off"
                        title="Không tìm thấy văn bản phù hợp"
                        description={librarySearch ? `Không có kết quả khớp với "${librarySearch}"` : "Chưa có văn bản nào trong nhóm này."}
                      />
                    ) : (
                      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                        {filteredLibrarySources.map((source) => {
                          const meta = parseSourceLegalMeta(source);
                          const artCount = sourceArticleCountMap.get(source.id) || 0;

                          return (
                            <div
                              key={source.id}
                              className="group bg-card border border-border rounded-xl p-5 hover:border-primary/50 hover:shadow-sahara transition-all flex flex-col justify-between"
                            >
                              <div>
                                {/* Header: Badge & Doc Number & Article Count */}
                                <div className="flex items-center justify-between gap-2 mb-3">
                                  <div className="flex items-center gap-1.5 flex-wrap">
                                    <span
                                      className={cn(
                                        "text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-md border",
                                        meta.badgeBg,
                                        meta.badgeBorder
                                      )}
                                      style={{ color: meta.badgeColor }}
                                    >
                                      {meta.badgeLabel}
                                    </span>
                                    {meta.docNumber && (
                                      <span className="text-[11px] font-mono font-semibold px-2 py-0.5 rounded-md bg-muted/80 text-foreground border border-border/80">
                                        Số: {meta.docNumber}
                                      </span>
                                    )}
                                  </div>

                                  <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-primary bg-primary/10 px-2 py-0.5 rounded-full border border-primary/20 shrink-0">
                                    <span className="material-symbols-outlined text-[13px]">menu_book</span>
                                    {artCount} Điều
                                  </span>
                                </div>

                                {/* Title */}
                                <Link
                                  href={`/wiki/source/${source.id}`}
                                  className="font-heading text-sm font-semibold text-foreground group-hover:text-primary transition-colors line-clamp-2 mb-2 leading-snug block"
                                  title={source.title}
                                >
                                  {source.title}
                                </Link>

                                {/* Metadata */}
                                <div className="flex items-center gap-2.5 text-xs text-muted-foreground flex-wrap mb-4">
                                  {meta.issuingAuthority && (
                                    <span className="flex items-center gap-1 font-medium text-foreground/80">
                                      <span className="material-symbols-outlined text-[13px] text-primary/70">account_balance</span>
                                      {meta.issuingAuthority}
                                    </span>
                                  )}
                                  {meta.docDate && (
                                    <span className="flex items-center gap-1">
                                      <span className="material-symbols-outlined text-[13px]">calendar_today</span>
                                      {meta.docDate}
                                    </span>
                                  )}
                                </div>
                              </div>

                              {/* Actions Footer */}
                              <div className="flex items-center gap-2 pt-3 border-t border-border/60">
                                <Link
                                  href={`/wiki/source/${source.id}`}
                                  className="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-primary/10 text-primary hover:bg-primary/20 transition-colors"
                                >
                                  <span className="material-symbols-outlined text-sm">visibility</span>
                                  Tổng quan
                                </Link>
                                <button
                                  type="button"
                                  onClick={() => setSelectedDrawerSource(source)}
                                  className="inline-flex items-center justify-center gap-1 px-3 py-1.5 rounded-lg text-xs font-semibold border border-border bg-background hover:bg-accent text-foreground transition-colors cursor-pointer"
                                  title="Xem danh sách các Điều trong văn bản"
                                >
                                  <span className="material-symbols-outlined text-sm">format_list_bulleted</span>
                                  Tra cứu Điều
                                </button>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                )}

                {/* VIEW 2: TẤT CẢ TRANG WIKI (PAGES GRID) */}
                {viewMode === "pages" && (
                  <div>
                    {/* Type tabs */}
                    <div className="flex items-center gap-1 mb-5 border-b border-border">
                      {TYPE_TABS.map((tab) => {
                        const count = tab === "all"
                          ? totalPages
                          : typeCounts[tab] ?? 0;
                        if (tab !== "all" && count === 0) return null;
                        return (
                          <button
                            key={tab}
                            onClick={() => setActiveTab(tab)}
                            className={`px-3 py-2 text-xs font-medium capitalize border-b-2 transition-colors cursor-pointer ${
                              activeTab === tab
                                ? "border-primary text-primary"
                                : "border-transparent text-muted-foreground hover:text-foreground"
                            }`}
                          >
                            {tab === "all" ? "All" : wikiTypeGroupLabel(tab)}
                            <span className="ml-1.5 tabular-nums text-muted-foreground">
                              {count}
                            </span>
                          </button>
                        );
                      })}
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                      {displayPages.map((page) => {
                        const cardHref =
                          page.scope_type && page.scope_type !== "global" && page.scope_id
                            ? `/wiki/${page.slug}?scopeType=${page.scope_type}&scopeId=${page.scope_id}`
                            : `/wiki/${page.slug}`;
                        return (
                          <Link
                            key={`${page.slug}-${page.scope_type ?? "global"}-${page.scope_id ?? "none"}`}
                            href={cardHref}
                            className="group block bg-card border border-border rounded-xl p-4 hover:border-primary/40 hover:shadow-sahara transition-all"
                          >
                            <div className="flex items-start justify-between gap-2 mb-2">
                              <div className="flex items-center gap-1.5 flex-wrap">
                                <WikiTypeBadge type={page.page_type} />
                                {page.scope_type && page.scope_type !== "global" && (
                                  <ScopeBadge scopeType={page.scope_type} scopeId={page.scope_id} />
                                )}
                              </div>
                              <span className="text-xs text-muted-foreground shrink-0">
                                v{page.version}
                              </span>
                            </div>
                            <h3 className="font-heading text-sm font-semibold text-foreground group-hover:text-primary transition-colors mb-1">
                              {page.title}
                            </h3>
                            {page.summary && (
                              <p className="text-xs text-muted-foreground line-clamp-2">
                                {page.summary}
                              </p>
                            )}
                            <p className="text-xs text-muted-foreground mt-3">
                              {new Date(page.updated_at).toLocaleDateString("vi-VN")}
                            </p>
                          </Link>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* VIEW 3: MỤC LỤC TỔNG HỢP (MARKDOWN INDEX) */}
                {viewMode === "index" && indexMd && (
                  <div className="bg-card border border-border rounded-2xl p-6 shadow-sahara">
                    <WikiContent markdown={indexMd} />
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>

      {/* Modal Drawer to Browse Articles of Selected Document */}
      {selectedDrawerSource && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-xs p-4 animate-in fade-in duration-200">
          <div className="bg-card border border-border rounded-2xl shadow-2xl w-full max-w-4xl max-h-[85vh] flex flex-col overflow-hidden animate-in zoom-in-95 duration-200">
            <div className="px-6 py-4 border-b border-border flex items-center justify-between gap-3 bg-muted/20">
              <div className="min-w-0">
                <span className="text-xs font-bold text-primary uppercase tracking-wider block mb-1">
                  Tra cứu danh sách Điều
                </span>
                <h2 className="text-sm font-semibold text-foreground truncate" title={selectedDrawerSource.title}>
                  {selectedDrawerSource.title}
                </h2>
              </div>
              <button
                onClick={() => setSelectedDrawerSource(null)}
                className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors cursor-pointer"
              >
                <span className="material-symbols-outlined text-lg">close</span>
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-4">
              <SourceArticlesDrawer
                source={selectedDrawerSource}
                onClose={() => setSelectedDrawerSource(null)}
              />
            </div>
          </div>
        </div>
      )}

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
