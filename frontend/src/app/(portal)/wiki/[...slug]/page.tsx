"use client";

import React from "react";
import { useParams, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { WikiPageDetail, DraftResponse } from "@/types/wiki";
import { WikiPageTree } from "@/components/wiki/wiki-page-tree";
import { WikiContent } from "@/components/wiki/wiki-content";
import { WikiSidebarRight } from "@/components/wiki/wiki-backlinks";
import { WikiEditor } from "@/components/wiki/wiki-editor";
import { WikiDraftBanner } from "@/components/wiki/wiki-draft-banner";
import { WikiTypeBadge, wikiTypeGroupLabel } from "@/components/wiki/wiki-type-badge";
import { ScopeBadge } from "@/components/shared/scope-badge";
import { WikiSearchDialog } from "@/components/wiki/wiki-search-dialog";
import { WikiCreatePageDialog } from "@/components/wiki/wiki-create-page-dialog";
import { WikiStatusBadge, WikiStatus } from "@/components/wiki/wiki-status-badge";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { WikiScope } from "@/types/wiki";
import { EmptyState } from "@/components/shared/empty-state";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import Link from "next/link";
import {
  getCachedPageDetail,
  setCachedPageDetail,
  getCachedSourceData,
  setCachedSourceData,
  useWikiStore,
} from "@/lib/wiki-store";

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

export default function WikiPageViewer() {
  const params = useParams();
  const searchParams = useSearchParams();
  const { user, hasPermission } = useAuth();
  const { treeCollapsed, infoCollapsed, setTreeCollapsed, setInfoCollapsed } = useWikiStore();
  const readingMode = treeCollapsed && infoCollapsed;

  const slugParts = Array.isArray(params.slug) ? params.slug : [params.slug ?? ""];
  const initialSlug = slugParts.join("/");
  const [currentSlug, setCurrentSlug] = React.useState(initialSlug);
  const [prevInitialSlug, setPrevInitialSlug] = React.useState(initialSlug);
  if (initialSlug !== prevInitialSlug) {
    setPrevInitialSlug(initialSlug);
    setCurrentSlug(initialSlug);
  }
  const fullSlug = currentSlug;

  const scopeType = searchParams.get("scopeType") || undefined;
  const scopeId = searchParams.get("scopeId") || undefined;
  const isScoped = !!scopeType && scopeType !== "global";
  const isProjectScoped = false;

  const scopeLinkSuffix = isScoped
    ? `?scopeType=${scopeType}&scopeId=${scopeId}`
    : "";

  // Support browser back/forward buttons smoothly
  React.useEffect(() => {
    const onPopState = () => {
      const match = window.location.pathname.match(/^\/wiki\/(.+)$/);
      if (match) {
        setCurrentSlug(decodeURIComponent(match[1]));
      }
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  const handlePageSelect = React.useCallback(
    (newSlug: string) => {
      if (newSlug === currentSlug) return;
      setCurrentSlug(newSlug);
      window.history.pushState(null, "", `/wiki/${newSlug}${scopeLinkSuffix}`);
    },
    [currentSlug, scopeLinkSuffix]
  );

  const currentSlugParts = currentSlug.split("/");
  const isSourceView = currentSlugParts[0] === "source" && currentSlugParts.length === 2;
  const sourceId = isSourceView ? currentSlugParts[1] : null;

  // Where "back" navigates. Projects keep their dedicated workspace page;
  // department-scoped pages return to the wiki landing with the scope preserved
  // so the user lands back on that department's tree+index, not global.
  const backHref = isProjectScoped ? "/workspaces" : "/wiki/law";

  // Look up the display name for the current page's scope so the scope
  // switcher trigger reads e.g. "Phòng Nhân sự" rather than just "department".
  const [scopes, setScopes] = React.useState<WikiScope[]>([]);
  React.useEffect(() => {
    api<WikiScope[]>("/api/wiki/my-scopes")
      .then((s) => setScopes(Array.isArray(s) ? s : []))
      .catch(() => setScopes([]));
  }, []);
  const currentScope: WikiScope = React.useMemo(() => {
    if (isScoped && scopeType && scopeId) {
      const match = scopes.find(
        (s) => s.scope_type === scopeType && s.scope_id === scopeId,
      );
      if (match) return match;
      return { scope_type: scopeType, scope_id: scopeId, name: scopeType };
    }
    return { scope_type: "global", scope_id: null, name: "Global" };
  }, [isScoped, scopeType, scopeId, scopes]);

  const [page, setPage] = React.useState<WikiPageDetail | null>(null);
  const [sourceData, setSourceData] = React.useState<any | null>(null);
  const [citations, setCitations] = React.useState<any[]>([]);
  const [sourcesExpanded, setSourcesExpanded] = React.useState(false);
  const [sourcesForSlug, setSourcesForSlug] = React.useState(currentSlug);
  if (sourcesForSlug !== currentSlug) {
    setSourcesForSlug(currentSlug);
    setSourcesExpanded(false);
  }
  const [notFound, setNotFound] = React.useState(false);
  const [loading, setLoading] = React.useState(true);
  const [searchOpen, setSearchOpen] = React.useState(false);
  const [createOpen, setCreateOpen] = React.useState(false);
  const [dialogScope, setDialogScope] = React.useState<WikiScope | null>(null);
  // Author-side: the draft the user is currently resubmitting (needs_revision).
  // When set, the page replaces the read view with a WikiEditor pre-filled
  // with the draft's previous content.
  const [editingDraft, setEditingDraft] = React.useState<DraftResponse | null>(null);

  // Edit mode
  const [mode, setMode] = React.useState<"view" | "edit">("view");

  // Branches context for contributions
  const [branches, setBranches] = React.useState<any[]>([]);
  const [activeBranch, setActiveBranch] = React.useState<any | null>(null);
  const [branchesLoading, setBranchesLoading] = React.useState(false);
  const [showCreateBranch, setShowCreateBranch] = React.useState(false);
  const [newBranchName, setNewBranchName] = React.useState("");
  const [newBranchDesc, setNewBranchDesc] = React.useState("");

  const loadBranches = React.useCallback(async () => {
    if (!user) return;
    setBranchesLoading(true);
    try {
      const scopeQs = isScoped ? `&scope_type=${scopeType}&scope_id=${scopeId}` : "";
      const list = await api<any[]>(`/api/wiki/branches?mine=true&status=draft${scopeQs}`);
      setBranches(list);
      if (list.length > 0) {
        setActiveBranch(list[0]);
      } else {
        const today = new Date().toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric" });
        const defaultName = `Đóng góp ngày ${today}`;
        const newB = await api<any>("/api/wiki/branches", {
          method: "POST",
          body: {
            name: defaultName,
            description: "Nhánh đóng góp tự động được tạo khi chỉnh sửa tài liệu.",
            scope_type: isScoped ? scopeType : "global",
            scope_id: isScoped ? scopeId : undefined,
          },
        });
        setBranches([newB]);
        setActiveBranch(newB);
      }
    } catch {
      setBranches([]);
      setActiveBranch(null);
    } finally {
      setBranchesLoading(false);
    }
  }, [user, isScoped, scopeType, scopeId]);

  // Pending drafts (for editors/admins)
  const [drafts, setDrafts] = React.useState<DraftResponse[]>([]);

  // ---------------------------------------------------------------------------
  // Permission helpers
  // ---------------------------------------------------------------------------
  // Workspace role has been deprecated and removed.
  const wsRole = null;
  const isGlobalAdmin = user?.role === "admin";
  const isDeptScoped = scopeType === "department";
  const isOwnDept =
    isDeptScoped && !!scopeId && !!user && user.department_ids.includes(scopeId);

  // Can directly edit (PUT /wiki/pages/{slug}). Department-scoped pages
  // require wiki:write:all — own_dept only grants propose access.
  const canEdit: boolean = (() => {
    if (!user) return false;
    if (isGlobalAdmin) return true;
    if (isProjectScoped) return roleAtLeast(wsRole, "editor");
    return hasPermission("wiki:write:all");
  })();

  // Can propose draft (POST /wiki/pages/{slug}/drafts).
  // - Project: workspace contributor+
  // - Department: own_dept perm AND the page is in user's department, OR write:all
  // - Global: any wiki:write permission
  const canPropose: boolean = (() => {
    if (!user) return false;
    if (canEdit) return true; // editors can always propose
    if (isProjectScoped) return roleAtLeast(wsRole, "contributor");
    if (isDeptScoped) {
      if (hasPermission("wiki:write:all")) return true;
      return hasPermission("wiki:write:own_dept") && isOwnDept;
    }
    // Global
    return hasPermission("wiki:write:own_dept") || hasPermission("wiki:write:all");
  })();

  // Can review drafts
  const canReview: boolean = canEdit;

  React.useEffect(() => {
    if (user && (canPropose || canEdit)) {
      loadBranches();
    }
  }, [user, canPropose, canEdit, loadBranches]);

  // Permission helper for the create-page action — mirrors the helper on
  // /wiki landing so the dialog mode follows whatever scope is chosen.
  const getCreateModeForScope = React.useCallback(
    (scope: { scope_type: string; scope_id: string | null }): "direct" | "propose" | null => {
      if (!user) return null;
      const st = scope.scope_type;
      const sid = scope.scope_id;
      if (st === "department" && sid) {
        if (isGlobalAdmin || hasPermission("wiki:write:all")) return "direct";
        if (
          hasPermission("wiki:write:own_dept") &&
          user.department_ids.includes(sid)
        ) {
          return "propose";
        }
        return null;
      }
      if (isGlobalAdmin || hasPermission("wiki:write:all")) return "direct";
      if (hasPermission("wiki:write:own_dept")) return "propose";
      return null;
    },
    [user, isGlobalAdmin, hasPermission],
  );
  const dialogTargetScope = dialogScope ?? currentScope;
  const dialogMode = getCreateModeForScope({
    scope_type: dialogTargetScope.scope_type,
    scope_id: dialogTargetScope.scope_id ?? null,
  });

  // ---------------------------------------------------------------------------
  // Load page (with memory cache for instant transitions)
  // ---------------------------------------------------------------------------
  React.useEffect(() => {
    if (!currentSlug) return;

    if (isSourceView && sourceId) {
      const cachedSrc = getCachedSourceData(sourceId);
      if (cachedSrc) {
        queueMicrotask(() => {
          setSourceData(cachedSrc);
          setPage({
            slug: currentSlug,
            title: ((cachedSrc.title || cachedSrc.file_name) as string) || "Tài liệu",
            page_type: "source",
            status: "evergreen",
            summary: "",
            knowledge_type_slugs: [],
            source_ids: [sourceId],
            version: 1,
            updated_at: (cachedSrc.updated_at as string) || new Date().toISOString(),
            content_md: "",
            backlinks: [],
            outlinks: [],
          });
          setLoading(false);
        });
      } else {
        queueMicrotask(() => {
          setPage(null);
          setSourceData(null);
        });
      }

      api<Record<string, unknown>>(`/api/sources/${sourceId}`)
        .then((data) => {
          setSourceData(data);
          setCachedSourceData(sourceId, data);
          setPage({
            slug: currentSlug,
            title: ((data.title || data.file_name) as string) || "Tài liệu",
            page_type: "source",
            status: "evergreen",
            summary: "",
            knowledge_type_slugs: [],
            source_ids: [sourceId],
            version: 1,
            updated_at: (data.updated_at as string) || new Date().toISOString(),
            content_md: "",
            backlinks: [],
            outlinks: [],
          });
          setNotFound(false);
        })
        .catch((err) => {
          if (err?.status === 404 || err?.message?.includes("404")) {
            setNotFound(true);
          }
        })
        .finally(() => setLoading(false));
    } else {
      const scopeParams = isScoped ? `?scope_type=${scopeType}&scope_id=${scopeId}` : "";
      const cacheKey = `${currentSlug}:${scopeType || "global"}:${scopeId || "none"}`;
      const cached = getCachedPageDetail(cacheKey);
      if (cached) {
        queueMicrotask(() => {
          setPage(cached);
          setLoading(false);
        });
      } else {
        queueMicrotask(() => {
          setPage(null);
        });
      }

      api<WikiPageDetail>(`/api/wiki/pages/${encodeURIComponent(currentSlug)}${scopeParams}`)
        .then((data) => {
          setPage(data);
          setCachedPageDetail(cacheKey, data);
          setNotFound(false);
        })
        .catch((err) => {
          if (err?.status === 404 || err?.message?.includes("404")) {
            setNotFound(true);
          }
        })
        .finally(() => setLoading(false));
    }
  }, [currentSlug, scopeType, scopeId, isScoped, isSourceView, sourceId]);

  // Load parallel citations (sources metadata) for page references
  React.useEffect(() => {
    if (page && !isSourceView && page.source_ids && page.source_ids.length > 0) {
      Promise.all(
        page.source_ids.map((id) =>
          api<Record<string, unknown>>(`/api/sources/${id}`).catch(() => null)
        )
      ).then((res) => {
        setCitations(res.filter(Boolean));
      });
    } else {
      queueMicrotask(() => setCitations([]));
    }
  }, [page, isSourceView]);

  // Dynamically inject standard Markdown footnote definitions at rendering time
  const contentWithFootnotes = React.useMemo(() => {
    if (!page || isSourceView || !citations.length) return page?.content_md || "";
    let append = "\n\n---\n\n";
    citations.forEach((c, idx) => {
      append += `[^${idx + 1}]: [${c.title || c.file_name}](/wiki/source/${c.id})\n`;
    });
    return page.content_md + append;
  }, [page, citations, isSourceView]);

  // ---------------------------------------------------------------------------
  // Load pending drafts (editors/admins only, after page loaded)
  // ---------------------------------------------------------------------------
  const fetchDrafts = React.useCallback(() => {
    if (!page) return;
    // Backend returns reviewable drafts to reviewers and author-only drafts
    // to everyone else — so the same fetch surfaces 'your pending draft'
    // even when the user is not a reviewer of this page.
    api<DraftResponse[]>(
      `/api/wiki/pages/${encodeURIComponent(fullSlug)}/drafts${isScoped ? `?scope_type=${scopeType}&scope_id=${scopeId}` : ""}`
    )
      .then((data) =>
        setDrafts(
          data.filter((d) => d.status === "pending" || d.status === "needs_revision"),
        ),
      )
      .catch(() => setDrafts([]));
  }, [page, fullSlug, isScoped, scopeType, scopeId]);

  React.useEffect(() => {
    fetchDrafts();
  }, [fetchDrafts]);

  // ---------------------------------------------------------------------------
  // Keyboard shortcut: ⌘K search
  // ---------------------------------------------------------------------------
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

  // ---------------------------------------------------------------------------
  // Save handlers
  // ---------------------------------------------------------------------------
  const handleSaveEdit = async (content: string, note: string) => {
    // Direct edit endpoint reads scope from query params (it accepts them via
    // FastAPI Query). Pass both via the URL so the backend resolves the page
    // in the correct scope even when the same slug exists elsewhere.
    const scopeParams = isScoped ? `?scope_type=${scopeType}&scope_id=${scopeId}` : "";
    const updated = await api<WikiPageDetail>(
      `/api/wiki/pages/${encodeURIComponent(fullSlug)}${scopeParams}`,
      {
        method: "PUT",
        body: { content_md: content, change_note: note || undefined },
      }
    );
    setPage(updated);
    setMode("view");
  };

  const handleSaveProposal = async (content: string, note: string) => {
    // propose_draft reads scope from the JSON body (Pydantic model, not Query).
    // Sending the params via query did nothing — backend fell through to
    // get_page_by_slug_any_scope, attaching the draft to whichever scope's
    // copy of the slug happened to be returned first.
    await api(
      `/api/wiki/pages/${encodeURIComponent(fullSlug)}/drafts`,
      {
        method: "POST",
        body: {
          content_md: content,
          note: note || undefined,
          scope_type: isScoped ? scopeType : "global",
          scope_id: isScoped ? scopeId : undefined,
          base_version: page?.version,
          branch_id: activeBranch?.id || undefined,
        },
      }
    );
    // Review is disabled: the edit is published immediately — reload it.
    const scopeParams = isScoped ? `?scope_type=${scopeType}&scope_id=${scopeId}` : "";
    const fresh = await api<WikiPageDetail>(`/api/wiki/pages/${encodeURIComponent(fullSlug)}${scopeParams}`);
    setPage(fresh);
    setMode("view");
  };

  const handleDraftApproved = (draftId: string) => {
    setDrafts((prev) => prev.filter((d) => d.id !== draftId));
    // Reload page content — the approved draft has been applied
    const scopeParams = isScoped ? `?scope_type=${scopeType}&scope_id=${scopeId}` : "";
    api<WikiPageDetail>(`/api/wiki/pages/${encodeURIComponent(fullSlug)}${scopeParams}`)
      .then(setPage)
      .catch(() => {});
  };

  const handleDraftRejected = (draftId: string) => {
    setDrafts((prev) => prev.filter((d) => d.id !== draftId));
  };

  const handleDraftWithdrawn = (draftId: string) => {
    setDrafts((prev) => prev.filter((d) => d.id !== draftId));
  };

  const handleResubmitOpen = (draft: DraftResponse) => {
    setEditingDraft(draft);
  };

  const handleResubmitSave = async (content: string, note: string) => {
    if (!editingDraft) return;
    await api(`/api/wiki/drafts/${editingDraft.id}/content`, {
      method: "PATCH",
      body: { content_md: content, note: note || undefined },
    });
    setEditingDraft(null);
    // Refresh draft list so the banner shows the new pending status.
    fetchDrafts();
  };

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------
  return (
    <>
      <div className="flex-1 min-h-0 flex flex-col">
      <div className="flex-1 flex gap-0 -mx-6 md:-mx-8 lg:-mx-10 -mt-4 -mb-6 md:-mb-8 lg:-mb-10 min-h-0 overflow-hidden">
        {/* Left: Page Tree — same scope-grouped layout as /wiki. We do NOT
            filter pagesUrl by scope so the sidebar is identical across all
            wiki pages; the active page's scope bucket auto-expands. */}
        <WikiPageTree
          activeSlug={currentSlug}
          onPageSelect={handlePageSelect}
          groupByScope
          activeScope={{
            scope_type: scopeType ?? "global",
            scope_id: scopeId ?? null,
          }}
          getCreateModeForScope={getCreateModeForScope}
          onSearch={() => setSearchOpen(true)}
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

        {/* Center: Content */}
        <div className="flex-1 overflow-y-auto min-w-0">
          {loading ? (
            <div className="px-4 py-8">
              <div className="flex items-center gap-2 mb-4">
                <div className="h-4 w-16 rounded bg-muted animate-pulse" />
                <div className="h-4 w-4 text-muted-foreground">/</div>
                <div className="h-4 w-24 rounded bg-muted animate-pulse" />
              </div>
              <div className="h-10 w-2/3 rounded-lg bg-muted animate-pulse mb-3" />
              <div className="h-4 w-full rounded bg-muted animate-pulse mb-2" />
              <div className="h-4 w-5/6 rounded bg-muted animate-pulse mb-8" />
              <div className="space-y-3">
                {Array.from({ length: 8 }).map((_, i) => (
                  <div
                    key={i}
                    className="h-4 rounded bg-muted animate-pulse"
                    style={{ width: `${85 - i * 5}%`, opacity: 1 - i * 0.08 }}
                  />
                ))}
              </div>
            </div>
          ) : notFound ? (
            <div className="px-8 py-12">
              <EmptyState
                icon="find_in_page"
                title="Page not found"
                description={`No wiki page found for "${fullSlug}". It may not have been compiled yet.`}
              />
            </div>
          ) : page ? (
            <div
              className={cn(
                "mx-auto px-6 xl:px-10 py-6",
                isSourceView ? "max-w-6xl" : "max-w-[54rem]",
              )}
            >
              {/* Breadcrumb + reading-mode toggle */}
              <div className="flex items-center gap-3 mb-4">
                <nav className="flex items-center gap-1 text-xs text-muted-foreground min-w-0">
                  <Link href={backHref} className="hover:text-foreground transition-colors font-medium">
                    {isProjectScoped ? "Workspace" : "Wiki"}
                  </Link>
                  <span className="material-symbols-outlined text-muted-foreground/50" style={{ fontSize: 14 }}>chevron_right</span>
                  <span className="font-medium text-foreground/80 truncate">{wikiTypeGroupLabel(page.page_type)}</span>
                </nav>
                <button
                  type="button"
                  onClick={() => {
                    const next = !readingMode;
                    setTreeCollapsed(next);
                    setInfoCollapsed(next);
                  }}
                  className={cn(
                    "ml-auto shrink-0 inline-flex items-center gap-1.5 h-7 px-2.5 rounded-md border text-xs font-medium transition-colors cursor-pointer",
                    readingMode
                      ? "border-primary/40 bg-primary/10 text-primary"
                      : "border-border text-muted-foreground hover:text-foreground hover:bg-accent/60",
                  )}
                  title={readingMode ? "Hiện lại danh mục và thông tin trang" : "Ẩn danh mục và thông tin trang để đọc rộng hơn"}
                >
                  <span className="material-symbols-outlined" style={{ fontSize: 15 }}>
                    {readingMode ? "close_fullscreen" : "open_in_full"}
                  </span>
                  <span className="hidden sm:inline">{readingMode ? "Thoát chế độ đọc" : "Chế độ đọc"}</span>
                </button>
              </div>

              {/* Badges: type · scope · status — version on the right */}
              <div className="flex items-center gap-2 flex-wrap mb-3">
                <WikiTypeBadge type={page.page_type} />
                {!isSourceView && <ScopeBadge scopeType={page.scope_type || "global"} scopeId={page.scope_id} />}
                {page.page_type !== "index" && page.page_type !== "log" && page.page_type !== "hot" && page.page_type !== "source" && (
                  canEdit ? (
                    <DropdownMenu>
                      <DropdownMenuTrigger className="cursor-pointer" title="Đổi độ hoàn thiện">
                        <WikiStatusBadge status={page.status} className="shrink-0" />
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="start">
                        {(["seed", "developing", "mature", "evergreen"] as WikiStatus[]).map((s) => (
                          <DropdownMenuItem
                            key={s}
                            onClick={async () => {
                              try {
                                const qs = scopeType ? `?scope_type=${scopeType}&scope_id=${scopeId}` : "";
                                await api(`/api/wiki/pages/${page.slug}/status${qs}`, {
                                  method: "PATCH",
                                  headers: { "Content-Type": "application/json" },
                                  body: JSON.stringify({ status: s }),
                                });
                                setPage((prev) => prev ? { ...prev, status: s } : prev);
                              } catch {}
                            }}
                            disabled={page.status === s}
                            className="gap-2"
                          >
                            <WikiStatusBadge status={s} />
                          </DropdownMenuItem>
                        ))}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  ) : (
                    <WikiStatusBadge status={page.status} className="shrink-0" />
                  )
                )}
                {!isSourceView && page.version > 0 && (
                  <span className="ml-auto text-xs font-mono text-muted-foreground" title="Phiên bản">
                    v{page.version}
                  </span>
                )}
              </div>

              {/* Title + Edit */}
              <div className="flex items-start justify-between gap-4">
                <h1 className="flex-1 min-w-0 font-heading text-3xl font-normal leading-tight text-foreground">
                  {page.title}
                </h1>
                {mode === "view" && !isSourceView && (canEdit || canPropose) && (
                  <Button variant="outline" size="sm" onClick={() => setMode("edit")} className="shrink-0 gap-1.5 mt-1">
                    <span className="material-symbols-outlined text-sm">edit</span>
                    {canEdit ? "Chỉnh sửa" : "Đề xuất sửa"}
                  </Button>
                )}
              </div>

              {!isSourceView && (
                <div className="mt-3 mb-6 space-y-3">
                  {page.updated_at && (
                    <p className="text-xs text-muted-foreground">
                      Cập nhật lúc{" "}
                      {new Date(page.updated_at).toLocaleString("vi-VN", {
                        hour: "2-digit",
                        minute: "2-digit",
                        day: "2-digit",
                        month: "2-digit",
                        year: "numeric",
                      })}
                    </p>
                  )}

                  {/* Source documents */}
                  {citations.length > 0 && (
                    <div className="flex flex-col gap-1">
                      {(sourcesExpanded ? citations : citations.slice(0, 2)).map((c) => (
                        <Link
                          key={c.id}
                          href={`/wiki/source/${c.id}${scopeLinkSuffix}`}
                          onClick={(e) => {
                            if (!e.ctrlKey && !e.metaKey && !e.shiftKey && e.button === 0) {
                              e.preventDefault();
                              handlePageSelect(`source/${c.id}`);
                            }
                          }}
                          className="inline-flex items-center gap-1.5 w-fit max-w-full text-sm text-foreground/80 hover:text-primary transition-colors"
                          title={c.title || c.file_name}
                        >
                          <span className="material-symbols-outlined text-muted-foreground shrink-0" style={{ fontSize: 16 }}>
                            description
                          </span>
                          <span className="truncate">{c.title || c.file_name}</span>
                        </Link>
                      ))}
                      {citations.length > 2 && (
                        <button
                          type="button"
                          onClick={() => setSourcesExpanded((v) => !v)}
                          className="w-fit text-xs font-medium text-primary hover:underline cursor-pointer"
                        >
                          {sourcesExpanded ? "Thu gọn" : `+${citations.length - 2} tài liệu`}
                        </button>
                      )}
                    </div>
                  )}

                  {/* Knowledge-type tags */}
                  {page.knowledge_type_slugs?.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {page.knowledge_type_slugs.map((k) => (
                        <span
                          key={k}
                          className="px-2 py-0.5 rounded-md bg-muted text-[11px] font-medium text-muted-foreground"
                        >
                          {k}
                        </span>
                      ))}
                    </div>
                  )}

                  {/* Summary */}
                  {page.summary && (
                    <div className="rounded-xl border border-border bg-muted/40 px-4 py-3">
                      <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-1">
                        Tóm tắt
                      </p>
                      <p className="text-sm leading-relaxed text-foreground/90">{page.summary}</p>
                    </div>
                  )}
                </div>
              )}
              {isSourceView && <div className="mb-6" />}

              {/* Draft banner — visible to reviewers AND to authors of own drafts. */}
              {mode === "view" && !editingDraft && drafts.length > 0 && (
                <div className="mb-6">
                  <WikiDraftBanner
                    drafts={drafts}
                    currentContent={page.content_md}
                    currentUserId={user?.id ?? null}
                    onApproved={handleDraftApproved}
                    onRejected={handleDraftRejected}
                    onResubmitDraft={handleResubmitOpen}
                    onWithdrawn={handleDraftWithdrawn}
                  />
                </div>
              )}

              {/* Markdown body / direct-edit / resubmit-draft editor */}
              {editingDraft ? (
                <WikiEditor
                  initialContent={editingDraft.content_md}
                  noteLabel="Resubmission note"
                  notePlaceholder="What changed in this round?"
                  saveLabel="Resubmit draft"
                  onSave={handleResubmitSave}
                  onCancel={() => setEditingDraft(null)}
                />
              ) : mode === "edit" ? (
                <>
                  {/* Branch context bar for contributors */}
                  {!canEdit && activeBranch && (
                    <div className="mb-4 flex flex-wrap items-center justify-between gap-3 p-3 rounded-xl border border-[#a8977e]/30 bg-[#a8977e]/5 shadow-sm text-xs text-[#8a7a62]">
                      <div className="flex items-center gap-2">
                        <span className="material-symbols-outlined text-sm font-semibold">fork_right</span>
                        <span>Đang lưu đóng góp vào nhánh: </span>
                        <strong className="text-foreground">{activeBranch.name}</strong>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => setShowCreateBranch(true)}
                          className="px-2.5 py-1 rounded bg-[#a8977e]/15 hover:bg-[#a8977e]/25 text-foreground transition-all cursor-pointer font-medium"
                        >
                          Tạo nhánh mới
                        </button>
                        {branches.length > 1 && (
                          <select
                            value={activeBranch.id}
                            onChange={(e) => {
                              const b = branches.find((x) => x.id === e.target.value);
                              if (b) setActiveBranch(b);
                            }}
                            className="h-7 px-2 rounded border border-border bg-background outline-none text-foreground cursor-pointer text-xs"
                          >
                            {branches.map((b) => (
                              <option key={b.id} value={b.id}>{b.name}</option>
                            ))}
                          </select>
                        )}
                      </div>
                    </div>
                  )}
                  <WikiEditor
                    initialContent={page.content_md}
                    noteLabel="Change note"
                    notePlaceholder="Briefly describe what you changed (optional)"
                    saveLabel="Save Edit"
                    onSave={canEdit ? handleSaveEdit : handleSaveProposal}
                    onCancel={() => setMode("view")}
                  />
                </>
              ) : isSourceView && sourceData ? (
                <div className="space-y-6">
                  {/* File information bar */}
                  <div className="flex flex-wrap items-center justify-between gap-4 p-4 rounded-xl border bg-card/50 shadow-sm">
                    <div className="flex items-center gap-3">
                      <span className="material-symbols-outlined text-4xl text-primary shrink-0">
                        {sourceData.source_type === "url" ? "language" : "description"}
                      </span>
                      <div className="min-w-0">
                        <h3 className="font-semibold text-foreground text-sm line-clamp-1 truncate max-w-[400px] flex items-center gap-2">
                          {sourceData.title || sourceData.file_name}
                          {sourceData.preserve_verbatim && (
                            <span
                              className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-secondary text-secondary-foreground shrink-0"
                              title="Verbatim — searches the exact original document, skipping the wiki pipeline"
                            >
                              Verbatim
                            </span>
                          )}
                        </h3>
                        <p className="text-xs text-muted-foreground mt-0.5">
                          {sourceData.source_type === "url" ? (
                            <a href={sourceData.url} target="_blank" rel="noopener noreferrer" className="hover:underline flex items-center gap-1">
                              {sourceData.url}
                              <span className="material-symbols-outlined text-[10px]">open_in_new</span>
                            </a>
                          ) : (
                            `Dung lượng: ${((sourceData.file_size || 0) / 1024 / 1024).toFixed(2)} MB`
                          )}
                          {sourceData.contributed_by_name && ` • Đăng bởi: ${sourceData.contributed_by_name}`}
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      {(sourceData.preview_url || sourceData.file_url || sourceData.download_url) && (
                        <Button
                          variant="outline"
                          onClick={() => window.open(sourceData.preview_url || sourceData.file_url || sourceData.download_url, "_blank")}
                          className="gap-2 shadow-sm hover:scale-[1.02] active:scale-[0.98] transition-all text-xs"
                        >
                          <span className="material-symbols-outlined text-sm">open_in_new</span>
                          Mở tab mới
                        </Button>
                      )}
                      {sourceData.download_url && (
                        <Button
                          onClick={() => window.open(sourceData.download_url, "_blank")}
                          className="gap-2 shadow-sm hover:scale-[1.02] active:scale-[0.98] transition-all text-xs"
                        >
                          <span className="material-symbols-outlined text-sm">cloud_download</span>
                          Tải tài liệu gốc
                        </Button>
                      )}
                    </div>
                  </div>

                  {/* Document Viewer Frame */}
                  <div className="border border-border rounded-2xl overflow-hidden shadow-sahara bg-card/30">
                    {sourceData.source_type === "file" && (sourceData.preview_url || sourceData.file_url || sourceData.download_url) ? (
                      sourceData.file_name?.toLowerCase().endsWith(".pdf") ? (
                        <div className="w-full h-[780px] bg-background relative flex flex-col">
                          <iframe
                            src={`${sourceData.preview_url || sourceData.file_url || sourceData.download_url}#toolbar=1`}
                            className="w-full h-full border-none"
                            title={sourceData.title || sourceData.file_name}
                          />
                        </div>
                      ) : sourceData.file_name?.toLowerCase().match(/\.(jpg|jpeg|png|gif|webp|svg)$/) ? (
                        <div className="flex items-center justify-center p-8 bg-black/[0.02] min-h-[400px]">
                          <img
                            src={sourceData.file_url || sourceData.preview_url || sourceData.download_url}
                            alt={sourceData.title || sourceData.file_name}
                            className="max-w-full max-h-[700px] object-contain rounded-lg border shadow-md"
                          />
                        </div>
                      ) : sourceData.file_name?.toLowerCase().match(/\.(docx|doc|xlsx|xls|pptx|ppt|txt|md|csv|json)$/) ? (
                        <div className="w-full h-[780px] bg-background relative flex flex-col">
                          <iframe
                            src={sourceData.preview_url || sourceData.download_url}
                            className="w-full h-full border-none"
                            title={sourceData.title || sourceData.file_name}
                          />
                        </div>
                      ) : (
                        <div className="flex flex-col items-center justify-center p-12 text-center text-sm text-muted-foreground gap-3 min-h-[300px]">
                          <span className="material-symbols-outlined text-4xl text-muted-foreground/60">draft</span>
                          <div className="font-semibold text-foreground">Không thể xem trước định dạng này trực tiếp</div>
                          <p className="text-xs max-w-sm">Tài liệu "{sourceData.file_name}" không hỗ trợ nhúng trực tiếp. Vui lòng bấm Tải tài liệu gốc để đọc.</p>
                          {sourceData.download_url && (
                            <Button
                              variant="outline"
                              onClick={() => window.open(sourceData.download_url, "_blank")}
                              className="mt-2 gap-2"
                            >
                              <span className="material-symbols-outlined text-sm">cloud_download</span>
                              Tải tài liệu gốc
                            </Button>
                          )}
                        </div>
                      )
                    ) : sourceData.source_type === "url" ? (
                      <div className="flex flex-col items-center justify-center p-12 text-center text-sm text-muted-foreground gap-4 min-h-[350px]">
                        <span className="material-symbols-outlined text-5xl text-primary/60">language</span>
                        <div>
                          <div className="font-semibold text-foreground text-base">Liên kết tài liệu gốc (Website Source)</div>
                          <p className="text-xs max-w-md mt-1">Đây là một liên kết ngoài. Bạn có thể mở trực tiếp trang web để đọc toàn văn tài liệu.</p>
                        </div>
                        <Button
                          variant="outline"
                          onClick={() => window.open(sourceData.url, "_blank")}
                          className="gap-2"
                        >
                          <span className="material-symbols-outlined text-sm">open_in_new</span>
                          Mở trang Web gốc
                        </Button>
                      </div>
                    ) : (
                      <div className="flex flex-col items-center justify-center p-12 text-center text-sm text-muted-foreground gap-2 min-h-[300px]">
                        <span className="material-symbols-outlined text-4xl">hourglass_empty</span>
                        <div>Tài liệu không có tệp đính kèm hoặc đang xử lý.</div>
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <div className="space-y-6">
                  <WikiContent markdown={contentWithFootnotes} linkSuffix={scopeLinkSuffix} onWikiLinkClick={handlePageSelect} />

                  {/* References card deck section at bottom of concept pages */}
                  {citations.length > 0 && (
                    <div className="mt-12 pt-8 border-t border-border">
                      <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-4 flex items-center gap-1.5">
                        <span className="material-symbols-outlined text-sm">description</span>
                        Tài liệu tham khảo ({citations.length})
                      </h3>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {citations.map((c, idx) => (
                          <div key={c.id} className="rounded-xl border bg-card p-4 flex flex-col justify-between shadow-sm hover:shadow-md transition-shadow">
                            <div>
                              <div className="flex items-center gap-1 text-[10px] text-muted-foreground/80 font-mono font-semibold mb-1 bg-black/[0.02] border rounded px-1.5 py-0.5 w-fit">
                                <span>Trích dẫn [{idx + 1}]</span>
                              </div>
                              <h4 className="font-semibold text-sm line-clamp-2 text-foreground" title={c.title || c.file_name}>
                                {c.title || c.file_name}
                              </h4>
                              <p className="text-[10px] text-muted-foreground mt-1">
                                {c.source_type === "url" ? "Liên kết Web" : `File • ${((c.file_size || 0) / 1024 / 1024).toFixed(2)} MB`}
                              </p>
                            </div>
                            <div className="flex gap-2 mt-4 pt-3 border-t">
                              <Link
                                href={`/wiki/source/${c.id}${scopeLinkSuffix}`}
                                onClick={(e) => {
                                  if (!e.ctrlKey && !e.metaKey && !e.shiftKey && e.button === 0) {
                                    e.preventDefault();
                                    handlePageSelect(`source/${c.id}`);
                                  }
                                }}
                                className="inline-flex items-center gap-1 text-xs text-primary font-medium hover:underline"
                              >
                                <span className="material-symbols-outlined text-xs">visibility</span>
                                Xem tài liệu →
                              </Link>
                              {c.download_url && (
                                <a
                                  href={c.download_url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground font-medium hover:underline ml-auto"
                                >
                                  <span className="material-symbols-outlined text-xs">cloud_download</span>
                                  Tải xuống
                                </a>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          ) : null}
        </div>

        {/* Right: Sidebar (hidden on < lg, only in view mode) */}
        {page && mode === "view" && (
          <div className="hidden xl:block h-full">
            {infoCollapsed ? (
              <div className="w-11 h-full border-l border-border bg-card/30 flex flex-col items-center pt-3">
                <button
                  onClick={() => setInfoCollapsed(false)}
                  className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent/60 transition-colors cursor-pointer"
                  title="Mở thông tin trang"
                >
                  <span className="material-symbols-outlined block" style={{ fontSize: 18 }}>right_panel_open</span>
                </button>
              </div>
            ) : (
              <div className="relative h-full">
                <button
                  onClick={() => setInfoCollapsed(true)}
                  className="absolute right-2 top-2.5 z-10 p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent/60 transition-colors cursor-pointer"
                  title="Thu gọn thông tin trang"
                >
                  <span className="material-symbols-outlined block" style={{ fontSize: 16 }}>right_panel_close</span>
                </button>
                <WikiSidebarRight slug={currentSlug} page={page} linkSuffix={scopeLinkSuffix} onSelectPage={handlePageSelect} />
              </div>
            )}
          </div>
        )}
      </div>
      </div>

      <WikiSearchDialog open={searchOpen} onOpenChange={setSearchOpen} onSelectPage={handlePageSelect} />
      {dialogMode && (
        <WikiCreatePageDialog
          open={createOpen}
          onOpenChange={(o) => {
            setCreateOpen(o);
            if (!o) setDialogScope(null);
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
        />
      )}
      {showCreateBranch && (
        <div className="fixed inset-0 bg-background/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-card border border-border rounded-2xl w-full max-w-md p-6 shadow-2xl space-y-4 animate-in fade-in zoom-in duration-200">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-foreground">Tạo nhánh đóng góp mới</h3>
              <button
                onClick={() => setShowCreateBranch(false)}
                className="text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
              >
                <span className="material-symbols-outlined text-sm">close</span>
              </button>
            </div>
            <div className="space-y-3">
              <div className="space-y-1">
                <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Tên nhánh</label>
                <input
                  type="text"
                  value={newBranchName}
                  onChange={(e) => setNewBranchName(e.target.value)}
                  placeholder="Ví dụ: thay-doi-quy-che-lam-viec"
                  className="w-full h-9 px-3 rounded-lg border border-input bg-background text-xs outline-none focus:border-primary text-foreground"
                />
              </div>
              <div className="space-y-1">
                <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Mô tả (Không bắt buộc)</label>
                <textarea
                  value={newBranchDesc}
                  onChange={(e) => setNewBranchDesc(e.target.value)}
                  placeholder="Mô tả tóm tắt nội dung đợt đóng góp này..."
                  rows={3}
                  className="w-full p-3 rounded-lg border border-input bg-background text-xs outline-none focus:border-primary resize-none text-foreground"
                />
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setShowCreateBranch(false)}
                className="px-3 py-1.5 rounded-lg border hover:bg-muted text-xs transition-all cursor-pointer text-foreground"
              >
                Hủy
              </button>
              <button
                onClick={async () => {
                  if (!newBranchName.trim()) return;
                  try {
                    const newB = await api<any>("/api/wiki/branches", {
                      method: "POST",
                      body: {
                        name: newBranchName.trim(),
                        description: newBranchDesc.trim() || undefined,
                        scope_type: isScoped ? scopeType : "global",
                        scope_id: isScoped ? scopeId : undefined,
                      },
                    });
                    setBranches((prev) => [newB, ...prev]);
                    setActiveBranch(newB);
                    setShowCreateBranch(false);
                    setNewBranchName("");
                    setNewBranchDesc("");
                  } catch {}
                }}
                className="px-3 py-1.5 rounded-lg bg-primary text-primary-foreground font-medium text-xs hover:opacity-90 transition-all cursor-pointer"
              >
                Tạo nhánh
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
