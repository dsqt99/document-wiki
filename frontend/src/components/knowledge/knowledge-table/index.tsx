"use client";

import React from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
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
import { useI18n } from "@/lib/i18n";

type Props = {
  sources: Source[];
  types: KnowledgeType[];
  departments: Department[];
  loading: boolean;
  onRefresh: () => void;
  page: number;
  totalPages: number;
  total: number;
  onPageChange: (page: number) => void;
  search: string;
  onSearch: (q: string) => void;
  selectedType: string | null;
  onSelectType: (slug: string | null) => void;
  selectedDepartment: string | null;
  onSelectDepartment: (id: string | null) => void;
};

export function KnowledgeTable({
  sources,
  types,
  departments,
  loading,
  onRefresh,
  page,
  totalPages,
  total,
  onPageChange,
  search,
  onSearch,
  selectedType,
  onSelectType,
  selectedDepartment,
  onSelectDepartment,
}: Props) {
  const { t } = useI18n();
  const [actionError, setActionError] = React.useState<string | null>(null);
  const [editSource, setEditSource] = React.useState<Source | null>(null);
  const [reviewPlanSource, setReviewPlanSource] = React.useState<Source | null>(null);
  const [reviewExtractionSource, setReviewExtractionSource] = React.useState<Source | null>(null);
  const [retryingIds, setRetryingIds] = React.useState<Set<string>>(new Set());
  const [searchInput, setSearchInput] = React.useState(search);
  const [statusFilter, setStatusFilter] = React.useState<string | null>(null);
  const router = useRouter();

  const handleDelete = async (id: string) => {
    if (!confirm(t("knowledge.deleteConfirm", "Delete this document? This cannot be undone."))) return;
    setActionError(null);
    try {
      await api(`/api/sources/${id}`, { method: "DELETE" });
      onRefresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to delete");
    }
  };

  const handleRetry = async (id: string) => {
    setActionError(null);
    setRetryingIds((prev) => new Set(prev).add(id));
    try {
      await api(`/api/sources/${id}/retry`, { method: "POST" });
      onRefresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to retry");
    } finally {
      setRetryingIds((prev) => { const s = new Set(prev); s.delete(id); return s; });
    }
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSearch(searchInput);
  };

  const filteredSources = statusFilter
    ? sources.filter((s) => s.status === statusFilter)
    : sources;

  const hasActiveFilters = selectedType || selectedDepartment || statusFilter;
  const clearAllFilters = () => {
    onSelectType(null);
    onSelectDepartment(null);
    setStatusFilter(null);
    if (searchInput) { setSearchInput(""); onSearch(""); }
  };

  const statuses = React.useMemo(() => {
    const set = new Set(sources.map((s) => s.status));
    return Array.from(set).sort();
  }, [sources]);

  return (
    <div className="flex flex-col gap-2">
      {actionError && (
        <div className="text-sm text-destructive bg-destructive/10 px-4 py-2 rounded-lg flex items-center gap-2 mb-2">
          <span className="material-symbols-outlined text-base">error</span>
          {actionError}
        </div>
      )}

      {/* Inline Filter Bar */}
      <div className="flex flex-wrap items-center gap-2 mb-1">
        {/* Search */}
        <form onSubmit={handleSearchSubmit} className="flex-1 min-w-[200px] max-w-[300px]">
          <div className="relative">
            <span className="material-symbols-outlined text-sm text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2">
              search
            </span>
            <input
              type="text"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder={t("knowledge.searchPlaceholder", "Search documents...")}
              className="h-8 w-full pl-9 pr-3 text-xs rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary/50 placeholder:text-muted-foreground/60"
            />
            {searchInput && (
              <button
                type="button"
                onClick={() => { setSearchInput(""); onSearch(""); }}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground cursor-pointer"
              >
                <span className="material-symbols-outlined text-sm">close</span>
              </button>
            )}
          </div>
        </form>

        {/* Category Filter */}
        <select
          value={selectedType ?? ""}
          onChange={(e) => onSelectType(e.target.value || null)}
          className="h-8 px-2.5 text-xs rounded-lg border border-border bg-background text-foreground cursor-pointer focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary/50 min-w-[120px] appearance-none"
          style={{ backgroundImage: `url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3e%3cpath stroke='%236b7280' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='M6 8l4 4 4-4'/%3e%3c/svg%3e")`, backgroundPosition: 'right 6px center', backgroundRepeat: 'no-repeat', backgroundSize: '16px', paddingRight: '24px' }}
        >
          <option value="">{t("knowledge.allCategories", "All Categories")}</option>
          {types.map((tItem) => (
            <option key={tItem.slug} value={tItem.slug}>{tItem.name}</option>
          ))}
        </select>

        {/* Department Filter */}
        {departments.length > 0 && (
          <select
            value={selectedDepartment ?? ""}
            onChange={(e) => onSelectDepartment(e.target.value || null)}
            className="h-8 px-2.5 text-xs rounded-lg border border-border bg-background text-foreground cursor-pointer focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary/50 min-w-[130px] appearance-none"
            style={{ backgroundImage: `url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3e%3cpath stroke='%236b7280' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='M6 8l4 4 4-4'/%3e%3c/svg%3e")`, backgroundPosition: 'right 6px center', backgroundRepeat: 'no-repeat', backgroundSize: '16px', paddingRight: '24px' }}
          >
            <option value="">{t("knowledge.allDepartments", "All Departments")}</option>
            {departments.map((d) => (
              <option key={d.id} value={d.id}>{d.name}</option>
            ))}
          </select>
        )}

        {/* Status Filter */}
        <select
          value={statusFilter ?? ""}
          onChange={(e) => setStatusFilter(e.target.value || null)}
          className="h-8 px-2.5 text-xs rounded-lg border border-border bg-background text-foreground cursor-pointer focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary/50 min-w-[110px] appearance-none capitalize"
          style={{ backgroundImage: `url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3e%3cpath stroke='%236b7280' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='M6 8l4 4 4-4'/%3e%3c/svg%3e")`, backgroundPosition: 'right 6px center', backgroundRepeat: 'no-repeat', backgroundSize: '16px', paddingRight: '24px' }}
        >
          <option value="">{t("knowledge.allStatuses", "All Statuses")}</option>
          {statuses.map((s) => (
            <option key={s} value={s} className="capitalize">
              {t(`knowledge.status.${s}`, s)}
            </option>
          ))}
        </select>

        {/* Clear All */}
        {hasActiveFilters && (
          <button
            type="button"
            onClick={clearAllFilters}
            className="h-8 px-2.5 text-xs rounded-lg border border-border bg-background text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors cursor-pointer flex items-center gap-1"
          >
            <span className="material-symbols-outlined text-sm">filter_alt_off</span>
            {t("common.clear", "Clear")}
          </button>
        )}

        {/* Spacer + Count */}
        <div className="ml-auto shrink-0">
          <span className="text-xs text-muted-foreground tabular-nums">
            {statusFilter ? `${filteredSources.length} ${t("common.of", "of")} ` : ""}{total} {t("knowledge.docCount", "document")}{total !== 1 ? "s" : ""}
          </span>
        </div>
      </div>

      {/* Table */}
      <div className="bg-card rounded-xl border border-border shadow-sahara overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <span className="material-symbols-outlined text-3xl text-muted-foreground animate-spin">
              progress_activity
            </span>
          </div>
        ) : filteredSources.length === 0 ? (
          <EmptyState
            icon="cloud_upload"
            title={search ? t("common.noResults", "No results found") : t("knowledge.emptyTitle", "No documents found")}
            description={search ? `${t("common.noResults", "No results found")}: "${search}"` : t("knowledge.emptyDesc", "Upload documents to start building your knowledge base.")}
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground">{t("knowledge.colDocument", "Document")}</TableHead>
                <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground">{t("knowledge.colCategory", "Category")}</TableHead>
                <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground">{t("knowledge.colVisibility", "Visibility")}</TableHead>
                <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground">{t("knowledge.colDepartment", "Department")}</TableHead>
                <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground">{t("knowledge.colPages", "Pages")}</TableHead>
                <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground">{t("knowledge.colWiki", "Wiki")}</TableHead>
                <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground">{t("knowledge.colContributedBy", "Contributed By")}</TableHead>
                <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground">{t("knowledge.colStatus", "Status")}</TableHead>
                <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground">{t("common.created", "Created")}</TableHead>
                <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground text-right w-[60px]"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredSources.map((source) => (
                <TableRow key={source.id} className="group hover:bg-secondary/30 transition-colors">
                  {/* Document name + icon */}
                  <TableCell>
                    <div className="flex items-center gap-2.5">
                      <span className="material-symbols-outlined text-muted-foreground" style={{ fontSize: 18 }}>
                        {fileIcons[getFileExt(source)] || (source.source_type === "url" ? "link" : "description")}
                      </span>
                      <div className="min-w-0">
                        <Link href={`/wiki/source/${source.id}`} className="text-sm font-medium text-foreground truncate max-w-[280px] hover:text-primary hover:underline transition-colors">{source.title}</Link>
                        {source.file_name && source.file_name !== source.title && (
                          <p className="text-[10px] text-muted-foreground truncate max-w-[280px]">{source.file_name}</p>
                        )}
                      </div>
                    </div>
                  </TableCell>

                  {/* Category (Knowledge Type) */}
                  <TableCell>
                    <div className="flex flex-wrap items-center gap-1">
                      {source.knowledge_type_name ? (
                        <Badge
                          variant="outline"
                          className="text-[10px] font-medium h-5 px-2"
                          style={{
                            borderColor: source.knowledge_type_color,
                            color: source.knowledge_type_color,
                          }}
                        >
                          {source.knowledge_type_name}
                        </Badge>
                      ) : (
                        <span className="text-xs text-muted-foreground/50">—</span>
                      )}
                      {source.preserve_verbatim && (
                        <Badge
                          variant="secondary"
                          className="text-[10px] font-medium h-5 px-2"
                          title="Keep verbatim — skip wiki generation"
                        >
                          Verbatim
                        </Badge>
                      )}
                    </div>
                  </TableCell>

                  {/* Visibility */}
                  <TableCell>
                    <ScopeBadge scopeType={source.scope_type} scopeId={source.scope_id} />
                  </TableCell>

                  {/* Department(s) */}
                  <TableCell>
                    {source.department_names && source.department_names.length > 0 ? (
                      <div className="flex flex-wrap gap-1">
                        {source.department_names.map((name, i) => (
                          <span key={i} className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-secondary text-secondary-foreground">
                            {name}
                          </span>
                        ))}
                      </div>
                    ) : (
                      <span className="text-xs text-muted-foreground/50 italic">Global</span>
                    )}
                  </TableCell>

                  {/* Page count */}
                  <TableCell>
                    <span className="text-xs text-muted-foreground tabular-nums">
                      {source.page_count ?? "—"}
                    </span>
                  </TableCell>

                  {/* Wiki page count */}
                  <TableCell>
                    {(source.wiki_page_count ?? 0) > 0 ? (
                      <span className="text-xs text-foreground tabular-nums">
                        {source.wiki_page_count}
                      </span>
                    ) : (
                      <span className="text-xs text-muted-foreground/50">—</span>
                    )}
                  </TableCell>

                  {/* Contributed by */}
                  <TableCell>
                    {source.contributed_by_name ? (
                      <span className="text-xs text-muted-foreground">{source.contributed_by_name}</span>
                    ) : (
                      <span className="text-xs text-muted-foreground/50">—</span>
                    )}
                  </TableCell>

                  {/* Status */}
                  <TableCell>
                    <StatusDot source={source} />
                  </TableCell>

                  {/* Created date */}
                  <TableCell>
                    <span className="text-xs text-muted-foreground tabular-nums">
                      {new Date(source.created_at).toLocaleDateString("en-US", {
                        month: "short", day: "numeric", year: "numeric",
                      })}
                    </span>
                  </TableCell>

                  {/* Actions */}
                  <TableCell className="text-right">
                    <DropdownMenu>
                      <DropdownMenuTrigger className="inline-flex items-center justify-center h-7 w-7 rounded-md hover:bg-accent text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity">
                        <span className="material-symbols-outlined text-base">more_vert</span>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => router.push(`/wiki/source/${source.id}`)}>
                          <span className="material-symbols-outlined mr-2" style={{ fontSize: 16 }}>visibility</span>
                          {t("common.view", "View")}
                        </DropdownMenuItem>
                        {source.status === "ready" && (
                          <DropdownMenuItem
                            onClick={async () => {
                              try {
                                const detail = await api<{ download_url?: string }>(`/api/sources/${source.id}`);
                                if (detail.download_url) window.open(detail.download_url, "_blank");
                              } catch {}
                            }}
                          >
                            <span className="material-symbols-outlined mr-2" style={{ fontSize: 16 }}>cloud_download</span>
                            {t("common.download", "Download")}
                          </DropdownMenuItem>
                        )}
                        <DropdownMenuSeparator />
                        <DropdownMenuItem onClick={() => setEditSource(source)}>
                          <span className="material-symbols-outlined mr-2" style={{ fontSize: 16 }}>edit</span>
                          {t("common.edit", "Edit")}
                        </DropdownMenuItem>
                        {source.status === "plan_ready" && (
                          <DropdownMenuItem onClick={() => setReviewPlanSource(source)}>
                            <span className="material-symbols-outlined mr-2 text-blue-500" style={{ fontSize: 16 }}>
                              fact_check
                            </span>
                            {t("knowledge.status.plan_ready", "Review Plan")}
                          </DropdownMenuItem>
                        )}
                        {source.status === "awaiting_approval" && (
                          <DropdownMenuItem onClick={() => setReviewExtractionSource(source)}>
                            <span className="material-symbols-outlined mr-2 text-orange-500" style={{ fontSize: 16 }}>
                              scale
                            </span>
                            {t("knowledge.status.awaiting_approval", "Review Size")}
                          </DropdownMenuItem>
                        )}
                        {source.status === "error" && (
                          <DropdownMenuItem
                            onClick={() => handleRetry(source.id)}
                            disabled={retryingIds.has(source.id)}
                          >
                            <span className={`material-symbols-outlined mr-2 ${retryingIds.has(source.id) ? "animate-spin" : ""}`} style={{ fontSize: 16 }}>
                              refresh
                            </span>
                            {retryingIds.has(source.id) ? t("common.retrying", "Retrying...") : t("common.retry", "Retry")}
                          </DropdownMenuItem>
                        )}
                        <DropdownMenuSeparator />
                        <DropdownMenuItem
                          onClick={() => handleDelete(source.id)}
                          className="text-destructive"
                        >
                          <span className="material-symbols-outlined mr-2" style={{ fontSize: 16 }}>delete</span>
                          {t("common.delete", "Delete")}
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-3">
          <span className="text-xs text-muted-foreground">
            {t("common.page", "Page")} {page} {t("common.of", "of")} {totalPages}
          </span>
          <div className="flex items-center gap-1">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => onPageChange(page - 1)}
              className="h-8 px-2.5"
            >
              <span className="material-symbols-outlined text-sm">chevron_left</span>
            </Button>
            {Array.from({ length: Math.min(totalPages, 7) }, (_, i) => {
              let p: number;
              if (totalPages <= 7) {
                p = i + 1;
              } else if (page <= 4) {
                p = i + 1;
              } else if (page >= totalPages - 3) {
                p = totalPages - 6 + i;
              } else {
                p = page - 3 + i;
              }
              return (
                <Button
                  key={p}
                  variant={p === page ? "default" : "outline"}
                  size="sm"
                  onClick={() => onPageChange(p)}
                  className={`h-8 w-8 p-0 text-xs ${p === page ? "bg-primary text-primary-foreground" : ""}`}
                >
                  {p}
                </Button>
              );
            })}
            <Button
              variant="outline"
              size="sm"
              disabled={page >= totalPages}
              onClick={() => onPageChange(page + 1)}
              className="h-8 px-2.5"
            >
              <span className="material-symbols-outlined text-sm">chevron_right</span>
            </Button>
          </div>
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
