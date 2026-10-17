"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { ScopeBadge } from "@/components/shared/scope-badge";
import { WikiSidebarRight } from "@/components/wiki/wiki-backlinks";
import { WikiContent } from "@/components/wiki/wiki-content";
import { WikiCreatePageDialog } from "@/components/wiki/wiki-create-page-dialog";
import { WikiDraftBanner } from "@/components/wiki/wiki-draft-banner";
import { WikiEditor } from "@/components/wiki/wiki-editor";
import { WikiPageTree } from "@/components/wiki/wiki-page-tree";
import { encodeSlugPath } from "@/components/wiki/wiki-pages-loader";
import { WikiSearchDialog } from "@/components/wiki/wiki-search-dialog";
import { WikiStatusBadge } from "@/components/wiki/wiki-status-badge";
import { WikiTypeBadge, wikiTypeGroupLabel } from "@/components/wiki/wiki-type-badge";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useIsEmbedded } from "@/lib/embed";
import { cn } from "@/lib/utils";
import {
  getCachedPageDetail,
  getCachedSourceData,
  setCachedPageDetail,
  setCachedSourceData,
  useWikiStore,
} from "@/lib/wiki-store";
import type { DraftResponse, WikiPageDetail, WikiScope } from "@/types/wiki";
import { BranchModal, type WikiBranch } from "./branch-modal";
import { formatMb, SourceView, sourceTitle, type SourceDetail } from "./source-view";

type CreateMode = "direct" | "propose";

type Props = {
  slug: string;
  scopeType: string | null;
  scopeId: string | null;
  scopeSuffix: string;
  navigate: (slug: string) => void;
  goTo: (href: string) => void;
};

type Ref = { id: string; data: SourceDetail };
type EditState = { key: string; kind: "page" } | { key: string; kind: "draft"; draft: DraftResponse };

const GLOBAL_SCOPE: WikiScope = { scope_type: "global", scope_id: null, name: "Global" };
const NO_STATUS_TYPES = new Set(["index", "log", "hot", "source"]);
const STATUS_CHOICES = ["seed", "developing", "mature", "evergreen"] as const;

function pad(n: number) {
  return String(n).padStart(2, "0");
}

