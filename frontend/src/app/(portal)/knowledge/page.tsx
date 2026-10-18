"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  DEFAULT_QUERY,
  KnowledgeTable,
  STATUS_GROUPS,
  type SourceQuery,
} from "@/components/knowledge/knowledge-table";
import { isRunning } from "@/components/knowledge/knowledge-table/utils";
import {
  errorText,
  type Department,
  type KnowledgeType,
  type Source,
  type SourceListResponse,
} from "@/components/knowledge/types";
import { UploadDialog } from "@/components/knowledge/upload-dialog";
import { KnowledgeTypeCards } from "@/components/types/knowledge-type-cards";
import { KnowledgeTypeDialog } from "@/components/types/knowledge-type-dialog";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

type Tab = "documents" | "types";
type Notice = { tone: "ok" | "error"; text: string };
/** Counts from GET /api/sources/processing-summary, scoped to what the user may read. */
type ProcessingSummary = {
  failed: number;
  failed_ai_outage: number;
  running: number;
  review: number;
  chunk_missing: number;
  pages_missing_vectors: number;
};

const POLL_MS = 3000;

function queryString(q: SourceQuery): string {
  const params = new URLSearchParams({
    page: String(q.page),
    page_size: String(q.pageSize),
    sort: q.sort,
  });
  if (q.search) params.set("search", q.search);
  if (q.typeId) params.set("knowledge_type_id", q.typeId);
  if (q.deptId) params.set("department_id", q.deptId);
  const status = STATUS_GROUPS.find((g) => g.value === q.status)?.apiStatus;
  if (status) params.set("status", status);
  return params.toString();
}

function Icon({ name, size = 16, className }: { name: string; size?: number; className?: string }) {
  return (
    <span className={cn("material-symbols-outlined", className)} style={{ fontSize: size }}>
      {name}
    </span>
  );
}

/** One menu row; an action whose count is known to be 0 is disabled (views stay clickable). */
function MenuAction({
  icon,
  label,
  count,
  onClick,
  view = false,
}: {
  icon: string;
  label: string;
  count?: number;
  onClick: () => void;
  view?: boolean;
}) {
  return (
    <DropdownMenuItem onClick={onClick} disabled={!view && count === 0}>
      <Icon name={icon} />
      <span className="flex-1">{label}</span>
      {count !== undefined && (
        <span
          className={cn(
            "ml-3 rounded-full px-1.5 text-[11px] tabular-nums",
            count > 0 ? "bg-muted text-foreground" : "text-muted-foreground"
          )}
        >
          {count}
        </span>
      )}
    </DropdownMenuItem>
  );
}

function fetchMeta(): Promise<{ types: KnowledgeType[]; departments: Department[] }> {
  return Promise.all([api<KnowledgeType[]>("/api/knowledge-types"), api<Department[]>("/api/departments")])
    .then(([types, departments]) => ({
      types: Array.isArray(types) ? types : [],
      departments: Array.isArray(departments) ? departments : [],
    }))
    .catch(() => ({ types: [], departments: [] }));
}

