"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  KnowledgeTable,
  SourceQuery,
  DEFAULT_QUERY,
  STATUS_GROUPS,
} from "@/components/knowledge/knowledge-table";
import { Source } from "@/components/knowledge/knowledge-table/types";
import { UploadDialog } from "@/components/knowledge/upload-dialog";
import { KnowledgeTypeCards } from "@/components/types/knowledge-type-cards";
import { KnowledgeTypeDialog } from "@/components/types/knowledge-type-dialog";
import { cn } from "@/lib/utils";

export type KnowledgeType = {
  id: string;
  slug: string;
  name: string;
  color: string;
  description?: string;
  sort_order: number;
  source_count?: number;
};

export type Department = {
  id: string;
  name: string;
};

type PaginatedSources = {
  items: Source[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};

type Tab = "documents" | "types";

const ACTIVE_STATUSES = new Set(["pending", "processing"]);

function buildParams(q: SourceQuery) {
  const params = new URLSearchParams({ page: String(q.page), page_size: String(q.pageSize), sort: q.sort });
  if (q.search) params.set("search", q.search);
  if (q.typeId) params.set("knowledge_type_id", q.typeId);
  if (q.deptId) params.set("department_id", q.deptId);
  const statuses = STATUS_GROUPS.find((g) => g.value === q.status)?.statuses;
  if (statuses) params.set("status", statuses);
  return params;
}

export default function KnowledgePage() {
  const { hasPermission } = useAuth();
  const canManage = hasPermission("org:settings:manage");

  const [tab, setTab] = useState<Tab>("documents");
  const [query, setQuery] = useState<SourceQuery>(DEFAULT_QUERY);
  const [sources, setSources] = useState<Source[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [types, setTypes] = useState<KnowledgeType[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [metaLoaded, setMetaLoaded] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [typeDialogOpen, setTypeDialogOpen] = useState(false);
  const [editType, setEditType] = useState<KnowledgeType | null>(null);
  const [notice, setNotice] = useState<{ tone: "ok" | "error"; text: string } | null>(null);

  // Drop responses from superseded queries (fast typing / paging).
  const reqId = useRef(0);
  // `loading` = the query on screen hasn't been answered yet (or a manual refresh is running).
  const queryKey = buildParams(query).toString();
  const [loadedKey, setLoadedKey] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const loading = loadedKey !== queryKey || refreshing;

  const loadSources = useCallback((q: SourceQuery, silent = false) => {
    const id = ++reqId.current;
    const key = buildParams(q).toString();
    return api<PaginatedSources>(`/api/sources?${key}`)
      .then((data) => {
        if (id !== reqId.current) return;
        setSources(data.items);
        setTotal(data.total);
        setTotalPages(Math.max(1, data.total_pages));
      })
      .catch((err) => {
        if (id !== reqId.current || silent) return;
        setSources([]);
        setTotal(0);
        setNotice({ tone: "error", text: err instanceof Error ? err.message : "Không tải được danh sách tài liệu" });
      })
      .finally(() => {
        if (id === reqId.current) setLoadedKey(key);
      });
  }, []);

  const loadMeta = useCallback(
    () =>
      Promise.all([api<KnowledgeType[]>("/api/knowledge-types"), api<Department[]>("/api/departments")])
        .then(([typesData, deptsData]) => {
          setTypes(typesData);
          setDepartments(deptsData);
        })
        .catch(() => {
          setTypes([]);
          setDepartments([]);
        })
        .finally(() => setMetaLoaded(true)),
    [],
  );

  useEffect(() => {
    loadMeta();
  }, [loadMeta]);

  useEffect(() => {
    loadSources(query);
  }, [query, loadSources]);

  // Poll quietly only while something on screen is still being processed.
  const hasActive = sources.some((s) => ACTIVE_STATUSES.has(s.status));
  useEffect(() => {
    if (!hasActive) return;
    const h = setInterval(() => loadSources(query, true), 3000);
    return () => clearInterval(h);
  }, [hasActive, query, loadSources]);

  const patchQuery = useCallback((patch: Partial<SourceQuery>) => setQuery((q) => ({ ...q, ...patch })), []);
  const refreshAll = () => {
    setRefreshing(true);
    Promise.all([loadSources(query), loadMeta()]).finally(() => setRefreshing(false));
  };

  const runBackfill = async (onlyMissing: boolean) => {
    const label = onlyMissing ? "các tài liệu còn thiếu thuộc tính" : "toàn bộ tài liệu";
    if (!confirm(`Trích xuất lại số hiệu, ngày ban hành, hiệu lực... cho ${label}? Việc này chạy nền và có thể dùng LLM.`)) return;
    try {
      await api(`/api/wiki/legal-docs/backfill?only_missing=${onlyMissing}&use_llm=true`, { method: "POST" });
      setNotice({ tone: "ok", text: "Đã đưa vào hàng đợi. Thuộc tính văn bản sẽ cập nhật sau ít phút." });
    } catch (err) {
      setNotice({ tone: "error", text: err instanceof Error ? err.message : "Không chạy được trích xuất" });
    }
  };

  const tabs: { value: Tab; label: string; icon: string; count: number }[] = [
    { value: "documents", label: "Tài liệu", icon: "description", count: total },
    { value: "types", label: "Danh mục", icon: "category", count: types.length },
  ];

  return (
    <div className="flex flex-col gap-5">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">Kho tri thức</h1>
          <p className="mt-1 text-sm text-muted-foreground">Quản lý và tổ chức tài liệu và danh mục của tổ chức bạn.</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" className="h-9 gap-1.5" onClick={refreshAll} disabled={loading}>
            <span className={cn("material-symbols-outlined", loading && "animate-spin")} style={{ fontSize: 18 }}>
              {loading ? "progress_activity" : "sync"}
            </span>
            Làm mới
          </Button>
          <Button size="sm" className="h-9 gap-1.5" onClick={() => setUploadOpen(true)}>
            <span className="material-symbols-outlined" style={{ fontSize: 18 }}>upload</span>
            Tải lên
          </Button>
        </div>
      </div>

      {/* Tabs + contextual action */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="inline-flex rounded-lg bg-muted p-1" role="tablist">
          {tabs.map((tb) => (
            <button
              key={tb.value}
              type="button"
              role="tab"
              aria-selected={tab === tb.value}
              onClick={() => setTab(tb.value)}
              className={cn(
                "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors cursor-pointer",
                tab === tb.value ? "bg-background text-foreground shadow-xs" : "text-muted-foreground hover:text-foreground",
              )}
            >
              <span className="material-symbols-outlined" style={{ fontSize: 17 }}>{tb.icon}</span>
              {tb.label}
              <span
                className={cn(
                  "rounded-full px-1.5 text-[11px] tabular-nums",
                  tab === tb.value ? "bg-primary/10 text-primary" : "bg-background/60 text-muted-foreground",
                )}
              >
                {tb.count}
              </span>
            </button>
          ))}
        </div>

        {tab === "documents" ? (
          canManage && (
            <DropdownMenu>
              <DropdownMenuTrigger className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-border bg-background px-3 text-xs font-medium hover:bg-accent cursor-pointer">
                <span className="material-symbols-outlined" style={{ fontSize: 16 }}>auto_fix_high</span>
                Xử lý nội dung
                <span className="material-symbols-outlined" style={{ fontSize: 16 }}>expand_more</span>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="min-w-64">
                <DropdownMenuItem onClick={() => runBackfill(true)}>
                  <span className="material-symbols-outlined mr-2" style={{ fontSize: 16 }}>data_info_alert</span>
                  Trích xuất thuộc tính còn thiếu
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => runBackfill(false)}>
                  <span className="material-symbols-outlined mr-2" style={{ fontSize: 16 }}>restart_alt</span>
                  Trích xuất lại toàn bộ thuộc tính
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => patchQuery({ status: "failed", page: 1 })}>
                  <span className="material-symbols-outlined mr-2" style={{ fontSize: 16 }}>error</span>
                  Xem tài liệu lỗi
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => patchQuery({ status: "review", page: 1 })}>
                  <span className="material-symbols-outlined mr-2" style={{ fontSize: 16 }}>fact_check</span>
                  Xem tài liệu chờ duyệt
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )
        ) : (
          <Button size="sm" variant="outline" className="h-8 gap-1.5 text-xs" onClick={() => { setEditType(null); setTypeDialogOpen(true); }}>
            <span className="material-symbols-outlined" style={{ fontSize: 16 }}>add</span>
            Thêm danh mục
          </Button>
        )}
      </div>

      {notice && (
        <div
          className={cn(
            "flex items-center gap-2 rounded-lg px-3 py-2 text-xs",
            notice.tone === "ok" ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400" : "bg-destructive/10 text-destructive",
          )}
        >
          <span className="material-symbols-outlined" style={{ fontSize: 16 }}>{notice.tone === "ok" ? "check_circle" : "error"}</span>
          <span className="flex-1">{notice.text}</span>
          <button type="button" onClick={() => setNotice(null)} className="cursor-pointer">
            <span className="material-symbols-outlined" style={{ fontSize: 16 }}>close</span>
          </button>
        </div>
      )}

      {tab === "documents" ? (
        <KnowledgeTable
          sources={sources}
          types={types}
          departments={departments}
          loading={loading}
          total={total}
          totalPages={totalPages}
          query={query}
          onQueryChange={patchQuery}
          onRefresh={() => { loadSources(query, true); loadMeta(); }}
          onUpload={() => setUploadOpen(true)}
        />
      ) : (
        <KnowledgeTypeCards
          types={types}
          loading={!metaLoaded}
          onEdit={(kt) => { setEditType(kt); setTypeDialogOpen(true); }}
          onCreate={() => { setEditType(null); setTypeDialogOpen(true); }}
          onRefresh={() => { loadMeta(); loadSources(query, true); }}
          onViewDocuments={(typeId) => {
            setQuery({ ...DEFAULT_QUERY, typeId });
            setTab("documents");
          }}
        />
      )}

      <UploadDialog
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        types={types}
        departments={departments}
        onUploaded={() => {
          // Newest first so the fresh upload is visible right away.
          setQuery((q) => ({ ...q, sort: "created_desc", page: 1 }));
          loadSources({ ...query, sort: "created_desc", page: 1 }, true);
          loadMeta();
        }}
      />

      <KnowledgeTypeDialog
        open={typeDialogOpen}
        onOpenChange={setTypeDialogOpen}
        knowledgeType={editType}
        onSaved={loadMeta}
      />
    </div>
  );
}
