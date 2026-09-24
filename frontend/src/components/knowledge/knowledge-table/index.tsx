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
import { fileIcons, getFileExt, parseSourceLegalMeta, LegalCategory } from "./utils";
import { StatusDot } from "./status-dot";
import { EditSourceDialog } from "./edit-source-dialog";
import { PlanReviewDialog } from "./plan-review-dialog";
import { ExtractionReviewDialog } from "./extraction-review-dialog";
import { SourceArticlesDrawer } from "./source-articles-drawer";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

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
  const [legalCategoryFilter, setLegalCategoryFilter] = React.useState<LegalCategory>("all");
  const [expandedSourceIds, setExpandedSourceIds] = React.useState<Set<string>>(new Set());
  const router = useRouter();

  const toggleExpand = (id: string) => {
    setExpandedSourceIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

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

  const filteredSources = React.useMemo(() => {
    let list = sources;
    if (statusFilter) {
      list = list.filter((s) => s.status === statusFilter);
    }
    if (legalCategoryFilter !== "all") {
      list = list.filter((s) => {
        const meta = parseSourceLegalMeta(s);
        return meta.category === legalCategoryFilter;
      });
    }
    return list;
  }, [sources, statusFilter, legalCategoryFilter]);

  const hasActiveFilters = Boolean(
    selectedType || selectedDepartment || statusFilter || legalCategoryFilter !== "all" || searchInput
  );
  const clearAllFilters = () => {
    onSelectType(null);
    onSelectDepartment(null);
    setStatusFilter(null);
    setLegalCategoryFilter("all");
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

      {/* Legal Category Pills Bar */}
      <div className="flex items-center gap-1.5 overflow-x-auto pb-1 scrollbar-none">
        {(
          [
            { id: "all", label: "Tất cả", icon: "library_books" },
            { id: "luat", label: "Luật", icon: "gavel" },
            { id: "nghi_dinh", label: "Nghị định", icon: "policy" },
            { id: "thong_tu", label: "Thông tư", icon: "description" },
            { id: "vbhn", label: "Văn bản hợp nhất", icon: "integration_instructions" },
            { id: "quyet_dinh", label: "Quyết định", icon: "verified" },
            { id: "khac", label: "Khác", icon: "folder" },
          ] as const
        ).map((tab) => {
          const count = categoryCounts[tab.id] ?? 0;
          if (tab.id !== "all" && count === 0) return null;
          const active = legalCategoryFilter === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => setLegalCategoryFilter(tab.id)}
              className={cn(
                "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-all cursor-pointer shrink-0 shadow-2xs",
                active
                  ? "bg-primary text-primary-foreground border-primary font-semibold shadow-xs"
                  : "bg-card border-border text-muted-foreground hover:text-foreground hover:bg-secondary/70"
              )}
            >
              <span className="material-symbols-outlined text-[15px]">{tab.icon}</span>
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
            {statusFilter || legalCategoryFilter !== "all" ? `${filteredSources.length} ${t("common.of", "of")} ` : ""}{total} {t("knowledge.docCount", "document")}{total !== 1 ? "s" : ""}
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
                <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground min-w-[340px]">
                  Văn bản quy phạm pháp luật
                </TableHead>
                <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground w-[160px]">
                  Phân loại & Phạm vi
                </TableHead>
                <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground w-[80px]">
                  Số trang
                </TableHead>
                <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground w-[170px]">
                  Điều khoản Wiki
                </TableHead>
                <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground w-[110px]">
                  Trạng thái
                </TableHead>
                <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground w-[100px]">
                  Ngày tải
                </TableHead>
                <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground text-right w-[50px]"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredSources.map((source) => {
                const meta = parseSourceLegalMeta(source);
                const isExpanded = expandedSourceIds.has(source.id);
                const hasArticles = (source.wiki_page_count ?? 0) > 0;

                return (
                  <React.Fragment key={source.id}>
                    <TableRow className={cn(
                      "group transition-colors",
                      isExpanded ? "bg-accent/40" : "hover:bg-secondary/30"
                    )}>
                      {/* Document Details Column */}
                      <TableCell className="py-3">
                        <div className="flex items-start gap-3">
                          {/* Legal Icon Badge */}
                          <div className="pt-0.5 shrink-0">
                            <span
                              className={cn(
                                "inline-flex items-center justify-center w-8 h-8 rounded-lg shadow-2xs border",
                                meta.badgeBg,
                                meta.badgeBorder
                              )}
                            >
                              <span className="material-symbols-outlined text-lg" style={{ color: meta.badgeColor }}>
                                {fileIcons[getFileExt(source)] || (source.source_type === "url" ? "link" : "gavel")}
                              </span>
                            </span>
                          </div>

                          <div className="min-w-0 flex-1 space-y-1">
                            {/* Badges line: Category & Doc Number */}
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

                            {/* Main Title: Full view, comfortable line-clamp */}
                            <Link
                              href={`/wiki/source/${source.id}`}
                              className="block text-sm font-semibold text-foreground hover:text-primary transition-colors leading-snug line-clamp-2"
                              title={source.title}
                            >
                              {source.title}
                            </Link>

                            {/* Subtitle: Authority, date, file name */}
                            <div className="flex items-center gap-2.5 text-[11px] text-muted-foreground flex-wrap pt-0.5">
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
                              {source.file_name && source.file_name !== source.title && (
                                <span className="truncate max-w-[200px] text-muted-foreground/70" title={source.file_name}>
                                  ({source.file_name})
                                </span>
                              )}
                            </div>
                          </div>
                        </div>
                      </TableCell>

                      {/* Category & Scope */}
                      <TableCell className="py-3">
                        <div className="flex flex-col gap-1.5">
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
                            ) : null}
                            {source.preserve_verbatim && (
                              <Badge
                                variant="secondary"
                                className="text-[10px] font-medium h-5 px-1.5"
                                title="Giữ nguyên văn bản"
                              >
                                Verbatim
                              </Badge>
                            )}
                          </div>
                          <ScopeBadge scopeType={source.scope_type} scopeId={source.scope_id} />
                        </div>
                      </TableCell>

                      {/* Page count */}
                      <TableCell className="py-3">
                        <span className="text-xs text-muted-foreground tabular-nums font-medium">
                          {source.page_count ? `${source.page_count} trang` : "—"}
                        </span>
                      </TableCell>

                      {/* Wiki Articles & Accordion Trigger */}
                      <TableCell className="py-3">
                        {hasArticles ? (
                          <div className="flex flex-col gap-1 items-start">
                            <button
                              type="button"
                              onClick={() => toggleExpand(source.id)}
                              className={cn(
                                "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold border transition-all cursor-pointer shadow-2xs",
                                isExpanded
                                  ? "bg-primary text-primary-foreground border-primary shadow-xs"
                                  : "bg-primary/10 text-primary border-primary/30 hover:bg-primary/20"
                              )}
                              title="Bấm để xem nhanh các Điều trong văn bản"
                            >
                              <span className="material-symbols-outlined text-[15px]">
                                {isExpanded ? "unfold_less" : "menu_book"}
                              </span>
                              <span className="tabular-nums">{source.wiki_page_count}</span> Điều
                              <span className="material-symbols-outlined text-xs ml-0.5">
                                {isExpanded ? "expand_less" : "expand_more"}
                              </span>
                            </button>

                            <Link
                              href={`/wiki/source/${source.id}`}
                              className="text-[11px] text-muted-foreground hover:text-primary transition-colors flex items-center gap-0.5 pl-0.5"
                            >
                              Mục lục chi tiết
                              <span className="material-symbols-outlined text-[12px]">arrow_forward</span>
                            </Link>
                          </div>
                        ) : (
                          <span className="text-xs text-muted-foreground/50 italic">—</span>
                        )}
                      </TableCell>

                      {/* Status */}
                      <TableCell className="py-3">
                        <StatusDot source={source} />
                      </TableCell>

                      {/* Created date */}
                      <TableCell className="py-3">
                        <span className="text-xs text-muted-foreground tabular-nums">
                          {new Date(source.created_at).toLocaleDateString("vi-VN", {
                            day: "2-digit",
                            month: "2-digit",
                            year: "numeric",
                          })}
                        </span>
                      </TableCell>

                      {/* Actions */}
                      <TableCell className="text-right py-3">
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

                    {/* Inline Expanded Articles Drawer */}
                    {isExpanded && (
                      <TableRow className="bg-muted/15 border-b border-border/80">
                        <TableCell colSpan={7} className="p-0">
                          <SourceArticlesDrawer
                            source={source}
                            onClose={() => toggleExpand(source.id)}
                          />
                        </TableCell>
                      </TableRow>
                    )}
                  </React.Fragment>
                );
              })}
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