export default function KnowledgePage() {
  const { hasPermission } = useAuth();
  const canManage = hasPermission("org:settings:manage");

  const [tab, setTab] = useState<Tab>("documents");
  const [query, setQuery] = useState<SourceQuery>(DEFAULT_QUERY);
  const [sources, setSources] = useState<Source[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  /** Query string of the most recent list response that was applied. */
  const [answeredKey, setAnsweredKey] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [types, setTypes] = useState<KnowledgeType[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [metaLoaded, setMetaLoaded] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [typeDialogOpen, setTypeDialogOpen] = useState(false);
  const [editingType, setEditingType] = useState<KnowledgeType | null>(null);

  const seqRef = useRef(0);
  const currentKey = queryString(query);
  const loading = answeredKey !== currentKey || refreshing;

  /** Fetch one page of sources; responses older than the latest request are dropped. */
  const loadList = useCallback((q: SourceQuery, silent: boolean): Promise<void> => {
    const seq = ++seqRef.current;
    const key = queryString(q);
    return api<SourceListResponse>(`/api/sources?${key}`)
      .then((res) => {
        if (seq !== seqRef.current) return;
        setSources(res.items ?? []);
        setTotal(res.total ?? 0);
        setTotalPages(Math.max(1, res.total_pages ?? 1));
        setAnsweredKey(key);
      })
      .catch((err: unknown) => {
        if (seq !== seqRef.current) return;
        setAnsweredKey(key);
        if (silent) return;
        setSources([]);
        setTotal(0);
        setTotalPages(1);
        setNotice({ tone: "error", text: errorText(err, "Không tải được danh sách tài liệu") });
      });
  }, []);

  const loadMeta = useCallback(() => {
    return fetchMeta().then((m) => {
      setTypes(m.types);
      setDepartments(m.departments);
      setMetaLoaded(true);
    });
  }, []);

  // Initial metadata.
  useEffect(() => {
    let cancelled = false;
    fetchMeta().then((m) => {
      if (cancelled) return;
      setTypes(m.types);
      setDepartments(m.departments);
      setMetaLoaded(true);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // List follows the query.
  useEffect(() => {
    const timer = setTimeout(() => {
      void loadList(query, false);
    }, 0);
    return () => clearTimeout(timer);
  }, [currentKey, query, loadList]);

  // Background polling while something on this page is still running.
  const hasRunning = sources.some(isRunning);
  useEffect(() => {
    if (!hasRunning) return;
    const timer = setInterval(() => {
      void loadList(query, true);
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [hasRunning, query, loadList]);

  const onQueryChange = useCallback((patch: Partial<SourceQuery>) => {
    setQuery((prev) => ({ ...prev, ...patch }));
  }, []);

  const refreshAll = () => {
    setRefreshing(true);
    void Promise.all([loadList(query, false), loadMeta()]).finally(() => setRefreshing(false));
  };

  const [summary, setSummary] = useState<ProcessingSummary | null>(null);
  const loadSummary = useCallback(() => {
    if (!canManage) return;
    api<ProcessingSummary>("/api/sources/processing-summary")
      .then(setSummary)
      .catch(() => setSummary(null));
  }, [canManage]);

  // Menu counts follow the list: refreshed when a list response lands or polling stops.
  useEffect(() => {
    if (answeredKey !== null) loadSummary();
  }, [answeredKey, total, hasRunning, loadSummary]);

  /** Confirm, POST, show the server's message, then refresh the list and the counts. */
  const runAction = async (question: string, path: string, okText: string, failText: string) => {
    if (!confirm(question)) return;
    try {
      const res = await api<{ message?: string }>(path, { method: "POST" });
      setNotice({ tone: "ok", text: res?.message || okText });
    } catch (err) {
      setNotice({ tone: "error", text: errorText(err, failText) });
    }
    void loadList(query, true);
    loadSummary();
  };

  const retryFailed = (onlyAiOutage: boolean) =>
    runAction(
      onlyAiOutage
        ? `Chạy lại ${summary?.failed_ai_outage ?? ""} tài liệu lỗi do dịch vụ AI gián đoạn?`
        : `Chạy lại ${summary?.failed ?? ""} tài liệu lỗi hoặc xử lý một phần? Mỗi tài liệu chỉ chạy lại phần bị lỗi.`,
      `/api/sources/retry-failed?only_ai_outage=${onlyAiOutage}`,
      "Đã xếp hàng chạy lại tài liệu lỗi.",
      "Không chạy lại được tài liệu lỗi"
    );

  const backfill = (onlyMissing: boolean) =>
    runAction(
      `Trích xuất lại số hiệu, ngày ban hành, hiệu lực... cho ${
        onlyMissing ? "các tài liệu còn thiếu thuộc tính" : "toàn bộ tài liệu"
      }? Việc này chạy nền và có thể dùng LLM.`,
      `/api/wiki/legal-docs/backfill?only_missing=${onlyMissing}&use_llm=true`,
      "Đã đưa vào hàng đợi. Thuộc tính văn bản sẽ cập nhật sau ít phút.",
      "Không chạy được trích xuất"
    );

  const reembedMissing = () =>
    runAction(
      `Tạo vector tìm kiếm cho ${summary?.pages_missing_vectors ?? ""} trang tri thức đang thiếu?`,
      "/api/sources/reembed-missing",
      "Đã xếp hàng tạo vector.",
      "Không tạo được vector"
    );

  const backfillChunks = () =>
    runAction(
      `Tạo chunk văn bản gốc cho ${summary?.chunk_missing ?? ""} tài liệu còn thiếu?`,
      "/api/settings/embeddings/backfill-source-chunks",
      "Đã xếp hàng tạo chunk văn bản gốc.",
      "Không tạo được chunk văn bản gốc"
    );

  const showGroup = (status: SourceQuery["status"]) => onQueryChange({ status, page: 1 });

  const tabs: { id: Tab; label: string; icon: string; count: number }[] = [
    { id: "documents", label: "Tài liệu", icon: "description", count: total },
    { id: "types", label: "Kiểu tri thức", icon: "category", count: types.length },
  ];

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Kho tri thức</h1>
          <p className="text-sm text-muted-foreground">Quản lý và tổ chức tài liệu và kiểu tri thức của tổ chức bạn.</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" className="h-9 gap-1.5" onClick={refreshAll} disabled={refreshing}>
            <Icon name={refreshing ? "progress_activity" : "sync"} className={cn(refreshing && "animate-spin")} />
            Làm mới
          </Button>
          <Button size="sm" className="h-9 gap-1.5" onClick={() => setUploadOpen(true)}>
            <Icon name="upload" />
            Tải lên
          </Button>
        </div>
      </div>

      {/* Tabs + contextual action */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div role="tablist" className="inline-flex rounded-lg bg-muted p-1">
          {tabs.map((tb) => {
            const active = tab === tb.id;
            return (
              <button
                key={tb.id}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => setTab(tb.id)}
                className={cn(
                  "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                  active ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
                )}
              >
                <Icon name={tb.icon} size={17} />
                {tb.label}
                <span
                  className={cn(
                    "rounded-full px-1.5 text-[11px] tabular-nums",
                    active ? "bg-primary/10 text-primary" : "bg-background/60"
                  )}
                >
                  {tb.count}
                </span>
              </button>
            );
          })}
        </div>

        {tab === "documents" && canManage && (
          <DropdownMenu onOpenChange={(open) => open && loadSummary()}>
            <DropdownMenuTrigger className="inline-flex h-8 items-center gap-1.5 rounded-[10px] border bg-background px-3 text-xs font-medium hover:bg-secondary">
              <Icon name="auto_fix_high" />
              Xử lý nội dung
              {!!summary?.failed && (
                <span className="rounded-full bg-destructive/10 px-1.5 text-[11px] text-destructive tabular-nums">
                  {summary.failed} lỗi
                </span>
              )}
              <Icon name="expand_more" />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="min-w-72">
              <DropdownMenuGroup>
                <DropdownMenuLabel>Chạy lại</DropdownMenuLabel>
                <MenuAction
                  icon="replay"
                  label="Chạy lại tất cả tài liệu lỗi"
                  count={summary?.failed}
                  onClick={() => void retryFailed(false)}
                />
                {!!summary?.failed_ai_outage && summary.failed_ai_outage < summary.failed && (
                  <MenuAction
                    icon="cloud_off"
                    label="Chỉ chạy lại lỗi do AI gián đoạn"
                    count={summary.failed_ai_outage}
                    onClick={() => void retryFailed(true)}
                  />
                )}
              </DropdownMenuGroup>
              <DropdownMenuSeparator />
              <DropdownMenuGroup>
                <DropdownMenuLabel>Thuộc tính văn bản</DropdownMenuLabel>
                <MenuAction icon="data_info_alert" label="Trích xuất thuộc tính còn thiếu" onClick={() => void backfill(true)} />
                <MenuAction icon="restart_alt" label="Trích xuất lại toàn bộ thuộc tính" onClick={() => void backfill(false)} />
              </DropdownMenuGroup>
              <DropdownMenuSeparator />
              <DropdownMenuGroup>
                <DropdownMenuLabel>Chỉ mục tìm kiếm</DropdownMenuLabel>
                <MenuAction
                  icon="hub"
                  label="Tạo vector cho trang còn thiếu"
                  count={summary?.pages_missing_vectors}
                  onClick={() => void reembedMissing()}
                />
                <MenuAction
                  icon="segment"
                  label="Tạo chunk văn bản gốc còn thiếu"
                  count={summary?.chunk_missing}
                  onClick={() => void backfillChunks()}
                />
              </DropdownMenuGroup>
              <DropdownMenuSeparator />
              <DropdownMenuGroup>
                <DropdownMenuLabel>Xem nhanh</DropdownMenuLabel>
                <MenuAction icon="error" label="Tài liệu lỗi" count={summary?.failed} onClick={() => showGroup("failed")} view />
                <MenuAction
                  icon="progress_activity"
                  label="Đang xử lý"
                  count={summary?.running}
                  onClick={() => showGroup("running")}
                  view
                />
                <MenuAction icon="fact_check" label="Chờ duyệt" count={summary?.review} onClick={() => showGroup("review")} view />
              </DropdownMenuGroup>
            </DropdownMenuContent>
          </DropdownMenu>
        )}

        {tab === "types" && (
          <Button
            variant="outline"
            size="sm"
            className="h-8 text-xs"
            onClick={() => {
              setEditingType(null);
              setTypeDialogOpen(true);
            }}
          >
            <Icon name="add" />
            Thêm kiểu tri thức
          </Button>
        )}
      </div>

      {notice && (
        <div
          className={cn(
            "flex items-start gap-2 rounded-lg px-3 py-2 text-xs",
            notice.tone === "ok"
              ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
              : "bg-destructive/10 text-destructive"
          )}
        >
          <Icon name={notice.tone === "ok" ? "check_circle" : "error"} className="shrink-0" />
          <span className="flex-1">{notice.text}</span>
          <button type="button" aria-label="Đóng" onClick={() => setNotice(null)} className="opacity-70 hover:opacity-100">
            <Icon name="close" />
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
          onQueryChange={onQueryChange}
          onRefresh={() => {
            void loadList(query, true);
            void loadMeta();
          }}
          onUpload={() => setUploadOpen(true)}
        />
      ) : (
        <KnowledgeTypeCards
          types={types}
          loading={!metaLoaded}
          onEdit={(kt) => {
            setEditingType(kt);
            setTypeDialogOpen(true);
          }}
          onCreate={() => {
            setEditingType(null);
            setTypeDialogOpen(true);
          }}
          onRefresh={() => {
            void loadMeta();
            void loadList(query, true);
          }}
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
          const next = { ...query, sort: "created_desc", page: 1 };
          setQuery(next);
          void loadList(next, true);
          void loadMeta();
        }}
      />
      <KnowledgeTypeDialog
        open={typeDialogOpen}
        onOpenChange={setTypeDialogOpen}
        knowledgeType={editingType}
        onSaved={() => void loadMeta()}
      />
    </div>
  );
}
