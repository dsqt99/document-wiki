"use client";

import React from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { EmptyState } from "@/components/shared/empty-state";
import { ScopeBadge } from "@/components/shared/scope-badge";

import { KnowledgeType, Department, Source } from "./types";
import { fileIcons, getFileExt } from "./utils";
import { StatusDot } from "./status-dot";
import { EditSourceDialog } from "./edit-source-dialog";
import { PlanReviewDialog } from "./plan-review-dialog";
import { ExtractionReviewDialog } from "./extraction-review-dialog";
import { SourceArticlesDrawer } from "./source-articles-drawer";
import { useI18n } from "@/lib/i18n";
import { VALIDITY_INFO, formatViDate } from "@/lib/legal-doc";
import { cn } from "@/lib/utils";

/** Server-side list query — every filter, sort and page lives here so results stay consistent across pages. */
export type SourceQuery = {
  search: string;
  typeId: string;
  deptId: string;
  status: StatusGroup;
  sort: string; // <field>_<asc|desc>
  page: number;
  pageSize: number;
};

export type StatusGroup = "" | "ready" | "running" | "review" | "failed";

export const STATUS_GROUPS: { value: StatusGroup; label: string; statuses: string }[] = [
  { value: "", label: "Tất cả trạng thái", statuses: "" },
  { value: "ready", label: "Sẵn sàng", statuses: "ready" },
  { value: "running", label: "Đang xử lý", statuses: "pending,processing" },
  { value: "review", label: "Chờ duyệt", statuses: "plan_ready,awaiting_approval" },
  { value: "failed", label: "Lỗi / một phần", statuses: "error,partial" },
];

export const DEFAULT_QUERY: SourceQuery = {
  search: "",
  typeId: "",
  deptId: "",
  status: "",
  sort: "created_desc",
  page: 1,
  pageSize: 20,
};

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

const selectCls =
  "h-8 rounded-lg border border-border bg-background pl-2.5 pr-7 text-xs text-foreground cursor-pointer appearance-none focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary/50";
const selectStyle: React.CSSProperties = {
  backgroundImage: `url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3e%3cpath stroke='%236b7280' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='M6 8l4 4 4-4'/%3e%3c/svg%3e")`,
  backgroundPosition: "right 6px center",
  backgroundRepeat: "no-repeat",
  backgroundSize: "16px",
};

function SortHead({
  field,
  sort,
  onSort,
  children,
  className,
}: {
  field: string;
  sort: string;
  onSort: (s: string) => void;
  children: React.ReactNode;
  className?: string;
}) {
  const [f, dir] = sort.split(/_(?=asc$|desc$)/);
  const active = f === field;
  // First click on a date column sorts newest first; titles start A→Z.
  const firstDir = field === "title" ? "asc" : "desc";
  const next = active ? (dir === "asc" ? "desc" : "asc") : firstDir;
  return (
    <TableHead className={cn(headCls, className)}>
      <button
        type="button"
        onClick={() => onSort(`${field}_${next}`)}
        className={cn(
          "inline-flex items-center gap-0.5 text-left uppercase tracking-wider cursor-pointer hover:text-foreground",
          active && "text-foreground",
        )}
      >
        {children}
        <span className={cn("material-symbols-outlined", !active && "opacity-30")} style={{ fontSize: 14 }}>
          {active ? (dir === "asc" ? "arrow_upward" : "arrow_downward") : "unfold_more"}
        </span>
      </button>
    </TableHead>
  );
}

const headCls = "h-10 py-1.5 text-[10.5px] leading-tight uppercase tracking-wider font-semibold text-muted-foreground whitespace-normal align-middle";

