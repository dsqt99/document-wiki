"use client";

import { OptionSelect } from "@/components/ui/option-select";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { errorText, type SourceListResponse } from "@/components/knowledge/types";
import { ScopeBadge } from "@/components/shared/scope-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { encodeSlugPath } from "@/components/wiki/wiki-pages-loader";
import { WikiStatusBadge } from "@/components/wiki/wiki-status-badge";
import { WikiOriginBadge } from "@/components/wiki/wiki-origin-badge";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/i18n";
import { sanitizeWikiLibraryReturnTo, wikiPageQuery } from "@/lib/wiki-navigation";
import { displaySourceTitle, getCachedSources, setCachedSources, type WikiSourceItem } from "@/lib/wiki-store";
import type { WikiPageSummary } from "@/types/wiki";
import type { WikiLibraryResponse } from "@/lib/wiki-search";

type LibraryResponse = WikiLibraryResponse;
type Props = {
  refreshKey?: number;
  /** Reports the total readable library count, independent of active filters. */
  onCountChange?: (total: number) => void;
};

const PAGE_SIZE = 30;
const FILTER_KEYS = ["wiki_q", "wiki_source", "wiki_type", "wiki_tag", "wiki_page"];
const controlClass = "h-9 w-full min-w-0 rounded-lg border border-input bg-background px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50";

function Icon({ name, className }: { name: string; className?: string }) {
  return <span aria-hidden="true" className={cn("material-symbols-outlined text-[18px]!", className)}>{name}</span>;
}

function pageLink(page: WikiPageSummary, returnTo: string, edit = false): string {
  return `/wiki/${encodeSlugPath(page.slug)}${wikiPageQuery(page.scope_type, page.scope_id, returnTo, edit)}`;
}

function formatUpdated(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Chưa rõ" : date.toLocaleString("vi-VN", { dateStyle: "short", timeStyle: "short" });
}

