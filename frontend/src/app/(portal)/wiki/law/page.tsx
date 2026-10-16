"use client";

import React from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { EmptyState } from "@/components/shared/empty-state";
import { FacetGroup, FacetOption, countFacet } from "@/components/wiki/wiki-facets";
import { LegalDoc, LegalDocList } from "@/types/legal-doc";
import {
  VALIDITY_INFO,
  VALIDITY_ORDER,
  docTypeOf,
  formatViDate,
  legalDocHref,
  validityOf,
} from "@/lib/legal-doc";
import { FormattedInlineText } from "@/components/wiki/formatted-inline-text";

const PAGE_CHUNK = 30;
const NEW_WINDOW_MS = 7 * 24 * 3600 * 1000;
const NONE = "__none";

type SortKey = "issued_desc" | "issued_asc" | "effective_desc" | "title";
type FacetKey = "kt" | "type" | "validity" | "field" | "unit" | "authority" | "year";

const PERSONAL = "__personal";
const GLOBAL = "__global";

/** Phạm vi hiển thị: từng phòng ban được gắn, hoặc Toàn ngành / Cá nhân. */
const unitsOf = (d: LegalDoc): string[] =>
  d.scope_type === "personal"
    ? [PERSONAL]
    : d.departments?.length
      ? d.departments.map((x) => x.name)
      : [GLOBAL];
const unitLabel = (k: string) => (k === PERSONAL ? "Cá nhân" : k === GLOBAL ? "Toàn ngành" : k);

/** Facets kept in component state; `kt` lives in the URL (?kt=a,b). */
type LocalFacetKey = Exclude<FacetKey, "kt">;

const EMPTY_FACETS = (): Record<LocalFacetKey, Set<string>> => ({
  type: new Set(),
  validity: new Set(),
  field: new Set(),
  unit: new Set(),
  authority: new Set(),
  year: new Set(),
});

const FACET_KEYS: Record<FacetKey, (d: LegalDoc) => string[]> = {
  kt: (d) => [d.knowledge_type?.slug ?? NONE],
  type: (d) => [docTypeOf(d)],
  validity: (d) => [validityOf(d)],
  field: (d) => [d.meta.field || NONE],
  unit: unitsOf,
  authority: (d) => [d.meta.issuing_authority || NONE],
  year: (d) => [d.meta.issued_date?.slice(0, 4) || NONE],
};

const matches = (d: LegalDoc, key: FacetKey, sel: Set<string>) =>
  sel.size === 0 || FACET_KEYS[key](d).some((v) => sel.has(v));

/** Keep selected values listed (count 0) so they can still be unchecked. */
function withSelected(opts: FacetOption[], sel: Set<string>, labelOf: (k: string) => string): FacetOption[] {
  const missing = [...sel].filter((v) => !opts.some((o) => o.value === v));
  return [...opts, ...missing.map((v) => ({ value: v, label: labelOf(v), count: 0 }))];
}

function sortDocs(list: LegalDoc[], sort: SortKey): LegalDoc[] {
  const out = [...list];
  const issued = (d: LegalDoc) => d.meta.issued_date || "";
  switch (sort) {
    case "issued_desc":
      out.sort((a, b) => issued(b).localeCompare(issued(a)) || (b.created_at ?? "").localeCompare(a.created_at ?? ""));
      break;
    case "issued_asc":
      // Undated documents go last either way.
      out.sort((a, b) => (issued(a) || "9999").localeCompare(issued(b) || "9999"));
      break;
    case "effective_desc":
      out.sort((a, b) => (b.meta.effective_date || "").localeCompare(a.meta.effective_date || ""));
      break;
    case "title":
      out.sort((a, b) => a.title.localeCompare(b.title, "vi", { numeric: true }));
      break;
  }
  return out;
}

function MetaItem({ label, value, className }: { label: string; value: React.ReactNode; className?: string }) {
  return (
    <span>
      {label} <span className={cn("text-foreground/80 font-medium", className)}>{value}</span>
    </span>
  );
}