function initials(name?: string) {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/);
  return (parts[parts.length - 1]?.[0] || "?").toUpperCase();
}

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
  const [actionError, setActionError] = React.useState<string | null>(null);
  const [editSource, setEditSource] = React.useState<Source | null>(null);
  const [reviewPlanSource, setReviewPlanSource] = React.useState<Source | null>(null);
  const [reviewExtractionSource, setReviewExtractionSource] = React.useState<Source | null>(null);
  const [retryingIds, setRetryingIds] = React.useState<Set<string>>(new Set());
  const [expanded, setExpanded] = React.useState<Set<string>>(new Set());
  const [selected, setSelected] = React.useState<Set<string>>(new Set());
  const [bulkBusy, setBulkBusy] = React.useState(false);
  const [searchInput, setSearchInput] = React.useState(query.search);

  // Debounce typing into the server-side search.
  const lastSearch = React.useRef(query.search);
  React.useEffect(() => {
    if (searchInput === lastSearch.current) return;
    const h = setTimeout(() => {
      lastSearch.current = searchInput;
      onQueryChange({ search: searchInput.trim(), page: 1 });
    }, 350);
    return () => clearTimeout(h);
  }, [searchInput, onQueryChange]);

  // Selection only refers to rows on the current page.
  const visibleIds = sources.map((s) => s.id);
  const selectedVisible = visibleIds.filter((id) => selected.has(id));
  const allSelected = visibleIds.length > 0 && selectedVisible.length === visibleIds.length;
  const toggleAll = () => setSelected(allSelected ? new Set() : new Set(visibleIds));
  const toggleOne = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const toggleExpand = (id: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const handleDelete = async (id: string) => {
    if (!confirm(t("knowledge.deleteConfirm", "Xóa tài liệu này? Thao tác không thể hoàn tác."))) return;
    setActionError(null);
    try {
      await api(`/api/sources/${id}`, { method: "DELETE" });
      setSelected((prev) => { const s = new Set(prev); s.delete(id); return s; });
      onRefresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Không xóa được tài liệu");
    }
  };

  // branch: undefined = server picks the failed branch(es); chunk / wiki / all = explicit.
  const handleRetry = async (id: string, branch?: "chunk" | "wiki" | "all") => {
    setActionError(null);
    setRetryingIds((prev) => new Set(prev).add(id));
    try {
      await api(`/api/sources/${id}/retry${branch ? `?branch=${branch}` : ""}`, { method: "POST" });
      onRefresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Không chạy lại được");
    } finally {
      setRetryingIds((prev) => { const s = new Set(prev); s.delete(id); return s; });
    }
  };

  const selectedSources = sources.filter((s) => selected.has(s.id));
  const retryable = selectedSources.filter((s) => s.status === "error" || s.status === "partial");

  const bulk = async (kind: "delete" | "retry") => {
    const targets = kind === "delete" ? selectedSources : retryable;
    if (!targets.length) return;
    if (kind === "delete" && !confirm(`Xóa ${targets.length} tài liệu đã chọn? Thao tác không thể hoàn tác.`)) return;
    setBulkBusy(true);
    setActionError(null);
    const failures: string[] = [];
    for (const s of targets) {
      try {
        if (kind === "delete") await api(`/api/sources/${s.id}`, { method: "DELETE" });
        else await api(`/api/sources/${s.id}/retry`, { method: "POST" });
      } catch (err) {
        failures.push(`${s.title}: ${err instanceof Error ? err.message : "lỗi"}`);
      }
    }
    setBulkBusy(false);
    setSelected(new Set());
    if (failures.length) setActionError(`${failures.length}/${targets.length} thao tác thất bại — ${failures[0]}`);
    onRefresh();
  };

  const hasFilters = Boolean(query.search || query.typeId || query.deptId || query.status);
  const clearFilters = () => {
    setSearchInput("");
    lastSearch.current = "";
    onQueryChange({ search: "", typeId: "", deptId: "", status: "", page: 1 });
  };

  const deptNames = (s: Source) => {
    if (s.department_names?.length) return s.department_names;
    const byId = new Map(departments.map((d) => [d.id, d.name]));
    return (s.department_ids || []).map((id) => byId.get(id)).filter(Boolean) as string[];
  };

  const from = total === 0 ? 0 : (query.page - 1) * query.pageSize + 1;
  const to = Math.min(query.page * query.pageSize, total);
  const COLS = 13;

  return (
    <div className="flex flex-col gap-3">
      {/* Filter row */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative w-full sm:w-64">
          <span className="material-symbols-outlined absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" style={{ fontSize: 16 }}>
            search
          </span>
          <input
            type="text"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Tìm kiếm tài liệu..."
            className="h-8 w-full rounded-lg border border-border bg-background pl-8 pr-7 text-xs placeholder:text-muted-foreground/70 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary/50"
          />
          {searchInput && (
            <button
              type="button"
              onClick={() => setSearchInput("")}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground cursor-pointer"
              title="Xóa"
            >
              <span className="material-symbols-outlined" style={{ fontSize: 14 }}>close</span>
            </button>
          )}
        </div>

        <select
          value={query.typeId}
          onChange={(e) => onQueryChange({ typeId: e.target.value, page: 1 })}
          className={selectCls}
          style={selectStyle}
        >
          <option value="">Tất cả danh mục</option>
          {types.map((ti) => (
            <option key={ti.id} value={ti.id}>{ti.name}</option>
          ))}
        </select>

        {departments.length > 0 && (
          <select
            value={query.deptId}
            onChange={(e) => onQueryChange({ deptId: e.target.value, page: 1 })}
            className={selectCls}
            style={selectStyle}
          >
            <option value="">Tất cả phòng ban</option>
            {departments.map((d) => (
              <option key={d.id} value={d.id}>{d.name}</option>
            ))}
          </select>
        )}

        <select
          value={query.status}
          onChange={(e) => onQueryChange({ status: e.target.value as StatusGroup, page: 1 })}
          className={selectCls}
          style={selectStyle}
        >
          {STATUS_GROUPS.map((g) => (
            <option key={g.value} value={g.value}>{g.label}</option>
          ))}
        </select>

        {hasFilters && (
          <button
            type="button"
            onClick={clearFilters}
            className="flex h-8 items-center gap-1 rounded-lg px-2 text-xs text-muted-foreground hover:bg-secondary hover:text-foreground cursor-pointer"
          >
            <span className="material-symbols-outlined" style={{ fontSize: 15 }}>filter_alt_off</span>
            Xóa lọc
          </button>
        )}

        <span className="ml-auto text-xs text-muted-foreground tabular-nums">
          {total} tài liệu
        </span>
      </div>

      {/* Bulk action bar */}
      {selectedVisible.length > 0 && (
        <div className="flex items-center gap-2 rounded-lg border border-primary/30 bg-primary/5 px-3 py-1.5 text-xs">
          <span className="font-medium text-foreground">Đã chọn {selectedVisible.length}</span>
          <button type="button" onClick={() => setSelected(new Set())} className="text-muted-foreground hover:text-foreground cursor-pointer">
            Bỏ chọn
          </button>
          <div className="ml-auto flex items-center gap-1.5">
            {retryable.length > 0 && (
              <Button variant="outline" size="sm" className="h-7 gap-1 text-xs" disabled={bulkBusy} onClick={() => bulk("retry")}>
                <span className="material-symbols-outlined" style={{ fontSize: 15 }}>refresh</span>
                Chạy lại ({retryable.length})
              </Button>
            )}
            <Button
              variant="outline"
              size="sm"
              className="h-7 gap-1 text-xs text-destructive hover:bg-destructive/10 hover:text-destructive"
              disabled={bulkBusy}
              onClick={() => bulk("delete")}
            >
              <span className={cn("material-symbols-outlined", bulkBusy && "animate-spin")} style={{ fontSize: 15 }}>
                {bulkBusy ? "progress_activity" : "delete"}
              </span>
              Xóa
            </Button>
          </div>
        </div>
      )}

      {actionError && (
        <div className="flex items-center gap-2 rounded-lg bg-destructive/10 px-3 py-2 text-xs text-destructive">
          <span className="material-symbols-outlined" style={{ fontSize: 16 }}>error</span>
          <span className="flex-1">{actionError}</span>
          <button type="button" onClick={() => setActionError(null)} className="cursor-pointer">
            <span className="material-symbols-outlined" style={{ fontSize: 16 }}>close</span>
          </button>
        </div>
      )}

      {/* Table */}
      <div className="overflow-hidden rounded-xl border border-border bg-card">
        {loading && sources.length === 0 ? (
          <div className="flex items-center justify-center py-16">
            <span className="material-symbols-outlined animate-spin text-3xl text-muted-foreground">progress_activity</span>
          </div>
        ) : sources.length === 0 ? (
          hasFilters ? (
            <EmptyState
              icon="search_off"
              title="Không có tài liệu phù hợp"
              description="Thử đổi từ khóa hoặc bỏ bớt bộ lọc."
              action={<Button variant="outline" size="sm" onClick={clearFilters}>Xóa bộ lọc</Button>}
            />
          ) : (
            <EmptyState
              icon="cloud_upload"
              title="Chưa có tài liệu nào"
              description="Tải lên văn bản đầu tiên để bắt đầu xây dựng kho tri thức."
              action={<Button size="sm" onClick={onUpload}>Tải lên tài liệu</Button>}
            />
          )
        ) : (
          <div className={cn("overflow-x-auto transition-opacity", loading && "opacity-60")}>
            <Table className="text-xs">
              <TableHeader>
                <TableRow className="bg-muted/30 hover:bg-muted/30">
                  <TableHead className="w-9 pl-3 pr-0">
                    <input
                      type="checkbox"
                      checked={allSelected}
                      ref={(el) => { if (el) el.indeterminate = selectedVisible.length > 0 && !allSelected; }}
                      onChange={toggleAll}
                      className="cursor-pointer accent-[var(--primary)]"
                      aria-label="Chọn tất cả"
                    />
                  </TableHead>
                  <SortHead field="title" sort={query.sort} onSort={(s) => onQueryChange({ sort: s, page: 1 })} className="min-w-[240px]">
                    Tài liệu
                  </SortHead>
                  <TableHead className={headCls}>Danh mục</TableHead>
                  <TableHead className={headCls}>Phạm vi hiển thị</TableHead>
                  <TableHead className={headCls}>Phòng ban phụ trách</TableHead>
                  <TableHead className={cn(headCls, "text-right")}>Số trang</TableHead>
                  <TableHead className={headCls}>Wiki</TableHead>
                  <TableHead className={headCls}>Người đóng góp</TableHead>
                  <TableHead className={headCls}>Trạng thái</TableHead>
                  <SortHead field="issued" sort={query.sort} onSort={(s) => onQueryChange({ sort: s, page: 1 })}>
                    Ngày ban hành
                  </SortHead>
                  <SortHead field="effective" sort={query.sort} onSort={(s) => onQueryChange({ sort: s, page: 1 })}>
                    Hiệu lực
                  </SortHead>
                  <SortHead field="created" sort={query.sort} onSort={(s) => onQueryChange({ sort: s, page: 1 })}>
                    Ngày tạo
                  </SortHead>
                  <TableHead className="w-10" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {sources.map((source) => {
                  const docMeta = source.doc_meta;
                  const validity = docMeta?.validity ? VALIDITY_INFO[docMeta.validity] : null;
                  const isExpanded = expanded.has(source.id);
                  const articles = source.wiki_page_count ?? 0;
                  const ext = getFileExt(source);
                  const depts = deptNames(source);
                  const isSelected = selected.has(source.id);
                  const wikiHref = `/wiki/law/${encodeURIComponent(docMeta?.doc_slug || source.id)}`;

                  return (
                    <React.Fragment key={source.id}>
                      <TableRow
                        data-state={isSelected ? "selected" : undefined}
                        className={cn("group", isExpanded ? "bg-accent/40" : isSelected ? "bg-primary/5" : "hover:bg-secondary/30")}
                      >
                        <TableCell className="pl-3 pr-0 py-2">
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={() => toggleOne(source.id)}
                            className="cursor-pointer accent-[var(--primary)]"
                            aria-label={`Chọn ${source.title}`}
                          />
                        </TableCell>

                        {/* Document */}
                        <TableCell className="py-2 max-w-[300px]">
                          <div className="flex items-center gap-2.5 min-w-0">
                            <span className="flex size-7 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
                              <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
                                {fileIcons[ext] || (source.source_type === "url" ? "link" : "description")}
                              </span>
                            </span>
                            <div className="min-w-0">
                              <Link
                                href={`/wiki/source/${source.id}`}
                                className="block truncate text-[13px] font-medium text-foreground hover:text-primary"
                                title={source.title}
                              >
                                {source.title}
                              </Link>
                              {(docMeta?.doc_number || docMeta?.issuing_authority) && (
                                <p className="truncate text-[11px] text-muted-foreground">
                                  {[docMeta?.doc_number, docMeta?.issuing_authority].filter(Boolean).join(" · ")}
                                </p>
                              )}
                            </div>
                          </div>
                        </TableCell>

                        {/* Category */}
                        <TableCell className="py-2">
                          <div className="flex items-center gap-1 whitespace-nowrap">
                            {source.knowledge_type_name ? (
                              <span
                                className="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium"
                                style={{
                                  borderColor: `${source.knowledge_type_color}55`,
                                  color: source.knowledge_type_color,
                                  backgroundColor: `${source.knowledge_type_color}12`,
                                }}
                              >
                                {source.knowledge_type_name}
                              </span>
                            ) : (
                              <span className="text-muted-foreground/60">—</span>
                            )}
                            {source.preserve_verbatim && (
                              <span
                                className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground"
                                title="Giữ nguyên văn — tách theo Điều, không biên soạn lại"
                              >
                                Nguyên văn
                              </span>
                            )}
                          </div>
                        </TableCell>

                        {/* Scope */}
                        <TableCell className="py-2">
                          <ScopeBadge scopeType={source.scope_type} scopeId={source.scope_id} />
                        </TableCell>

                        {/* Departments */}
                        <TableCell className="py-2 max-w-[140px]">
                          {depts.length ? (
                            <span className="block truncate text-foreground/80" title={depts.join(", ")}>
                              {depts[0]}
                              {depts.length > 1 && <span className="text-muted-foreground"> +{depts.length - 1}</span>}
                            </span>
                          ) : (
                            <span className="text-muted-foreground/60">—</span>
                          )}
                        </TableCell>

                        {/* Pages */}
                        <TableCell className="py-2 text-right tabular-nums text-muted-foreground">
                          {source.page_count || "—"}
                        </TableCell>

                        {/* Wiki */}
                        <TableCell className="py-2">
                          {source.status === "ready" || articles > 0 ? (
                            <div className="flex items-center gap-1.5 whitespace-nowrap">
                              <Link href={wikiHref} className="inline-flex items-center gap-0.5 font-medium text-primary hover:underline">
                                Xem wiki
                                <span className="material-symbols-outlined" style={{ fontSize: 13 }}>arrow_outward</span>
                              </Link>
                              {articles > 0 && (
                                <button
                                  type="button"
                                  onClick={() => toggleExpand(source.id)}
                                  className={cn(
                                    "inline-flex items-center rounded-full px-1.5 py-0.5 text-[10px] font-semibold tabular-nums cursor-pointer",
                                    isExpanded ? "bg-primary text-primary-foreground" : "bg-primary/10 text-primary hover:bg-primary/20",
                                  )}
                                  title="Xem nhanh các Điều"
                                >
                                  {articles}
                                  <span className="material-symbols-outlined" style={{ fontSize: 12 }}>
                                    {isExpanded ? "expand_less" : "expand_more"}
                                  </span>
                                </button>
                              )}
                            </div>
                          ) : (
                            <span className="text-muted-foreground/60">—</span>
                          )}
                        </TableCell>

                        {/* Contributor */}
                        <TableCell className="py-2 max-w-[130px]">
                          {source.contributed_by_name ? (
                            <span className="flex items-center gap-1.5 min-w-0">
                              <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-secondary text-[10px] font-semibold text-secondary-foreground">
                                {initials(source.contributed_by_name)}
                              </span>
                              <span className="truncate" title={source.contributed_by_name}>{source.contributed_by_name}</span>
                            </span>
                          ) : (
                            <span className="text-muted-foreground/60">—</span>
                          )}
                        </TableCell>

                        {/* Status */}
                        <TableCell className="py-2">
                          <StatusDot source={source} />
                        </TableCell>

                        {/* Issued */}
                        <TableCell className="py-2 whitespace-nowrap tabular-nums text-foreground/80">
                          {docMeta?.issued_date ? formatViDate(docMeta.issued_date) : <span className="text-muted-foreground/60">—</span>}
                        </TableCell>

                        {/* Validity */}
                        <TableCell className="py-2">
                          {validity ? (
                            <span
                              className={cn("whitespace-nowrap rounded-full border px-2 py-0.5 text-[10px] font-semibold", validity.badge)}
                              title={docMeta?.effective_date ? `Hiệu lực từ ${formatViDate(docMeta.effective_date)}` : undefined}
                            >
                              {validity.label}
                            </span>
                          ) : (
                            <span className="text-muted-foreground/60">—</span>
                          )}
                        </TableCell>

                        {/* Created */}
                        <TableCell className="py-2 whitespace-nowrap tabular-nums text-muted-foreground">
                          {new Date(source.created_at).toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric" })}
                        </TableCell>

                        {/* Actions */}
                        <TableCell className="py-2 pr-2 text-right">
                          <DropdownMenu>
                            <DropdownMenuTrigger className="inline-flex size-7 items-center justify-center rounded-md text-muted-foreground hover:bg-accent group-hover:text-foreground">
                              <span className="material-symbols-outlined" style={{ fontSize: 18 }}>more_horiz</span>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end" className="min-w-48">
                              <DropdownMenuItem onClick={() => router.push(`/wiki/source/${source.id}`)}>
                                <span className="material-symbols-outlined mr-2" style={{ fontSize: 16 }}>visibility</span>
                                Xem tài liệu
                              </DropdownMenuItem>
                              {source.status === "ready" && (
                                <DropdownMenuItem onClick={() => router.push(wikiHref)}>
                                  <span className="material-symbols-outlined mr-2" style={{ fontSize: 16 }}>auto_stories</span>
                                  Mở trong Trang wiki
                                </DropdownMenuItem>
                              )}
                              {source.status === "ready" && source.source_type !== "url" && (
                                <DropdownMenuItem
                                  onClick={async () => {
                                    try {
                                      const detail = await api<{ download_url?: string }>(`/api/sources/${source.id}`);
                                      if (detail.download_url) window.open(detail.download_url, "_blank");
                                    } catch (err) {
                                      setActionError(err instanceof Error ? err.message : "Không tải được tệp");
                                    }
                                  }}
                                >
                                  <span className="material-symbols-outlined mr-2" style={{ fontSize: 16 }}>download</span>
                                  Tải tệp gốc
                                </DropdownMenuItem>
                              )}
                              <DropdownMenuSeparator />
                              <DropdownMenuItem onClick={() => setEditSource(source)}>
                                <span className="material-symbols-outlined mr-2" style={{ fontSize: 16 }}>edit</span>
                                Chỉnh sửa thông tin
                              </DropdownMenuItem>
                              {source.status === "plan_ready" && (
                                <DropdownMenuItem onClick={() => setReviewPlanSource(source)}>
                                  <span className="material-symbols-outlined mr-2 text-blue-500" style={{ fontSize: 16 }}>fact_check</span>
                                  Duyệt kế hoạch biên soạn
                                </DropdownMenuItem>
                              )}
                              {source.status === "awaiting_approval" && (
                                <DropdownMenuItem onClick={() => setReviewExtractionSource(source)}>
                                  <span className="material-symbols-outlined mr-2 text-orange-500" style={{ fontSize: 16 }}>scale</span>
                                  Duyệt dung lượng trích xuất
                                </DropdownMenuItem>
                              )}
                              {(source.status === "error" || source.status === "partial") && (
                                <DropdownMenuItem onClick={() => handleRetry(source.id)} disabled={retryingIds.has(source.id)}>
                                  <span className={cn("material-symbols-outlined mr-2", retryingIds.has(source.id) && "animate-spin")} style={{ fontSize: 16 }}>
                                    refresh
                                  </span>
                                  {retryingIds.has(source.id) ? "Đang chạy lại..." : "Chạy lại phần lỗi"}
                                </DropdownMenuItem>
                              )}
                              {/* Per-branch retry: only once text was extracted (a branch left 'pending'). */}
                              {["error", "partial", "plan_ready"].includes(source.status) &&
                                ((source.chunk_status && source.chunk_status !== "pending") ||
                                  (source.wiki_status && source.wiki_status !== "pending")) && (
                                  <>
                                    <DropdownMenuItem onClick={() => handleRetry(source.id, "chunk")} disabled={retryingIds.has(source.id)}>
                                      <span className="material-symbols-outlined mr-2" style={{ fontSize: 16 }}>segment</span>
                                      {t("knowledge.retryChunk", "Chạy lại tách đoạn")}
                                    </DropdownMenuItem>
                                    {!source.preserve_verbatim && (
                                      <DropdownMenuItem onClick={() => handleRetry(source.id, "wiki")} disabled={retryingIds.has(source.id)}>
                                        <span className="material-symbols-outlined mr-2" style={{ fontSize: 16 }}>auto_stories</span>
                                        {t("knowledge.retryWiki", "Biên soạn lại wiki")}
                                      </DropdownMenuItem>
                                    )}
                                    <DropdownMenuItem onClick={() => handleRetry(source.id, "all")} disabled={retryingIds.has(source.id)}>
                                      <span className="material-symbols-outlined mr-2" style={{ fontSize: 16 }}>restart_alt</span>
                                      {t("knowledge.retryAll", "Xử lý lại từ đầu")}
                                    </DropdownMenuItem>
                                  </>
                                )}
                              <DropdownMenuSeparator />
                              <DropdownMenuItem onClick={() => handleDelete(source.id)} className="text-destructive">
                                <span className="material-symbols-outlined mr-2" style={{ fontSize: 16 }}>delete</span>
                                Xóa
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </TableCell>
                      </TableRow>

                      {isExpanded && (
                        <TableRow className="bg-muted/15 hover:bg-muted/15">
                          <TableCell colSpan={COLS} className="p-0">
                            <SourceArticlesDrawer source={source} onClose={() => toggleExpand(source.id)} />
                          </TableCell>
                        </TableRow>
                      )}
                    </React.Fragment>
                  );
                })}
              </TableBody>
            </Table>
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
              value={query.pageSize}
              onChange={(e) => onQueryChange({ pageSize: Number(e.target.value), page: 1 })}
              className={cn(selectCls, "h-7")}
              style={selectStyle}
              aria-label="Số dòng mỗi trang"
            >
              {[10, 20, 50, 100].map((n) => (
                <option key={n} value={n}>{n} / trang</option>
              ))}
            </select>
          </div>
          {totalPages > 1 && (
            <div className="flex items-center gap-1">
              <Button variant="outline" size="sm" className="h-7 px-2" disabled={query.page <= 1} onClick={() => onQueryChange({ page: query.page - 1 })}>
                <span className="material-symbols-outlined" style={{ fontSize: 16 }}>chevron_left</span>
              </Button>
              <span className="px-2 tabular-nums">
                Trang {query.page} / {totalPages}
              </span>
              <Button variant="outline" size="sm" className="h-7 px-2" disabled={query.page >= totalPages} onClick={() => onQueryChange({ page: query.page + 1 })}>
                <span className="material-symbols-outlined" style={{ fontSize: 16 }}>chevron_right</span>
              </Button>
            </div>
          )}
        </div>
      )}

      {editSource && (
        <EditSourceDialog
          source={editSource}
          types={types}
          departments={departments}
          onClose={() => setEditSource(null)}
          onSaved={() => { setEditSource(null); onRefresh(); }}
        />
      )}
      {reviewPlanSource && (
        <PlanReviewDialog
          source={reviewPlanSource}
          onClose={() => setReviewPlanSource(null)}
          onDone={() => { setReviewPlanSource(null); onRefresh(); }}
        />
      )}
      {reviewExtractionSource && (
        <ExtractionReviewDialog
          source={reviewExtractionSource}
          onClose={() => setReviewExtractionSource(null)}
          onDone={() => { setReviewExtractionSource(null); onRefresh(); }}
        />
      )}
    </div>
  );
}
