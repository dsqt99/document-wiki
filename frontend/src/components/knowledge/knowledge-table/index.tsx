"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Fragment, useEffect, useState, type ReactNode } from "react";
import { EmptyState } from "@/components/shared/empty-state";
import { ScopeBadge } from "@/components/shared/scope-badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { VALIDITY_INFO, formatViDate } from "@/lib/legal-doc";
import { cn } from "@/lib/utils";
import { TypePill } from "../type-pill";
import { errorText, type Department, type KnowledgeType, type Source } from "../types";
import { EditSourceDialog } from "./edit-source-dialog";
import { ExtractionReviewDialog } from "./extraction-review-dialog";
import { PlanReviewDialog } from "./plan-review-dialog";
import { SourceArticlesDrawer } from "./source-articles-drawer";
import { StatusDot } from "./status-dot";
import {
  formatCreatedDate,
  hasBranchRetry,
  isFailed,
  lawKey,
  sourceIcon,
} from "./utils";

export type StatusGroup = "" | "ready" | "running" | "review" | "failed";

export const STATUS_GROUPS: { value: StatusGroup; label: string; apiStatus: string }[] = [
  { value: "", label: "Tất cả trạng thái", apiStatus: "" },
  { value: "ready", label: "Sẵn sàng", apiStatus: "ready" },
  { value: "running", label: "Đang xử lý", apiStatus: "pending,processing" },
  { value: "review", label: "Chờ duyệt", apiStatus: "plan_ready,awaiting_approval" },
  { value: "failed", label: "Lỗi / một phần", apiStatus: "error,partial" },
];

export type SourceQuery = {
  search: string;
  typeId: string;
  deptId: string;
  status: StatusGroup;
  /** `{field}_{asc|desc}` */
  sort: string;
  page: number;
  pageSize: number;
};

export const DEFAULT_QUERY: SourceQuery = {
  search: "",
  typeId: "",
  deptId: "",
  status: "",
  sort: "created_desc",
  page: 1,
  pageSize: 20,
};

const PAGE_SIZES = [10, 20, 50, 100];
const COLUMN_COUNT = 7;

type SortField = "title" | "issued" | "effective" | "created";

type Props = {
  sources: Source[];
  types: KnowledgeType[];
  departments: Department[];
  loading: boolean;
  total: number;
  totalPages: number;
  query: SourceQuery;
  onQueryChange: (patch: Partial<SourceQuery>) => void;
  onRefresh: () => void;
  onUpload: () => void;
};

type RetryBranch = "chunk" | "wiki" | "all" | null;

const FILTER_CONTROL =
  "h-8 rounded-[10px] border border-border bg-background text-xs outline-none focus:ring-2 focus:ring-primary/30";

function parseSort(sort: string): { field: string; dir: "asc" | "desc" } {
  const idx = sort.lastIndexOf("_");
  if (idx < 0) return { field: sort, dir: "desc" };
  const dir = sort.slice(idx + 1) === "asc" ? "asc" : "desc";
  return { field: sort.slice(0, idx), dir };
}

function Dash() {
  return <span className="text-muted-foreground/50">—</span>;
}

function Icon({ name, size = 16, className }: { name: string; size?: number; className?: string }) {
  return (
    <span className={cn("material-symbols-outlined", className)} style={{ fontSize: size }}>
      {name}
    </span>
  );
}

function NativeSelect({
  value,
  onChange,
  children,
  ariaLabel,
  className,
}: {
  value: string;
  onChange: (v: string) => void;
  children: ReactNode;
  ariaLabel: string;
  className?: string;
}) {
  return (
    <div className={cn("relative", className)}>
      <select
        value={value}
        aria-label={ariaLabel}
        onChange={(e) => onChange(e.target.value)}
        className={cn(FILTER_CONTROL, "w-full cursor-pointer appearance-none pr-7 pl-2.5")}
      >
        {children}
      </select>
      <Icon
        name="expand_more"
        size={16}
        className="pointer-events-none absolute top-1/2 right-1.5 -translate-y-1/2 text-gray-400"
      />
    </div>
  );
}