export default function WikiLawPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const ktParam = searchParams.get("kt") || "";
  const ktSelected = React.useMemo(() => new Set(ktParam.split(",").filter(Boolean)), [ktParam]);

  const [data, setData] = React.useState<LegalDocList | null>(null);
  const [error, setError] = React.useState("");

  const [query, setQuery] = React.useState("");
  const [searchMode, setSearchMode] = React.useState<"title" | "content">("title");
  const [sort, setSort] = React.useState<SortKey>("issued_desc");
  const [facets, setFacets] = React.useState(EMPTY_FACETS);
  const [shown, setShown] = React.useState(PAGE_CHUNK);
  const [copied, setCopied] = React.useState<string | null>(null);
  const [now] = React.useState(() => Date.now());

  React.useEffect(() => {
    api<LegalDocList>("/api/wiki/legal-docs")
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Không tải được danh sách văn bản"));
  }, []);

  // Content search runs server-side (ILIKE over full text); results tagged
  // with the query they answer so stale responses are ignored.
  const trimmedQuery = query.trim();
  const contentActive = searchMode === "content" && !!trimmedQuery;
  const [contentResult, setContentResult] = React.useState<{ q: string; ids: Set<string> } | null>(null);
  const contentIds = contentActive && contentResult?.q === trimmedQuery ? contentResult.ids : null;
  const contentLoading = contentActive && !contentIds;
  React.useEffect(() => {
    if (searchMode !== "content" || !trimmedQuery) return;
    let cancelled = false;
    const t = setTimeout(() => {
      api<LegalDocList>(`/api/wiki/legal-docs?content_q=${encodeURIComponent(trimmedQuery)}`)
        .then((r) => {
          if (!cancelled) setContentResult({ q: trimmedQuery, ids: new Set(r.items.map((d) => d.id)) });
        })
        .catch(() => {
          if (!cancelled) setContentResult({ q: trimmedQuery, ids: new Set() });
        });
    }, 400);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [searchMode, trimmedQuery]);

  // Reset pagination whenever the result set definition changes
  const listKey = [query, searchMode, sort, facets, ktParam] as const;
  const [prevListKey, setPrevListKey] = React.useState(listKey);
  if (listKey.some((v, i) => v !== prevListKey[i])) {
    setPrevListKey(listKey);
    setShown(PAGE_CHUNK);
  }

  const allDocs = React.useMemo(() => data?.items ?? [], [data]);

  // 1) search
  const searched = React.useMemo(() => {
    if (!trimmedQuery) return allDocs;
    if (searchMode === "content") return contentIds ? allDocs.filter((d) => contentIds.has(d.id)) : [];
    const q = trimmedQuery.toLowerCase();
    return allDocs.filter((d) =>
      `${d.title} ${d.meta.doc_number ?? ""} ${d.meta.official_title ?? ""} ${d.file_name ?? ""}`
        .toLowerCase()
        .includes(q),
    );
  }, [allDocs, trimmedQuery, searchMode, contentIds]);

  // 2) facets — each group is counted against every *other* active filter, so
  // ticking one option never zeroes out its siblings (OR within, AND across).
  const selectedOf = React.useCallback(
    (key: FacetKey) => (key === "kt" ? ktSelected : facets[key]),
    [ktSelected, facets],
  );
  const filterExcept = React.useCallback(
    (skip: FacetKey | null) =>
      searched.filter((d) =>
        (Object.keys(FACET_KEYS) as FacetKey[]).every((k) => k === skip || matches(d, k, selectedOf(k))),
      ),
    [searched, selectedOf],
  );

  const facetOptions = React.useMemo(() => {
    const ktInfo = new Map((data?.knowledge_types ?? []).map((kt) => [kt.slug, kt]));
    const ktLabel = (k: string) => (k === NONE ? "Chưa phân loại" : ktInfo.get(k)?.name ?? k);
    const noneLabel = (fallback: string) => (k: string) => (k === NONE ? fallback : k);
    const validityLabel = (k: string) => VALIDITY_INFO[k as keyof typeof VALIDITY_INFO]?.label ?? k;
    const build = (key: FacetKey, labelOf: (k: string) => string, order?: string[]) =>
      withSelected(countFacet(filterExcept(key), FACET_KEYS[key], labelOf, order), selectedOf(key), labelOf);
    return {
      kt: build("kt", ktLabel).map((o) => ({
        ...o,
        color: o.value === NONE ? "#94a3b8" : ktInfo.get(o.value)?.color || undefined,
      })),
      type: build("type", (k) => k),
      validity: build("validity", validityLabel, VALIDITY_ORDER).map((o) => ({
        ...o,
        color: VALIDITY_INFO[o.value as keyof typeof VALIDITY_INFO]?.color,
      })),
      field: build("field", noneLabel("Chưa phân loại")),
      unit: build("unit", unitLabel),
      authority: build("authority", noneLabel("Không rõ")),
      year: build("year", noneLabel("Không rõ")).sort((a, b) => b.value.localeCompare(a.value)),
    };
  }, [data, filterExcept, selectedOf]);

  const filtered = React.useMemo(() => sortDocs(filterExcept(null), sort), [filterExcept, sort]);

  const activeFilterCount =
    ktSelected.size + Object.values(facets).reduce((n, s) => n + s.size, 0);

  const writeKt = (next: Set<string>) => {
    const params = new URLSearchParams(searchParams.toString());
    if (next.size === 0) params.delete("kt");
    else params.set("kt", [...next].join(","));
    const qs = params.toString();
    const base = window.location.pathname;
    router.replace(qs ? `${base}?${qs}` : base, { scroll: false });
  };

  const toggleFacet = (key: FacetKey, value: string) => {
    if (key === "kt") {
      const next = new Set(ktSelected);
      if (next.has(value)) next.delete(value);
      else next.add(value);
      writeKt(next);
      return;
    }
    setFacets((prev) => {
      const next = new Set(prev[key]);
      if (next.has(value)) next.delete(value);
      else next.add(value);
      return { ...prev, [key]: next };
    });
  };

  const clearFilters = () => {
    setFacets(EMPTY_FACETS());
    if (ktSelected.size) writeKt(new Set());
  };

  /** Hide a group that can't narrow anything (single value, nothing selected). */
  const facetGroup = (
    key: FacetKey,
    title: string,
    extra?: Partial<React.ComponentProps<typeof FacetGroup>>,
  ) =>
    facetOptions[key].length > 1 || selectedOf(key).size > 0 ? (
      <FacetGroup
        key={key}
        title={title}
        options={facetOptions[key]}
        selected={selectedOf(key)}
        onToggle={(v) => toggleFacet(key, v)}
        {...extra}
      />
    ) : null;

  const copyLink = (d: LegalDoc) => {
    void navigator.clipboard?.writeText(`${window.location.origin}${legalDocHref(d)}`);
    setCopied(d.id);
    setTimeout(() => setCopied((c) => (c === d.id ? null : c)), 1500);
  };

  const download = async (d: LegalDoc) => {
    try {
      const detail = await api<{ download_url?: string }>(`/api/sources/${d.id}`);
      if (detail.download_url) window.open(detail.download_url, "_blank");
    } catch {
      /* ignore — button only shows for documents with a file */
    }
  };

  const loading = !data && !error;

  return (
    <div className="flex flex-col gap-5">
      {/* Header */}
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <span className="material-symbols-outlined text-primary" style={{ fontSize: 26 }}>
              auto_stories
            </span>
            Kho tri thức
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Tra cứu văn bản theo số hiệu, lĩnh vực và tình trạng hiệu lực.
          </p>
        </div>
        <Link
          href="/wiki/graph"
          className="flex items-center gap-1.5 px-3 h-9 rounded-lg border border-border bg-background text-sm font-medium hover:bg-muted transition-colors"
        >
          <span className="material-symbols-outlined" style={{ fontSize: 17 }}>hub</span>
          Đồ thị tri thức
        </Link>
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-48">
          <span className="material-symbols-outlined text-3xl text-muted-foreground animate-spin">progress_activity</span>
        </div>
      ) : error ? (
        <EmptyState icon="error" title="Không tải được danh sách" description={error} />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_17rem] xl:grid-cols-[minmax(0,1fr)_19rem] gap-6 items-start">
          <div className="min-w-0 flex flex-col gap-4">
            {/* Search card */}
            <div className="bg-card border border-border rounded-xl p-3 flex flex-col gap-3">
              <div className="flex flex-col sm:flex-row gap-2">
                <select
                  value={searchMode}
                  onChange={(e) => setSearchMode(e.target.value as "title" | "content")}
                  className="h-10 px-3 rounded-lg border border-border bg-background text-sm font-medium focus:outline-none focus:ring-2 focus:ring-primary/30 cursor-pointer shrink-0"
                >
                  <option value="title">Tiêu đề, số hiệu</option>
                  <option value="content">Nội dung văn bản</option>
                </select>
                <div className="relative flex-1">
                  <span className="material-symbols-outlined text-lg text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2">
                    {contentLoading ? "progress_activity" : "search"}
                  </span>
                  <input
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder={
                      searchMode === "content" ? "Tìm cụm từ trong toàn văn..." : "Nhập tiêu đề hoặc số hiệu, ví dụ 75/VBHN-VPQH"
                    }
                    className="h-10 w-full pl-10 pr-8 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary/50 placeholder:text-muted-foreground/60"
                  />
                  {query && (
                    <button
                      onClick={() => setQuery("")}
                      className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground cursor-pointer"
                    >
                      <span className="material-symbols-outlined text-base">close</span>
                    </button>
                  )}
                </div>
              </div>
            </div>

            <div className="flex items-center justify-between gap-2 flex-wrap">
              <p className="text-sm text-muted-foreground">
                Tìm thấy <span className="font-semibold text-foreground tabular-nums">{filtered.length}</span> văn bản
              </p>
              <label className="flex h-8 items-center gap-2 px-2.5 rounded-lg border border-border bg-background text-xs shrink-0">
                <span className="material-symbols-outlined text-muted-foreground" style={{ fontSize: 16 }}>sort</span>
                <select
                  value={sort}
                  onChange={(e) => setSort(e.target.value as SortKey)}
                  className="bg-transparent font-medium focus:outline-none cursor-pointer"
                >
                  <option value="issued_desc">Ban hành mới nhất</option>
                  <option value="issued_asc">Ban hành cũ nhất</option>
                  <option value="effective_desc">Hiệu lực mới nhất</option>
                  <option value="title">Tên A → Z</option>
                </select>
              </label>
            </div>

            {filtered.length === 0 ? (
              <EmptyState
                icon="search_off"
                title="Không có văn bản phù hợp"
                description={
                  contentLoading
                    ? "Đang tìm..."
                    : trimmedQuery
                      ? `Không có kết quả cho "${trimmedQuery}"`
                      : "Thử bỏ bớt điều kiện lọc."
                }
              />
            ) : (
              <div className="bg-card border border-border rounded-xl divide-y divide-border">
                {filtered.slice(0, shown).map((d, i) => {
                  const v = VALIDITY_INFO[validityOf(d)];
                  const created = d.created_at ? new Date(d.created_at).getTime() : 0;
                  const isNew = created && now - created < NEW_WINDOW_MS;
                  const m = d.meta;
                  return (
                    <div key={d.id} className="group px-5 py-4 hover:bg-muted/30 transition-colors">
                      <div className="flex items-start gap-2 min-w-0">
                        <span className="text-sm text-muted-foreground tabular-nums shrink-0 pt-px">{i + 1}.</span>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2 min-w-0">
                            <Link
                              href={legalDocHref(d)}
                              className="font-semibold text-[15px] text-foreground hover:text-primary line-clamp-2 transition-colors"
                              title={d.title}
                            >
                              <FormattedInlineText text={d.title} />
                            </Link>
                            {isNew && (
                              <span className="shrink-0 px-1.5 py-px rounded text-[10px] font-semibold bg-emerald-500/15 text-emerald-700 dark:text-emerald-400">
                                Mới
                              </span>
                            )}
                            <button
                              type="button"
                              onClick={() => copyLink(d)}
                              title="Sao chép liên kết"
                              className="shrink-0 text-muted-foreground/60 hover:text-primary cursor-pointer"
                            >
                              <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
                                {copied === d.id ? "check" : "content_copy"}
                              </span>
                            </button>
                          </div>
                          {m.official_title && m.official_title !== d.title && (
                            <p className="mt-0.5 text-sm text-muted-foreground line-clamp-1">
                              <FormattedInlineText text={m.official_title} />
                            </p>
                          )}
                          <div className="mt-2 flex items-center gap-x-4 gap-y-1.5 flex-wrap text-xs text-muted-foreground">
                            <span
                              className={cn("px-2 py-px rounded-full border text-[11px] font-semibold", v.badge)}
                            >
                              {v.label}
                            </span>
                            {m.doc_number && <MetaItem label="Số hiệu" value={m.doc_number} />}
                            <MetaItem label="Ban hành" value={formatViDate(m.issued_date)} />
                            <MetaItem label="Áp dụng" value={formatViDate(m.effective_date)} />
                            {m.issuing_authority && <MetaItem label="Cơ quan" value={m.issuing_authority} />}
                            {!!m.article_count && (
                              <span className="flex items-center gap-1">
                                <span className="material-symbols-outlined" style={{ fontSize: 14 }}>format_list_numbered</span>
                                {m.article_count} điều
                              </span>
                            )}
                            {m.field && <MetaItem label="Lĩnh vực" value={m.field} />}
                            <MetaItem label="Phạm vi" value={unitsOf(d).map(unitLabel).join(", ")} />
                          </div>
                          {(d.replaced_by.length > 0 || d.repealed_by.length > 0) && (
                            <p className="mt-1.5 text-xs text-muted-foreground">
                              {d.replaced_by.length > 0 && <>Bị thay thế bởi <b>{d.replaced_by.join(", ")}</b>. </>}
                              {d.repealed_by.length > 0 && <>Bị bãi bỏ bởi <b>{d.repealed_by.join(", ")}</b>.</>}
                            </p>
                          )}
                          <div className="mt-2 flex items-center gap-1 text-xs font-medium flex-wrap">
                            {(
                              [
                                ["source", "Tài liệu gốc"],
                                ["fulltext", "Toàn văn"],
                                ["overview", "Tổng quan"],
                                ["schema", "Lược đồ"],
                                ["graph", "Đồ thị"],
                              ] as const
                            ).map(([tab, label], idx) => (
                              <React.Fragment key={tab}>
                                {idx > 0 && <span className="text-border">|</span>}
                                <Link href={legalDocHref(d, tab)} className="px-1 text-primary hover:underline">
                                  {label}
                                </Link>
                              </React.Fragment>
                            ))}
                            {d.has_file && (
                              <>
                                <span className="text-border">|</span>
                                <button
                                  type="button"
                                  onClick={() => void download(d)}
                                  className="px-1 text-primary hover:underline cursor-pointer flex items-center gap-0.5"
                                >
                                  <span className="material-symbols-outlined" style={{ fontSize: 14 }}>download</span>
                                  Tải về
                                </button>
                              </>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
            {filtered.length > shown && (
              <button
                onClick={() => setShown((n) => n + PAGE_CHUNK)}
                className="self-center px-4 py-1.5 rounded-lg text-sm font-medium border border-border bg-background hover:bg-muted cursor-pointer"
              >
                Xem thêm ({filtered.length - shown} văn bản)
              </button>
            )}
          </div>

          {/* Facet sidebar */}
          <aside className="order-first lg:order-none bg-card border border-border rounded-xl px-4 pt-3 pb-1 lg:sticky lg:top-0 lg:max-h-[calc(100vh-7rem)] lg:overflow-y-auto">
            <div className="flex items-center justify-between pb-2">
              <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Tra cứu nhanh</span>
              {activeFilterCount > 0 && (
                <button onClick={clearFilters} className="text-xs font-medium text-primary hover:underline cursor-pointer">
                  Xóa điều kiện lọc
                </button>
              )}
            </div>
            {facetGroup("kt", "Kiểu tri thức")}
            {facetGroup("type", "Loại văn bản")}
            {facetGroup("validity", "Tình trạng hiệu lực")}
            {facetGroup("field", "Lĩnh vực", { searchable: true, searchPlaceholder: "Tìm lĩnh vực..." })}
            {facetGroup("unit", "Phòng ban / phạm vi", { searchable: true, searchPlaceholder: "Tìm phòng ban..." })}
            {facetGroup("authority", "Cơ quan ban hành", {
              searchable: true,
              searchPlaceholder: "Tìm cơ quan...",
              defaultOpen: false,
            })}
            {facetGroup("year", "Năm ban hành", { defaultOpen: false })}
          </aside>
        </div>
      )}
    </div>
  );
}