export function WikiLibrary({ refreshKey = 0, onCountChange }: Props) {
  const { t } = useI18n();
  const pageTypes = [["concept", t("wiki.type.concept")], ["source", t("wiki.type.source")]];
  const params = useSearchParams();
  const pathname = usePathname();
  const returnTo = sanitizeWikiLibraryReturnTo(`${pathname}?${params}`);
  const { user, hasPermission } = useAuth();
  const search = params.get("wiki_q") ?? "";
  const sourceId = params.get("wiki_source") ?? "";
  const pageType = params.get("wiki_type") ?? "";
  const originTag = params.get("wiki_tag") ?? "";
  const rawPage = Number(params.get("wiki_page") ?? 1);
  const page = Number.isSafeInteger(rawPage) && rawPage > 0 ? Math.min(rawPage, Math.floor(Number.MAX_SAFE_INTEGER / PAGE_SIZE)) : 1;
  const [draft, setDraft] = useState({ base: search, value: search });
  const searchInput = draft.base === search ? draft.value : search;
  const [retryKey, setRetryKey] = useState(0);
  const [sourceRetryKey, setSourceRetryKey] = useState(0);
  const [sources, setSources] = useState<WikiSourceItem[]>(() => getCachedSources() ?? []);
  const [sourceError, setSourceError] = useState<string | null>(null);
  const [result, setResult] = useState<{ key: string; data?: LibraryResponse; error?: string } | null>(null);

  // Native history updates are integrated with Next's search params, and avoid a route reload.
  const updateFilters = useCallback((patch: Record<string, string>, resetPage = true) => {
    const next = new URLSearchParams(window.location.search);
    next.delete("tab");
    next.delete("wiki_status");
    next.set("view", "wiki");
    if (resetPage) next.delete("wiki_page");
    Object.entries(patch).forEach(([key, value]) => {
      if (value) next.set(key, value);
      else next.delete(key);
    });
    window.history.replaceState(null, "", `${window.location.pathname}?${next}${window.location.hash}`);
  }, []);

  useEffect(() => {
    if (searchInput === search) return;
    const timer = setTimeout(() => updateFilters({ wiki_q: searchInput.trim() }), 300);
    return () => clearTimeout(timer);
  }, [searchInput, search, updateFilters]);

  const query = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String((page - 1) * PAGE_SIZE) });
  if (search) query.set("q", search);
  if (sourceId) query.set("source_id", sourceId);
  if (pageType) query.set("page_type", pageType);
  if (originTag) query.set("origin_tag", originTag);
  const queryString = query.toString();
  const resultKey = `${queryString}:${refreshKey}:${retryKey}`;
  const loading = result?.key !== resultKey || searchInput.trim() !== search;
  const data = !loading && result?.key === resultKey ? result.data : undefined;
  const error = !loading && result?.key === resultKey ? result.error : undefined;

  useEffect(() => {
    let cancelled = false;
    api<LibraryResponse>(`/api/wiki/library?${queryString}`)
      .then((res) => {
        if (cancelled) return;
        const lastPage = Math.max(1, Math.ceil(res.total / PAGE_SIZE));
        if (page > lastPage) {
          updateFilters({ wiki_page: lastPage > 1 ? String(lastPage) : "" }, false);
          return;
        }
        setResult({ key: resultKey, data: res });
      })
      .catch((err: unknown) => {
        if (!cancelled) setResult({ key: resultKey, error: errorText(err, "Không tải được danh sách Wiki") });
      });
    return () => { cancelled = true; };
  }, [queryString, resultKey, page, updateFilters]);

  useEffect(() => {
    if (!onCountChange) return;
    let cancelled = false;
    api<LibraryResponse>("/api/wiki/library?limit=1&offset=0")
      .then((res) => { if (!cancelled) onCountChange(res.total); })
      .catch(() => { /* The list request displays actionable errors. Retain the last known count. */ });
    return () => { cancelled = true; };
  }, [refreshKey, retryKey, onCountChange]);

  useEffect(() => {
    let cancelled = false;
    async function loadSources() {
      try {
        const all: WikiSourceItem[] = [];
        let nextPage = 1;
        let totalPages = 1;
        do {
          const res = await api<SourceListResponse>(`/api/sources?page_size=1000&page=${nextPage}`);
          if (cancelled) return;
          all.push(...res.items.map((source) => ({ ...source, file_name: source.file_name ?? undefined, source_type: source.source_type ?? undefined })));
          totalPages = res.total_pages ?? Math.ceil(res.total / (res.page_size || 1000));
          nextPage += 1;
        } while (nextPage <= totalPages);
        const unique = [...new Map(all.map((source) => [source.id, source])).values()];
        setCachedSources(unique);
        setSources(unique);
        setSourceError(null);
      } catch (err) {
        if (!cancelled) setSourceError(errorText(err, "Không tải được bộ lọc tài liệu"));
      }
    }
    void loadSources();
    return () => { cancelled = true; };
  }, [refreshKey, sourceRetryKey]);

  const sourceTitle = (id: string) => {
    const source = sources.find((item) => item.id === id);
    return source ? displaySourceTitle(source) : "Tài liệu đã chọn";
  };
  const clearFilters = () => {
    setDraft({ base: "", value: "" });
    updateFilters(Object.fromEntries(FILTER_KEYS.map((key) => [key, ""])));
  };
  const activeFilters = [
    ...(search ? [{ key: "wiki_q", label: `Tìm: ${search}` }] : []),
    ...(sourceId ? [{ key: "wiki_source", label: sourceTitle(sourceId) }] : []),
    ...(pageType ? [{ key: "wiki_type", label: pageTypes.find(([value]) => value === pageType)?.[1] ?? pageType }] : []),
    ...(originTag ? [{ key: "wiki_tag", label: t(`wiki.origin.${originTag}`) }] : []),
  ];
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <section aria-label="Thư viện Wiki" className="min-w-0 space-y-4">
      <div className="grid grid-cols-2 gap-3 xl:grid-cols-[minmax(220px,1fr)_minmax(180px,260px)_150px_150px]">
        <label className="col-span-2 min-w-0 space-y-1.5 sm:col-span-1">
          <span className="text-xs font-medium text-muted-foreground">Tìm trang Wiki</span>
          <div className="relative">
            <Icon name="search" className="pointer-events-none absolute top-2.5 left-2.5 text-muted-foreground" />
            <Input value={searchInput} onChange={(event) => setDraft({ base: search, value: event.target.value })} placeholder="Tìm nội dung, tiêu đề trang Wiki..." className="h-9 pl-9" />
          </div>
        </label>
        <label className="col-span-2 min-w-0 space-y-1.5 sm:col-span-1">
          <span className="text-xs font-medium text-muted-foreground">{t("wiki.filterDoc")}</span>
          <OptionSelect searchable searchPlaceholder={t("wiki.searchSource")} aria-label={t("wiki.filterDoc")} value={sourceId} onValueChange={(value) => updateFilters({ wiki_source: value })} className={controlClass}>
            <option value="">{t("wiki.allDocuments")}</option>
            {sourceId && !sources.some((source) => source.id === sourceId) && <option value={sourceId}>{t("wiki.selectedSource")}</option>}
            {sources.map((source) => <option key={source.id} value={source.id}>{displaySourceTitle(source)}</option>)}
          </OptionSelect>
        </label>
        <label className="min-w-0 space-y-1.5">
          <span className="text-xs font-medium text-muted-foreground">{t("wiki.filterType")}</span>
          <OptionSelect aria-label={t("wiki.filterType")} value={pageType} onValueChange={(value) => updateFilters({ wiki_type: value })} className={controlClass}>
            <option value="">{t("wiki.allPageTypes")}</option>
            {pageTypes.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            {pageType && !pageTypes.some(([value]) => value === pageType) && <option value={pageType}>{pageType}</option>}
          </OptionSelect>
        </label>
        <label className="min-w-0 space-y-1.5">
          <span className="text-xs font-medium text-muted-foreground">{t("wiki.origin.label")}</span>
          <OptionSelect aria-label={t("wiki.origin.filter")} value={originTag} onValueChange={(value) => updateFilters({ wiki_tag: value })} className={controlClass}>
            <option value="">{t("wiki.origin.all")}</option><option value="extracted">{t("wiki.origin.extracted")}</option><option value="generated">{t("wiki.origin.generated")}</option>
          </OptionSelect>
        </label>
      </div>

      {sourceError && <div role="alert" className="flex flex-wrap items-center gap-2 text-xs text-destructive">{sourceError}<Button size="xs" variant="outline" onClick={() => setSourceRetryKey((key) => key + 1)}>Thử lại bộ lọc</Button></div>}

      {activeFilters.length > 0 && (
        <div aria-label="Bộ lọc đang áp dụng" className="flex flex-wrap items-center gap-2">
          {activeFilters.map((filter) => (
            <button key={filter.key} type="button" onClick={() => {
              if (filter.key === "wiki_q") setDraft({ base: "", value: "" });
              updateFilters({ [filter.key]: "" });
            }} aria-label={`Bỏ bộ lọc ${filter.label}`} className="inline-flex max-w-full items-center gap-1 rounded-full border bg-muted/50 px-2.5 py-1 text-xs hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring">
              <span className="truncate">{filter.label}</span><Icon name="close" className="shrink-0 text-[14px]!" />
            </button>
          ))}
          <Button variant="ghost" size="xs" onClick={clearFilters}>Xóa bộ lọc</Button>
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
        <p role="status" aria-live="polite">{loading ? "Đang tải trang Wiki..." : error ? "Không tải được Wiki" : `${total.toLocaleString("vi-VN")} trang${activeFilters.length ? " khớp bộ lọc" : " trong thư viện"}`}</p>
        <span>{search ? data?.search?.mode === "rerank" ? `Liên quan nhất · điểm > ${data.search.threshold}` : "Theo độ liên quan" : "Mới cập nhật trước"}</span>
      </div>
      {data?.search?.warning && <p role="status" className="rounded-lg border border-amber-400/40 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:bg-amber-900/15 dark:text-amber-200">{data.search.warning}</p>}
      {data?.search && <p className="text-xs text-muted-foreground">Kết quả từ tối đa {data.search.candidate_limit} ứng viên phù hợp bộ lọc.</p>}

      <div aria-busy={loading} className="overflow-hidden rounded-xl border bg-card">
        {loading ? (
          <div className="flex min-h-56 items-center justify-center gap-2 text-sm text-muted-foreground"><Icon name="progress_activity" className="animate-spin" />Đang tải thư viện Wiki...</div>
        ) : error ? (
          <div role="alert" className="flex min-h-56 flex-col items-center justify-center gap-3 px-4 text-center"><Icon name="error" className="text-destructive" /><p className="text-sm text-destructive">{error}</p><Button variant="outline" size="sm" onClick={() => setRetryKey((key) => key + 1)}>Thử lại</Button></div>
        ) : !data?.items.length ? (
          <div className="flex min-h-56 flex-col items-center justify-center gap-2 px-4 text-center"><Icon name="menu_book" className="text-[28px]! text-muted-foreground" /><p className="text-sm font-medium">{activeFilters.length ? "Không có trang Wiki phù hợp" : "Chưa có trang Wiki"}</p><p className="text-xs text-muted-foreground">{activeFilters.length ? "Thử từ khóa khác hoặc bỏ bớt bộ lọc." : "Các trang Wiki sẽ xuất hiện sau khi tài liệu được xử lý."}</p>{activeFilters.length > 0 && <Button variant="outline" size="sm" className="mt-2" onClick={clearFilters}>Xóa bộ lọc</Button>}</div>
        ) : (
          <div>
          <div className="hidden grid-cols-[minmax(0,1fr)_110px_95px] gap-5 border-b bg-muted/30 px-4 py-2 text-xs font-medium text-muted-foreground sm:grid"><span>Trang Wiki</span><span>{t("wiki.origin.label")}</span><span className="text-right">Thao tác</span></div>
          <ul className="divide-y">
            {data.items.map((item) => {
              const canEdit = hasPermission("wiki:write:all") || (hasPermission("wiki:write:own_dept") && (item.scope_type !== "department" || !!item.scope_id && !!(user?.scope_department_ids ?? user?.department_ids)?.includes(item.scope_id)));
              const sourceTitles = (item.source_ids ?? []).map(sourceTitle);
              let title = item.title || item.slug;
              for (const source of sourceTitles) {
                const suffix = ` - ${source}`;
                if (title.endsWith(suffix)) title = title.slice(0, -suffix.length);
              }
              const summary = item.summary?.replace(new RegExp(`^${title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*[–—-]\\s*`), "");
              return (
                <li key={`${item.slug}:${item.scope_type ?? "global"}:${item.scope_id ?? ""}`} className="group grid grid-cols-1 gap-3 px-4 py-4 transition-colors hover:bg-muted/25 sm:grid-cols-[minmax(0,1fr)_110px_95px] sm:items-start sm:gap-5">
                  <div className="min-w-0 flex-1 space-y-2">
                    <Link href={pageLink(item, returnTo)} className="block w-fit max-w-full rounded-sm text-sm font-semibold break-words hover:text-primary hover:underline focus-visible:ring-2 focus-visible:ring-ring">{title}</Link>
                    <p className="line-clamp-2 text-sm leading-relaxed break-words text-muted-foreground">{summary || "Chưa có tóm tắt."}</p>
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5 text-[11px] text-muted-foreground">
                      <span>{pageTypes.find(([value]) => value === item.page_type)?.[1] ?? item.page_type}</span>
                      {item.rerank_score != null && <span>Điểm liên quan {item.rerank_score.toFixed(3)}</span>}
                      <ScopeBadge scopeType={item.scope_type} />
                      {item.scope_name && item.scope_type !== "global" && <span>{item.scope_name}</span>}
                      <WikiStatusBadge status={(item.status as string) === "growing" ? "developing" : item.status} />
                      <span>Cập nhật <time dateTime={item.updated_at}>{formatUpdated(item.updated_at)}</time></span>
                    </div>
                    {!!item.source_ids?.length && <p className="truncate text-xs text-muted-foreground" title={item.source_ids.map(sourceTitle).join(" · ")}>Tài liệu: {item.source_ids.map(sourceTitle).join(" · ")}</p>}
                  </div>
                  <div><span className="mr-2 text-xs text-muted-foreground sm:hidden">{t("wiki.origin.label")}</span><WikiOriginBadge tag={item.origin_tag} /></div>
                  <div className="flex shrink-0 items-center justify-end gap-2 text-xs">
                    {canEdit && <Link href={pageLink(item, returnTo, true)} className="inline-flex h-8 items-center gap-1 rounded-lg px-2 font-medium text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"><Icon name="edit" />Chỉnh sửa</Link>}
                  </div>
                </li>
              );
            })}
          </ul>
          </div>
        )}
      </div>

      {!loading && !error && total > 0 && (
        <nav aria-label="Phân trang Wiki" className="flex flex-wrap items-center justify-between gap-3 text-xs text-muted-foreground">
          <span>{(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, total)} / {total.toLocaleString("vi-VN")} trang</span>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => updateFilters({ wiki_page: page > 2 ? String(page - 1) : "" }, false)}><Icon name="chevron_left" />Trước</Button>
            <span aria-current="page">{page} / {totalPages}</span>
            <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => updateFilters({ wiki_page: String(page + 1) }, false)}>Sau<Icon name="chevron_right" /></Button>
          </div>
        </nav>
      )}
    </section>
  );
}