function Banner({ message, onClose }: { message: string; onClose: () => void }) {
  return (
    <div className="flex items-start gap-2 rounded-lg bg-destructive/10 px-3 py-2 text-xs text-destructive">
      <Icon name="error" size={16} className="shrink-0" />
      <span className="flex-1">{message}</span>
      <button type="button" onClick={onClose} aria-label="Đóng" className="shrink-0 opacity-70 hover:opacity-100">
        <Icon name="close" size={16} />
      </button>
    </div>
  );
}

/** Paged, filterable table of uploaded sources with row/bulk actions. */
export function KnowledgeTable({
  sources,
  types,
  departments,
  loading,
  total,
  totalPages,
  query,
  onQueryChange,
  onRefresh,
  onUpload,
}: Props) {
  const { t } = useI18n();
  const router = useRouter();

  // Search box text mirrors query.search, but may run ahead of it while debouncing.
  const [searchText, setSearchText] = useState(query.search);
  const [syncedSearch, setSyncedSearch] = useState(query.search);
  if (syncedSearch !== query.search) {
    setSyncedSearch(query.search);
    setSearchText(query.search);
  }

  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const [bulkBusy, setBulkBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState<Set<string>>(() => new Set());
  const [expanded, setExpanded] = useState<string | null>(null);
  const [expandedInfo, setExpandedInfo] = useState<string | null>(null);
  const [editing, setEditing] = useState<Source | null>(null);
  const [planFor, setPlanFor] = useState<Source | null>(null);
  const [extractionFor, setExtractionFor] = useState<Source | null>(null);

  useEffect(() => {
    const trimmed = searchText.trim();
    if (trimmed === query.search) return;
    const timer = setTimeout(() => onQueryChange({ search: trimmed, page: 1 }), 350);
    return () => clearTimeout(timer);
  }, [searchText, query.search, onQueryChange]);

  const hasFilter = !!(query.search || query.typeId || query.deptId || query.status);
  const { field: sortField, dir: sortDir } = parseSort(query.sort);

  const selectedRows = sources.filter((s) => selected.has(s.id));
  const failedSelected = selectedRows.filter(isFailed);
  const allSelected = sources.length > 0 && selectedRows.length === sources.length;
  const someSelected = selectedRows.length > 0 && !allSelected;

  const deptName = (id: string) => departments.find((d) => d.id === id)?.name;

  const clearFilters = () => {
    setSearchText("");
    onQueryChange({ search: "", typeId: "", deptId: "", status: "", page: 1 });
  };

  const toggleSort = (f: SortField) => {
    let dir: "asc" | "desc";
    if (sortField === f) dir = sortDir === "asc" ? "desc" : "asc";
    else dir = f === "title" ? "asc" : "desc";
    onQueryChange({ sort: `${f}_${dir}`, page: 1 });
  };

  const toggleRow = (id: string, checked: boolean) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (checked) next.add(id);
      else next.delete(id);
      return next;
    });
  };

  const toggleAll = (checked: boolean) => {
    setSelected(checked ? new Set(sources.map((s) => s.id)) : new Set());
  };

  const runBulk = async (rows: Source[], action: (s: Source) => Promise<unknown>) => {
    setActionError(null);
    setBulkBusy(true);
    const failures: { title: string; message: string }[] = [];
    for (const row of rows) {
      try {
        await action(row);
      } catch (err) {
        failures.push({ title: row.title, message: errorText(err, "lỗi") });
      }
    }
    setBulkBusy(false);
    setSelected(new Set());
    if (failures.length > 0) {
      const first = failures[0];
      setActionError(`${failures.length}/${rows.length} thao tác thất bại — ${first.title}: ${first.message}`);
    }
    onRefresh();
  };

  const bulkDelete = () => {
    if (!confirm(`Xóa ${selectedRows.length} tài liệu đã chọn? Thao tác không thể hoàn tác.`)) return;
    void runBulk(selectedRows, (s) => api(`/api/sources/${s.id}`, { method: "DELETE" }));
  };

  const bulkRetry = () => {
    void runBulk(failedSelected, (s) => api(`/api/sources/${s.id}/retry`, { method: "POST" }));
  };

  const retryRow = async (s: Source, branch: RetryBranch) => {
    setActionError(null);
    setRetrying((prev) => new Set(prev).add(s.id));
    try {
      const qs = branch ? `?branch=${branch}` : "";
      await api(`/api/sources/${s.id}/retry${qs}`, { method: "POST" });
      onRefresh();
    } catch (err) {
      setActionError(errorText(err, "Không chạy lại được"));
    } finally {
      setRetrying((prev) => {
        const next = new Set(prev);
        next.delete(s.id);
        return next;
      });
    }
  };

  const deleteRow = async (s: Source) => {
    if (!confirm(t("knowledge.deleteConfirm"))) return;
    setActionError(null);
    try {
      await api(`/api/sources/${s.id}`, { method: "DELETE" });
      setSelected((prev) => {
        const next = new Set(prev);
        next.delete(s.id);
        return next;
      });
      onRefresh();
    } catch (err) {
      setActionError(errorText(err, "Không xóa được tài liệu"));
    }
  };

  const downloadRow = async (s: Source) => {
    setActionError(null);
    try {
      const detail = await api<{ download_url?: string | null }>(`/api/sources/${s.id}`);
      if (detail.download_url) window.open(detail.download_url, "_blank", "noopener,noreferrer");
    } catch (err) {
      setActionError(errorText(err, "Không tải được tệp"));
    }
  };

  const sortHeader = (label: string, f: SortField) => {
    const active = sortField === f;
    return (
      <button
        type="button"
        onClick={() => toggleSort(f)}
        className={cn("inline-flex items-center gap-0.5 uppercase hover:text-foreground", active && "text-foreground")}
      >
        {label}
        <Icon
          name={active ? (sortDir === "asc" ? "arrow_upward" : "arrow_downward") : "unfold_more"}
          size={14}
          className={cn(!active && "opacity-30")}
        />
      </button>
    );
  };

  const from = total > 0 ? (query.page - 1) * query.pageSize + 1 : 0;
  const to = Math.min(query.page * query.pageSize, total);

  const th = "px-3 py-3 text-left align-middle text-xs font-medium text-muted-foreground";
  const td = "px-3 py-3.5 align-middle";
  const thPlain = "align-middle text-xs font-medium text-foreground";

  return (
    <div className="flex flex-col gap-3">
      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative w-full sm:w-64">
          <Icon
            name="search"
            size={16}
            className="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-muted-foreground"
          />
          <input
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            placeholder="Tìm kiếm tài liệu..."
            className={cn(FILTER_CONTROL, "w-full pr-7 pl-8")}
          />
          {searchText && (
            <button
              type="button"
              title="Xóa"
              aria-label="Xóa"
              onClick={() => setSearchText("")}
              className="absolute top-1/2 right-2 flex -translate-y-1/2 text-muted-foreground hover:text-foreground"
            >
              <Icon name="close" size={14} />
            </button>
          )}
        </div>

        <NativeSelect
          ariaLabel="Kiểu tri thức"
          value={query.typeId}
          onChange={(v) => onQueryChange({ typeId: v, page: 1 })}
        >
          <option value="">Tất cả kiểu tri thức</option>
          {types.map((ty) => (
            <option key={ty.id} value={ty.id}>
              {ty.name}
            </option>
          ))}
        </NativeSelect>

        {departments.length > 0 && (
          <NativeSelect
            ariaLabel="Phòng ban"
            value={query.deptId}
            onChange={(v) => onQueryChange({ deptId: v, page: 1 })}
          >
            <option value="">Tất cả phòng ban</option>
            {departments.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </NativeSelect>
        )}

        <NativeSelect
          ariaLabel="Trạng thái"
          value={query.status}
          onChange={(v) => onQueryChange({ status: v as StatusGroup, page: 1 })}
        >
          {STATUS_GROUPS.map((g) => (
            <option key={g.value || "all"} value={g.value}>
              {g.label}
            </option>
          ))}
        </NativeSelect>

        {hasFilter && (
          <button
            type="button"
            onClick={clearFilters}
            className="inline-flex h-8 items-center gap-1 rounded-md px-2 text-xs text-muted-foreground hover:bg-secondary hover:text-foreground"
          >
            <Icon name="filter_alt_off" size={15} />
            Xóa lọc
          </button>
        )}

        <NativeSelect ariaLabel="Sắp xếp tài liệu" value={query.sort} onChange={(sort) => onQueryChange({ sort, page: 1 })}>
          <option value="created_desc">Mới tải lên</option><option value="created_asc">Cũ nhất</option>
          <option value="title_asc">Tên A → Z</option><option value="title_desc">Tên Z → A</option><option value="issued_desc">Mới ban hành</option><option value="issued_asc">Ban hành cũ nhất</option><option value="effective_desc">Mới có hiệu lực</option><option value="effective_asc">Hiệu lực cũ nhất</option>
        </NativeSelect>
      </div>

      {/* Bulk bar */}
      {selectedRows.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-primary/30 bg-primary/5 px-3 py-1.5 text-xs">
          <span className="font-medium">Đã chọn {selectedRows.length}</span>
          <button
            type="button"
            onClick={() => setSelected(new Set())}
            className="text-muted-foreground hover:text-foreground hover:underline"
          >
            Bỏ chọn
          </button>
          <div className="ml-auto flex items-center gap-2">
            {failedSelected.length > 0 && (
              <Button variant="outline" size="sm" disabled={bulkBusy} onClick={bulkRetry}>
                <Icon name="refresh" size={15} />
                Chạy lại ({failedSelected.length})
              </Button>
            )}
            <Button
              variant="outline"
              size="sm"
              disabled={bulkBusy}
              onClick={bulkDelete}
              className="text-destructive hover:text-destructive"
            >
              <Icon name={bulkBusy ? "progress_activity" : "delete"} size={15} className={cn(bulkBusy && "animate-spin")} />
              Xóa
            </Button>
          </div>
        </div>
      )}

      {actionError && <Banner message={actionError} onClose={() => setActionError(null)} />}

      {/* Table frame */}
      <div className="overflow-hidden rounded-xl border bg-card">
        {sources.length === 0 ? (
          loading ? (
            <div className="flex justify-center py-16 text-muted-foreground">
              <Icon name="progress_activity" size={30} className="animate-spin" />
            </div>
          ) : hasFilter ? (
            <EmptyState
              icon="search_off"
              title="Không có tài liệu phù hợp"
              description="Thử đổi từ khóa hoặc bỏ bớt bộ lọc."
              action={
                <Button variant="outline" size="sm" onClick={clearFilters}>
                  Xóa bộ lọc
                </Button>
              }
            />
          ) : (
            <EmptyState
              icon="cloud_upload"
              title="Chưa có tài liệu nào"
              description="Tải lên văn bản đầu tiên để bắt đầu xây dựng kho tri thức."
              action={
                <Button size="sm" onClick={onUpload}>
                  Tải lên tài liệu
                </Button>
              }
            />
          )
        ) : (
          <div className={cn("overflow-x-auto transition-opacity", loading && "opacity-60")}>
            <table className="w-full table-auto border-collapse text-xs">
              <thead>
                <tr className="h-10 border-b bg-muted/30">
                  <th className={cn(thPlain, "w-[25px] py-0 pl-3")}>
                    <input
                      type="checkbox"
                      aria-label="Chọn tất cả"
                      className="size-[13px] cursor-pointer accent-primary"
                      checked={allSelected}
                      ref={(el) => {
                        if (el) el.indeterminate = someSelected;
                      }}
                      onChange={(e) => toggleAll(e.target.checked)}
                    />
                  </th>
                  <th className={th}>{sortHeader("Tài liệu", "title")}</th>
                  <th className={cn(th, "hidden xl:table-cell")}>Phạm vi</th>
                  <th className={cn(th, "hidden md:table-cell")}>Trang Wiki</th>
                  <th className={cn(th, "hidden sm:table-cell")}>Trạng thái</th>
                  <th className={cn(th, "hidden lg:table-cell whitespace-nowrap")}>{sortHeader("Ngày tải lên", "created")}</th>
                  <th className={cn(thPlain, "w-11 px-2")} />
                </tr>
              </thead>
              <tbody>
                {sources.map((s) => {
                  const isSel = selected.has(s.id);
                  const isOpen = expanded === s.id;
                  const isInfoOpen = expandedInfo === s.id;
                  const infoId = `source-info-${s.id}`;
                  const meta = s.doc_meta;
                  const subParts = [
                    meta?.doc_number && !s.title.includes(meta.doc_number) ? meta.doc_number : null,
                    meta?.issuing_authority && !s.title.toLocaleLowerCase("vi").includes(meta.issuing_authority.toLocaleLowerCase("vi")) ? meta.issuing_authority : null,
                  ].filter(Boolean);
                  const deptNames =
                    s.department_names && s.department_names.length > 0
                      ? s.department_names
                      : (s.department_ids ?? []).map((id) => deptName(id)).filter((n): n is string => !!n);
                  const wikiCount = s.wiki_page_count ?? 0;
                  const showWiki = s.status === "ready" || wikiCount > 0;
                  const validity = meta?.validity ? VALIDITY_INFO[meta.validity] : undefined;
                  const isRetrying = retrying.has(s.id);
                  const groupA = hasBranchRetry(s);
                  const failed = isFailed(s);
                  return (
                    <Fragment key={s.id}>
                      <tr
                        data-state={isSel ? "selected" : undefined}
                        className={cn(
                          "group last:border-b-0",
                          !isInfoOpen && "border-b",
                          isOpen ? "bg-accent/40" : isSel ? "bg-primary/5" : "hover:bg-secondary/30"
                        )}
                      >
                        <td className={cn(td, "w-[25px] pr-0 pl-3")}>
                          <input
                            type="checkbox"
                            aria-label={`Chọn ${s.title}`}
                            className="size-[13px] cursor-pointer accent-primary"
                            checked={isSel}
                            onChange={(e) => toggleRow(s.id, e.target.checked)}
                          />
                        </td>
                        <td className={cn(td, "w-full max-w-[520px] sm:w-auto sm:min-w-[260px]")}>
                          <div className="flex min-w-0 items-center gap-2.5">
                            <span className="flex size-7 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
                              <Icon name={sourceIcon(s)} size={16} />
                            </span>
                            <div className="min-w-0">
                              <Link
                                href={`/wiki/source/${s.id}`}
                                title={s.title}
                                className="line-clamp-2 break-words text-sm leading-5 font-medium hover:text-primary hover:underline"
                              >
                                {s.title}
                              </Link>
                              {subParts.length > 0 && (
                                <p className="mt-1 truncate text-xs leading-4 text-muted-foreground">{subParts.join(" · ")}</p>
                              )}
                              <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                                {s.knowledge_type_name && <TypePill name={s.knowledge_type_name} color={s.knowledge_type_color} />}
                                {s.preserve_verbatim && <span title="Giữ nguyên văn, tách theo Điều, không biên soạn lại" className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">Nguyên văn</span>}
                                <button
                                  type="button"
                                  id={`${infoId}-toggle`}
                                  aria-expanded={isInfoOpen}
                                  aria-controls={infoId}
                                  onClick={() => setExpandedInfo(isInfoOpen ? null : s.id)}
                                  className={cn(
                                    "inline-flex cursor-pointer items-center gap-1 rounded-sm py-0.5 text-xs transition-colors hover:text-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
                                    isInfoOpen ? "text-primary" : "text-muted-foreground"
                                  )}
                                >
                                  <span aria-hidden="true" className="inline-flex"><Icon name={isInfoOpen ? "expand_less" : "expand_more"} size={14} /></span>
                                  Thông tin bổ sung
                                </button>
                              </div>
                              <div className="mt-2 sm:hidden"><StatusDot source={s} /></div>
                            </div>
                          </div>
                        </td>
                        <td className={cn(td, "hidden xl:table-cell")}>
                          <ScopeBadge scopeType={s.scope_type ?? undefined} scopeId={s.scope_id} className="px-2.5 py-0.5 text-[11px]" />
                          {deptNames.length > 0 && <p className="mt-1 max-w-40 truncate text-xs text-muted-foreground" title={deptNames.join(", ")}>{deptNames.join(", ")}</p>}
                        </td>
                        <td className={cn(td, "hidden md:table-cell whitespace-nowrap")}>
                          {showWiki && wikiCount > 0 ? (
                            <div className="flex items-center gap-1.5">
                                <button
                                  type="button"
                                  title="Xem các trang Wiki của tài liệu"
                                  aria-label={`Xem ${wikiCount} trang Wiki của ${s.title}`}
                                  onClick={() => setExpanded(isOpen ? null : s.id)}
                                  className={cn(
                                    "inline-flex items-center rounded-full px-1.5 py-0.5 text-[10px] font-semibold tabular-nums",
                                    isOpen ? "bg-primary text-primary-foreground" : "bg-primary/10 text-primary"
                                  )}
                                >
                                  {wikiCount} trang
                                  <Icon name={isOpen ? "expand_less" : "expand_more"} size={12} />
                                </button>
                            </div>
                          ) : (
                            <Dash />
                          )}
                        </td>
                        <td className={cn(td, "hidden sm:table-cell min-w-32")}>
                          <StatusDot source={s} showWikiCount={false} />
                        </td>
                        <td className={cn(td, "hidden lg:table-cell whitespace-nowrap text-muted-foreground tabular-nums")}>
                          {formatCreatedDate(s.created_at)}
                        </td>
                        <td className={cn(td, "w-11 text-right")}>
                          <DropdownMenu>
                            <DropdownMenuTrigger
                              aria-label="Thao tác"
                              className="inline-flex size-7 items-center justify-center rounded-md text-muted-foreground group-hover:text-foreground hover:bg-secondary"
                            >
                              <Icon name="more_horiz" size={18} />
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end" className="min-w-48">
                              <DropdownMenuItem onClick={() => router.push(`/wiki/source/${s.id}`)}>
                                <Icon name="visibility" />
                                Xem tài liệu
                              </DropdownMenuItem>
                              {s.status === "ready" && (
                                <DropdownMenuItem onClick={() => router.push(`/wiki/law/${lawKey(s)}`)}>
                                  <Icon name="auto_stories" />
                                  Mở trong Kho tri thức
                                </DropdownMenuItem>
                              )}
                              {s.status === "ready" && s.source_type !== "url" && (
                                <DropdownMenuItem onClick={() => void downloadRow(s)}>
                                  <Icon name="download" />
                                  Tải tệp gốc
                                </DropdownMenuItem>
                              )}
                              <DropdownMenuSeparator />
                              <DropdownMenuItem onClick={() => setEditing(s)}>
                                <Icon name="edit" />
                                Chỉnh sửa thông tin
                              </DropdownMenuItem>
                              {s.status === "plan_ready" && (
                                <DropdownMenuItem onClick={() => setPlanFor(s)}>
                                  <Icon name="fact_check" className="text-blue-600 dark:text-blue-400" />
                                  Duyệt kế hoạch biên soạn
                                </DropdownMenuItem>
                              )}
                              {s.status === "awaiting_approval" && (
                                <DropdownMenuItem onClick={() => setExtractionFor(s)}>
                                  <Icon name="scale" className="text-orange-600 dark:text-orange-400" />
                                  Duyệt dung lượng trích xuất
                                </DropdownMenuItem>
                              )}
                              {failed && (
                                <DropdownMenuItem disabled={isRetrying} onClick={() => void retryRow(s, null)}>
                                  <Icon name="refresh" className={cn(isRetrying && "animate-spin")} />
                                  {isRetrying ? "Đang chạy lại..." : "Chạy lại phần lỗi"}
                                </DropdownMenuItem>
                              )}
                              {groupA && (
                                <DropdownMenuItem disabled={isRetrying} onClick={() => void retryRow(s, "chunk")}>
                                  <Icon name="segment" />
                                  {t("knowledge.retryChunk")}
                                </DropdownMenuItem>
                              )}
                              {groupA &&
                                !s.preserve_verbatim &&
                                ["error", "partial", "plan_ready"].includes(s.status) && (
                                  <DropdownMenuItem disabled={isRetrying} onClick={() => void retryRow(s, "wiki")}>
                                    <Icon name="auto_stories" />
                                    {t("knowledge.retryWiki")}
                                  </DropdownMenuItem>
                                )}
                              {groupA && (
                                <DropdownMenuItem disabled={isRetrying} onClick={() => void retryRow(s, "all")}>
                                  <Icon name="restart_alt" />
                                  {t("knowledge.retryAll")}
                                </DropdownMenuItem>
                              )}
                              <DropdownMenuSeparator />
                              <DropdownMenuItem variant="destructive" onClick={() => void deleteRow(s)}>
                                <Icon name="delete" />
                                Xóa
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </td>
                      </tr>
                      <tr className="border-b last:border-b-0" hidden={!isInfoOpen}>
                        <td colSpan={COLUMN_COUNT} className="p-0">
                          <div id={infoId} role="region" aria-labelledby={`${infoId}-toggle`} className="bg-muted/25 px-4 py-3 sm:pr-6 sm:pl-[75px]">
                            <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-xs leading-5 lg:grid-cols-4">
                              <div className="min-w-0">
                                <dt className="text-muted-foreground">Số trang tệp</dt>
                                <dd className="mt-0.5 font-medium tabular-nums">{s.page_count ?? "Chưa có"}</dd>
                              </div>
                              <div className="min-w-0">
                                <dt className="text-muted-foreground">Người đóng góp</dt>
                                <dd className="mt-0.5 break-words font-medium">{s.contributed_by_name || "Chưa có"}</dd>
                              </div>
                              <div className="min-w-0">
                                <dt className="text-muted-foreground">Ngày ban hành</dt>
                                <dd className="mt-0.5 font-medium tabular-nums">{meta?.issued_date ? formatViDate(meta.issued_date) : "Chưa có"}</dd>
                              </div>
                              <div className="min-w-0">
                                <dt className="text-muted-foreground">Hiệu lực</dt>
                                <dd className="mt-0.5 flex flex-wrap items-center gap-x-1.5 font-medium">
                                  <span>{validity?.label || "Chưa xác định"}</span>
                                  {meta?.effective_date && <span className="text-muted-foreground tabular-nums">· {formatViDate(meta.effective_date)}</span>}
                                </dd>
                              </div>
                              <div className="col-span-2 min-w-0 xl:hidden">
                                <dt className="text-muted-foreground">Phạm vi</dt>
                                <dd className="mt-0.5 flex flex-wrap items-center gap-2 break-words">
                                  <ScopeBadge scopeType={s.scope_type ?? undefined} scopeId={s.scope_id} />
                                  {deptNames.length > 0 && <span>{deptNames.join(", ")}</span>}
                                </dd>
                              </div>
                              {showWiki && wikiCount > 0 && <div className="col-span-2 md:hidden"><button type="button" aria-expanded={isOpen} onClick={() => setExpanded(isOpen ? null : s.id)} className="inline-flex cursor-pointer items-center gap-1 rounded-sm text-primary hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"><Icon name="auto_stories" size={14} />{isOpen ? "Thu gọn" : "Xem"} {wikiCount} trang Wiki<Icon name={isOpen ? "expand_less" : "expand_more"} size={14} /></button></div>}
                            </dl>
                          </div>
                        </td>
                      </tr>
                      {isOpen && (
                        <tr className="bg-muted/15">
                          <td colSpan={COLUMN_COUNT} className="p-0">
                            <SourceArticlesDrawer source={s} onClose={() => setExpanded(null)} />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Pagination */}
      {total > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
          <div className="flex items-center gap-2">
            <span className="tabular-nums">
              {from}–{to} / {total}
            </span>
            <select
              aria-label="Số dòng mỗi trang"
              value={query.pageSize}
              onChange={(e) => onQueryChange({ pageSize: Number(e.target.value), page: 1 })}
              className="h-7 cursor-pointer rounded-md border border-border bg-background px-1.5 text-xs outline-none focus:ring-2 focus:ring-primary/30"
            >
              {PAGE_SIZES.map((n) => (
                <option key={n} value={n}>
                  {n} / trang
                </option>
              ))}
            </select>
          </div>
          {totalPages > 1 && (
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="icon-sm"
                aria-label="Trang trước"
                disabled={query.page <= 1}
                onClick={() => onQueryChange({ page: query.page - 1 })}
              >
                <Icon name="chevron_left" size={18} />
              </Button>
              <span className="tabular-nums">
                Trang {query.page} / {totalPages}
              </span>
              <Button
                variant="outline"
                size="icon-sm"
                aria-label="Trang sau"
                disabled={query.page >= totalPages}
                onClick={() => onQueryChange({ page: query.page + 1 })}
              >
                <Icon name="chevron_right" size={18} />
              </Button>
            </div>
          )}
        </div>
      )}

      {editing && (
        <EditSourceDialog
          source={editing}
          types={types}
          departments={departments}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            onRefresh();
          }}
        />
      )}
      {planFor && (
        <PlanReviewDialog
          source={planFor}
          onClose={() => setPlanFor(null)}
          onDone={() => {
            setPlanFor(null);
            onRefresh();
          }}
        />
      )}
      {extractionFor && (
        <ExtractionReviewDialog
          source={extractionFor}
          onClose={() => setExtractionFor(null)}
          onDone={() => {
            setExtractionFor(null);
            onRefresh();
          }}
        />
      )}
    </div>
  );
}