function formatUpdated(iso: string | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${pad(d.getHours())}:${pad(d.getMinutes())} ${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()}`;
}

/** Query string addressing a page in its own scope (scope_id only when present). */
function pageScopeQuery(scopeType: string | null | undefined, scopeId: string | null | undefined): string {
  const st = scopeType || "global";
  return `scope_type=${encodeURIComponent(st)}${scopeId ? `&scope_id=${encodeURIComponent(scopeId)}` : ""}`;
}

/** Build the pseudo page shown for `/wiki/source/{id}`. */
function sourcePseudoPage(id: string, s: SourceDetail): WikiPageDetail {
  return {
    slug: `source/${id}`,
    title: s.title || s.file_name || "Tài liệu",
    page_type: "source",
    status: "evergreen",
    summary: "",
    knowledge_type_slugs: [],
    source_ids: [],
    version: 1,
    updated_at: s.updated_at || s.created_at || "",
    content_md: "",
    backlinks: [],
    outlinks: [],
  };
}

const escapeLinkText = (s: string) => s.replace(/[[\]]/g, (c) => `\\${c}`);

export function WikiPageView({ slug, scopeType, scopeId, scopeSuffix, navigate, goTo }: Props) {
  const { user, hasPermission } = useAuth();
  const embedded = useIsEmbedded();
  const { treeCollapsed, infoCollapsed, setTreeCollapsed, setInfoCollapsed } = useWikiStore();

  const parts = slug.split("/").filter(Boolean);
  const sourceMode = parts.length === 2 && parts[0] === "source";
  const sourceId = sourceMode ? parts[1] : null;
  const hasScope = !!scopeType;
  const cacheKey = `${slug}:${scopeType || "global"}:${scopeId || "none"}`;
  const apiScopeQs = hasScope ? `?${pageScopeQuery(scopeType, scopeId)}` : "";

  // ---------------------------------------------------------------- scopes & permissions
  const [myScopes, setMyScopes] = useState<WikiScope[]>([]);
  useEffect(() => {
    let cancelled = false;
    api<WikiScope[]>("/api/wiki/my-scopes")
      .then((res) => {
        if (!cancelled) setMyScopes(Array.isArray(res) ? res : []);
      })
      .catch(() => {
        if (!cancelled) setMyScopes([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const currentScope = useMemo<WikiScope>(() => {
    if (!hasScope) {
      return myScopes.find((s) => s.scope_type === "global") ?? GLOBAL_SCOPE;
    }
    return (
      myScopes.find((s) => s.scope_type === scopeType && (s.scope_id ?? null) === (scopeId ?? null)) ?? {
        scope_type: scopeType ?? "global",
        scope_id: scopeId,
        name: scopeType ?? "global",
      }
    );
  }, [myScopes, hasScope, scopeType, scopeId]);

  const isAdmin = user?.role === "admin";
  const writeAll = hasPermission("wiki:write:all");
  const writeOwnDept = hasPermission("wiki:write:own_dept");
  const deptIds = useMemo(() => user?.department_ids ?? [], [user]);
  const canEdit = isAdmin || writeAll;
  const canPropose =
    canEdit ||
    (scopeType === "department"
      ? writeAll || (writeOwnDept && !!scopeId && deptIds.includes(scopeId))
      : writeOwnDept || writeAll);

  const getCreateModeForScope = useCallback(
    (type: string, id: string | null): CreateMode | null => {
      if (type === "department" && id) {
        if (isAdmin || writeAll) return "direct";
        if (writeOwnDept && deptIds.includes(id)) return "propose";
        return null;
      }
      if (isAdmin || writeAll) return "direct";
      if (writeOwnDept) return "propose";
      return null;
    },
    [isAdmin, writeAll, writeOwnDept, deptIds],
  );

  // ---------------------------------------------------------------- contribution branches
  const [branches, setBranches] = useState<WikiBranch[]>([]);
  const [activeBranchId, setActiveBranchId] = useState<string | null>(null);
  const userId = user?.id ?? null;
  const wantsBranches = !!userId && (canPropose || canEdit);

  useEffect(() => {
    if (!wantsBranches) return;
    let cancelled = false;
    const scopeQs = hasScope
      ? `&scope_type=${encodeURIComponent(scopeType ?? "")}&scope_id=${encodeURIComponent(scopeId ?? "")}`
      : "";
    (async () => {
      try {
        const list = await api<WikiBranch[]>(`/api/wiki/branches?mine=true&status=draft${scopeQs}`);
        const arr = Array.isArray(list) ? list : [];
        if (arr.length > 0) {
          if (!cancelled) {
            setBranches(arr);
            setActiveBranchId(arr[0].id);
          }
          return;
        }
        const created = await api<WikiBranch>("/api/wiki/branches", {
          method: "POST",
          body: {
            name: `Đóng góp ngày ${new Date().toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric" })}`,
            description: "Nhánh đóng góp tự động được tạo khi chỉnh sửa tài liệu.",
            scope_type: scopeType || "global",
            scope_id: scopeId || null,
          },
        });
        if (!cancelled) {
          setBranches(created ? [created] : []);
          setActiveBranchId(created?.id ?? null);
        }
      } catch {
        if (!cancelled) {
          setBranches([]);
          setActiveBranchId(null);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [wantsBranches, hasScope, scopeType, scopeId]);

  const activeBranch = branches.find((b) => b.id === activeBranchId) ?? null;
  const [branchModalOpen, setBranchModalOpen] = useState(false);

  // ---------------------------------------------------------------- page data
  const [pageState, setPageState] = useState<{ key: string; page: WikiPageDetail | null; notFound: boolean }>({
    key: "",
    page: null,
    notFound: false,
  });
  const [sourceState, setSourceState] = useState<{ id: string; data: SourceDetail | null }>({ id: "", data: null });
  const [pageTick, setPageTick] = useState(0);
  const reloadPage = useCallback(() => setPageTick((n) => n + 1), []);

  useEffect(() => {
    if (sourceMode) return;
    let cancelled = false;
    api<WikiPageDetail>(`/api/wiki/pages/${encodeSlugPath(slug)}${apiScopeQs}`)
      .then((page) => {
        if (cancelled) return;
        setCachedPageDetail(cacheKey, page);
        setPageState({ key: cacheKey, page, notFound: false });
      })
      .catch((e) => {
        if (cancelled) return;
        if (e instanceof ApiError && e.status === 404) setPageState({ key: cacheKey, page: null, notFound: true });
        else setPageState({ key: cacheKey, page: getCachedPageDetail(cacheKey), notFound: false });
      });
    return () => {
      cancelled = true;
    };
  }, [sourceMode, slug, apiScopeQs, cacheKey, pageTick]);

  useEffect(() => {
    if (!sourceId) return;
    let cancelled = false;
    api<SourceDetail>(`/api/sources/${encodeURIComponent(sourceId)}`)
      .then((data) => {
        if (cancelled) return;
        setCachedSourceData(sourceId, data as unknown as Record<string, unknown>);
        setSourceState({ id: sourceId, data });
      })
      .catch(() => {
        if (cancelled) return;
        const cached = getCachedSourceData(sourceId) as unknown as SourceDetail | null;
        setSourceState({ id: sourceId, data: cached });
      });
    return () => {
      cancelled = true;
    };
  }, [sourceId]);

  const sourceData: SourceDetail | null = sourceId
    ? sourceState.id === sourceId
      ? sourceState.data
      : (getCachedSourceData(sourceId) as unknown as SourceDetail | null)
    : null;
  const sourceSettled = !!sourceId && sourceState.id === sourceId;

  const page: WikiPageDetail | null = sourceMode
    ? sourceData && sourceId
      ? sourcePseudoPage(sourceId, sourceData)
      : null
    : pageState.key === cacheKey
      ? pageState.page
      : getCachedPageDetail(cacheKey);
  const notFound = sourceMode ? sourceSettled && !sourceData : pageState.key === cacheKey && pageState.notFound;
  const loading = !page && !notFound && (sourceMode ? !sourceSettled : pageState.key !== cacheKey);

  const updatePageLocally = (next: WikiPageDetail) => {
    setCachedPageDetail(cacheKey, next);
    setPageState({ key: cacheKey, page: next, notFound: false });
  };

  // ---------------------------------------------------------------- citations
  const sourceIdsKey = (page?.source_ids ?? []).join(",");
  const [refsState, setRefsState] = useState<{ key: string; refs: Ref[] }>({ key: "", refs: [] });
  useEffect(() => {
    if (!sourceIdsKey) return;
    let cancelled = false;
    const ids = sourceIdsKey.split(",");
    Promise.allSettled(ids.map((id) => api<SourceDetail>(`/api/sources/${encodeURIComponent(id)}`))).then((results) => {
      if (cancelled) return;
      const refs: Ref[] = [];
      results.forEach((r, i) => {
        if (r.status === "fulfilled" && r.value) refs.push({ id: ids[i], data: r.value });
      });
      setRefsState({ key: sourceIdsKey, refs });
    });
    return () => {
      cancelled = true;
    };
  }, [sourceIdsKey]);
  const refs = useMemo(
    () => (sourceIdsKey && refsState.key === sourceIdsKey ? refsState.refs : []),
    [sourceIdsKey, refsState],
  );
  const [showAllRefs, setShowAllRefs] = useState(false);

  const markdown = useMemo(() => {
    const body = page?.content_md ?? "";
    if (refs.length === 0) return body;
    const notes = refs
      .map((r, i) => `[^${i + 1}]: [${escapeLinkText(sourceTitle(r.data))}](/wiki/source/${encodeURIComponent(r.id)})`)
      .join("\n");
    return `${body}\n\n---\n\n${notes}\n`;
  }, [page?.content_md, refs]);

  // ---------------------------------------------------------------- drafts
  const [draftsState, setDraftsState] = useState<{ key: string; list: DraftResponse[] }>({ key: "", list: [] });
  const [draftsTick, setDraftsTick] = useState(0);
  const reloadDrafts = useCallback(() => setDraftsTick((n) => n + 1), []);
  useEffect(() => {
    if (sourceMode) return;
    let cancelled = false;
    api<DraftResponse[]>(`/api/wiki/pages/${encodeSlugPath(slug)}/drafts${apiScopeQs}`)
      .then((list) => {
        if (cancelled) return;
        const open = (Array.isArray(list) ? list : []).filter(
          (d) => d.status === "pending" || d.status === "needs_revision",
        );
        setDraftsState({ key: cacheKey, list: open });
      })
      .catch(() => {
        if (!cancelled) setDraftsState({ key: cacheKey, list: [] });
      });
    return () => {
      cancelled = true;
    };
  }, [sourceMode, slug, apiScopeQs, cacheKey, draftsTick]);
  const drafts = draftsState.key === cacheKey ? draftsState.list : [];
  const dropDraft = (id: string) =>
    setDraftsState((prev) => ({ key: prev.key, list: prev.list.filter((d) => d.id !== id) }));

  // ---------------------------------------------------------------- edit mode
  const [editState, setEditState] = useState<EditState | null>(null);
  const editing = editState && editState.key === cacheKey ? editState : null;

  const savePage = async (content: string, note: string) => {
    if (!page) return;
    const qs = pageScopeQuery(page.scope_type, page.scope_id);
    if (canEdit) {
      const res = await api<WikiPageDetail>(`/api/wiki/pages/${encodeSlugPath(page.slug)}?${qs}`, {
        method: "PUT",
        body: { content_md: content, change_note: note },
      });
      const next: WikiPageDetail =
        res && typeof res === "object" && "slug" in res ? { ...page, ...res } : { ...page, content_md: content };
      updatePageLocally(next);
      setEditState(null);
      return;
    }
    await api(`/api/wiki/pages/${encodeSlugPath(page.slug)}/drafts`, {
      method: "POST",
      body: {
        content_md: content,
        note,
        scope_type: page.scope_type || "global",
        scope_id: page.scope_id ?? null,
        base_version: page.version,
        branch_id: activeBranch?.id ?? null,
      },
    });
    setEditState(null);
    reloadPage();
    reloadDrafts();
  };

  const resubmitDraft = async (draft: DraftResponse, content: string, note: string) => {
    await api(`/api/wiki/drafts/${encodeURIComponent(draft.id)}/content`, {
      method: "PATCH",
      body: { content_md: content, note },
    });
    setEditState(null);
    reloadDrafts();
  };

  const changeStatus = async (status: string) => {
    if (!page || status === page.status) return;
    try {
      const res = await api<WikiPageDetail>(
        `/api/wiki/pages/${encodeSlugPath(page.slug)}/status?${pageScopeQuery(page.scope_type, page.scope_id)}`,
        { method: "PATCH", body: { status } },
      );
      const next: WikiPageDetail =
        res && typeof res === "object" && "slug" in res ? { ...page, ...res } : { ...page, status: status as WikiPageDetail["status"] };
      updatePageLocally(next);
    } catch {
      /* keep the current status */
    }
  };

  // ---------------------------------------------------------------- dialogs & shortcuts
  const [searchOpen, setSearchOpen] = useState(false);
  const [createState, setCreateState] = useState<{ open: boolean; scope: WikiScope; mode: CreateMode | null }>({
    open: false,
    scope: GLOBAL_SCOPE,
    mode: null,
  });

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setSearchOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const openCreate = (type: string, id: string | null) => {
    const scope =
      myScopes.find((s) => s.scope_type === type && (s.scope_id ?? null) === (id ?? null)) ??
      (type === "global" ? GLOBAL_SCOPE : { scope_type: type, scope_id: id, name: type });
    setCreateState({ open: true, scope, mode: getCreateModeForScope(type, id) });
  };

  const readerMode = treeCollapsed && infoCollapsed;
  const toggleReader = () => {
    const next = !readerMode;
    setTreeCollapsed(next);
    setInfoCollapsed(next);
  };

  const fill = embedded
    ? "-m-4 md:-m-5"
    : "-mx-6 -mt-4 -mb-6 md:-mx-8 md:-mb-8 lg:-mx-10 lg:-mb-10";

  const showRight = !!page && !editing && !sourceMode;
  const visibleRefs = showAllRefs ? refs : refs.slice(0, 2);

  return (
    <div className={cn("flex h-screen min-h-0 overflow-hidden", fill)}>
      <WikiPageTree
        activeSlug={slug}
        groupByScope
        activeScope={currentScope}
        getCreateModeForScope={getCreateModeForScope}
        onPageSelect={navigate}
        linkQueryParams={scopeSuffix}
        onSearch={() => setSearchOpen(true)}
        onCreatePage={openCreate}
        onDeleted={(deleted) => {
          if (deleted === slug) goTo("/wiki/law");
        }}
      />

      <div className="min-w-0 flex-1 overflow-y-auto">
        <div className={cn("mx-auto w-full px-6 py-6 md:px-8", sourceMode ? "max-w-[72rem]" : "max-w-[54rem]")}>
          {loading ? (
            <PageSkeleton />
          ) : notFound || !page ? (
            <div className="flex flex-col items-center justify-center py-24 text-center">
              <span className="material-symbols-outlined text-muted-foreground" style={{ fontSize: 56 }}>
                find_in_page
              </span>
              <h2 className="mt-3 text-lg font-semibold">Page not found</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                {`No wiki page found for "${slug}". It may not have been compiled yet.`}
              </p>
            </div>
          ) : (
            <article className="flex flex-col gap-4">
              {/* breadcrumb */}
              <div className="flex items-center gap-2">
                <nav className="flex min-w-0 items-center gap-1 text-xs text-muted-foreground">
                  <span>Wiki</span>
                  <span className="material-symbols-outlined" style={{ fontSize: 14 }}>
                    chevron_right
                  </span>
                  <span className="truncate">{wikiTypeGroupLabel(page.page_type)}</span>
                </nav>
                <Tooltip>
                  <TooltipTrigger
                    render={
                      <button
                        type="button"
                        onClick={toggleReader}
                        className={cn(
                          "ml-auto flex items-center gap-1 rounded-md border px-2 py-1 text-xs",
                          readerMode
                            ? "border-primary/30 bg-primary/10 text-primary"
                            : "text-muted-foreground hover:bg-muted hover:text-foreground",
                        )}
                      />
                    }
                  >
                    <span className="material-symbols-outlined" style={{ fontSize: 15 }}>
                      {readerMode ? "close_fullscreen" : "open_in_full"}
                    </span>
                    {readerMode ? "Thoát chế độ đọc" : "Chế độ đọc"}
                  </TooltipTrigger>
                  <TooltipContent>
                    {readerMode ? "Hiện lại danh mục và thông tin trang" : "Ẩn danh mục và thông tin trang để đọc rộng hơn"}
                  </TooltipContent>
                </Tooltip>
              </div>

              {/* badges */}
              <div className="flex flex-wrap items-center gap-2">
                <WikiTypeBadge type={page.page_type} />
                {!sourceMode && <ScopeBadge scopeType={page.scope_type} scopeId={page.scope_id} />}
                {!NO_STATUS_TYPES.has(page.page_type) &&
                  (canEdit ? (
                    <DropdownMenu>
                      <DropdownMenuTrigger
                        render={
                          <button
                            type="button"
                            title="Đổi độ hoàn thiện"
                            className="flex items-center gap-0.5 rounded-full hover:opacity-80"
                          />
                        }
                      >
                        <WikiStatusBadge status={page.status} />
                        <span className="material-symbols-outlined text-muted-foreground" style={{ fontSize: 16 }}>
                          expand_more
                        </span>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent className="w-auto min-w-40">
                        {STATUS_CHOICES.map((s) => (
                          <DropdownMenuItem key={s} disabled={s === page.status} onClick={() => changeStatus(s)}>
                            <WikiStatusBadge status={s} />
                          </DropdownMenuItem>
                        ))}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  ) : (
                    <WikiStatusBadge status={page.status} />
                  ))}
                {!sourceMode && (
                  <span className="ml-auto font-mono text-xs text-muted-foreground" title="Phiên bản">
                    v{page.version}
                  </span>
                )}
              </div>

              {/* title */}
              <div className="flex items-start gap-3">
                <h1 className="min-w-0 flex-1 text-3xl font-bold tracking-tight">{page.title}</h1>
                {!editing && !sourceMode && (canEdit || canPropose) && (
                  <Button variant="outline" size="sm" className="mt-1.5" onClick={() => setEditState({ key: cacheKey, kind: "page" })}>
                    <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
                      edit
                    </span>
                    {canEdit ? "Chỉnh sửa" : "Đề xuất sửa"}
                  </Button>
                )}
              </div>

              {page.updated_at && (
                <p className="-mt-2 text-xs text-muted-foreground">Cập nhật lúc {formatUpdated(page.updated_at)}</p>
              )}

              {/* citation links */}
              {refs.length > 0 && (
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
                  {visibleRefs.map((r) => (
                    <button
                      key={r.id}
                      type="button"
                      onClick={() => navigate(`source/${r.id}`)}
                      className="inline-flex max-w-full items-center gap-1 text-primary hover:underline"
                    >
                      <span className="material-symbols-outlined" style={{ fontSize: 15 }}>
                        description
                      </span>
                      <span className="truncate">{sourceTitle(r.data)}</span>
                    </button>
                  ))}
                  {refs.length > 2 && (
                    <button
                      type="button"
                      onClick={() => setShowAllRefs((v) => !v)}
                      className="text-xs text-muted-foreground hover:text-foreground"
                    >
                      {showAllRefs ? "Thu gọn" : `+${refs.length - 2} tài liệu`}
                    </button>
                  )}
                </div>
              )}

              {page.knowledge_type_slugs?.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {page.knowledge_type_slugs.map((k) => (
                    <span key={k} className="rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">
                      {k}
                    </span>
                  ))}
                </div>
              )}

              {page.summary?.trim() && (
                <div className="rounded-lg border bg-muted/40 px-4 py-3">
                  <div className="mb-1 text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">Tóm tắt</div>
                  <p className="text-sm leading-relaxed">{page.summary}</p>
                </div>
              )}

              {!editing && !sourceMode && drafts.length > 0 && (
                <WikiDraftBanner
                  drafts={drafts}
                  currentContent={page.content_md}
                  currentUserId={user?.id ?? null}
                  onApproved={(id) => {
                    dropDraft(id);
                    reloadPage();
                  }}
                  onRejected={dropDraft}
                  onWithdrawn={dropDraft}
                  onChangesRequested={() => reloadDrafts()}
                  onResubmitDraft={(draft) => setEditState({ key: cacheKey, kind: "draft", draft })}
                />
              )}

              {/* body */}
              {editing?.kind === "page" ? (
                <div className="flex flex-col gap-3">
                  {!canEdit && activeBranch && (
                    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-stone-300 bg-stone-100 px-3 py-2 text-sm text-stone-700 dark:border-stone-600 dark:bg-stone-800/50 dark:text-stone-200">
                      <span className="material-symbols-outlined" style={{ fontSize: 18 }}>
                        fork_right
                      </span>
                      <span>
                        Đang lưu đóng góp vào nhánh: <strong>{activeBranch.name}</strong>
                      </span>
                      {branches.length > 1 && (
                        <Select value={activeBranch.id} onValueChange={(v) => v && setActiveBranchId(String(v))}>
                          <SelectTrigger size="sm" className="h-7 min-w-36 bg-background text-xs">
                            <SelectValue>{() => activeBranch.name}</SelectValue>
                          </SelectTrigger>
                          <SelectContent>
                            {branches.map((b) => (
                              <SelectItem key={b.id} value={b.id}>
                                {b.name}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      )}
                      <Button variant="outline" size="xs" className="ml-auto" onClick={() => setBranchModalOpen(true)}>
                        Tạo nhánh mới
                      </Button>
                    </div>
                  )}
                  <WikiEditor
                    key={`page:${cacheKey}`}
                    initialContent={page.content_md}
                    noteLabel="Change note"
                    notePlaceholder="Briefly describe what you changed (optional)"
                    saveLabel="Save Edit"
                    onSave={savePage}
                    onCancel={() => setEditState(null)}
                  />
                </div>
              ) : editing?.kind === "draft" ? (
                <WikiEditor
                  key={`draft:${editing.draft.id}`}
                  initialContent={editing.draft.content_md}
                  noteLabel="Resubmission note"
                  notePlaceholder="What changed in this round?"
                  saveLabel="Resubmit draft"
                  onSave={(content, note) => resubmitDraft(editing.draft, content, note)}
                  onCancel={() => setEditState(null)}
                />
              ) : sourceMode && sourceData ? (
                <SourceView source={sourceData} />
              ) : (
                <>
                  <WikiContent markdown={markdown} linkSuffix={scopeSuffix} onWikiLinkClick={navigate} />
                  {refs.length > 0 && (
                    <section className="mt-6 border-t pt-6">
                      <h2 className="mb-4 text-xl font-semibold">Tài liệu tham khảo ({refs.length})</h2>
                      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                        {refs.map((r, i) => (
                          <div key={r.id} className="flex flex-col gap-2 rounded-lg border p-3">
                            <span className="w-fit rounded bg-primary/10 px-1.5 py-0.5 text-[11px] font-medium text-primary">
                              Trích dẫn [{i + 1}]
                            </span>
                            <span className="line-clamp-2 text-sm font-medium">{sourceTitle(r.data)}</span>
                            <span className="text-xs text-muted-foreground">
                              {r.data.source_type === "url" ? "Liên kết Web" : `File • ${formatMb(r.data.file_size)}`}
                            </span>
                            <div className="mt-auto flex items-center gap-3 text-xs">
                              <button
                                type="button"
                                onClick={() => navigate(`source/${r.id}`)}
                                className="inline-flex items-center gap-1 text-primary hover:underline"
                              >
                                <span className="material-symbols-outlined" style={{ fontSize: 14 }}>
                                  visibility
                                </span>
                                Xem tài liệu →
                              </button>
                              {r.data.download_url && (
                                <a
                                  href={r.data.download_url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground"
                                >
                                  <span className="material-symbols-outlined" style={{ fontSize: 14 }}>
                                    cloud_download
                                  </span>
                                  Tải xuống
                                </a>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </section>
                  )}
                </>
              )}
            </article>
          )}
        </div>
      </div>

      {showRight && page && (
        <div className="hidden h-full shrink-0 xl:flex">
          {infoCollapsed ? (
            <div className="flex w-11 flex-col items-center border-l py-3">
              <Tooltip>
                <TooltipTrigger
                  render={
                    <button
                      type="button"
                      aria-label="Mở thông tin trang"
                      onClick={() => setInfoCollapsed(false)}
                      className="flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
                    />
                  }
                >
                  <span className="material-symbols-outlined" style={{ fontSize: 20 }}>
                    right_panel_open
                  </span>
                </TooltipTrigger>
                <TooltipContent side="left">Mở thông tin trang</TooltipContent>
              </Tooltip>
            </div>
          ) : (
            <div className="relative h-full">
              <Tooltip>
                <TooltipTrigger
                  render={
                    <button
                      type="button"
                      aria-label="Thu gọn thông tin trang"
                      onClick={() => setInfoCollapsed(true)}
                      className="absolute top-2 right-2 z-10 flex size-7 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
                    />
                  }
                >
                  <span className="material-symbols-outlined" style={{ fontSize: 18 }}>
                    right_panel_close
                  </span>
                </TooltipTrigger>
                <TooltipContent side="left">Thu gọn thông tin trang</TooltipContent>
              </Tooltip>
              <WikiSidebarRight slug={page.slug} page={page} linkSuffix={scopeSuffix} onSelectPage={navigate} />
            </div>
          )}
        </div>
      )}

      <WikiSearchDialog open={searchOpen} onOpenChange={setSearchOpen} onSelectPage={navigate} />

      {createState.mode && (
        <WikiCreatePageDialog
          open={createState.open}
          onOpenChange={(open) => setCreateState((prev) => ({ ...prev, open }))}
          mode={createState.mode}
          defaultScope={createState.scope}
          scopes={myScopes}
          getCreateModeForScope={getCreateModeForScope}
        />
      )}

      <BranchModal
        open={branchModalOpen}
        onClose={() => setBranchModalOpen(false)}
        scopeType={scopeType || "global"}
        scopeId={scopeId || null}
        onCreated={(b) => {
          setBranches((prev) => [b, ...prev.filter((x) => x.id !== b.id)]);
          setActiveBranchId(b.id);
        }}
      />
    </div>
  );
}

function PageSkeleton() {
  return (
    <div className="flex animate-pulse flex-col gap-4">
      <div className="h-3 w-40 rounded bg-muted" />
      <div className="h-9 w-3/4 rounded bg-muted" />
      <div className="mt-2 flex flex-col gap-2.5">
        {[92, 85, 97, 70, 88, 94, 60].map((w, i) => (
          <div key={i} className="h-3.5 rounded bg-muted" style={{ width: `${w}%` }} />
        ))}
      </div>
    </div>
  );
}

