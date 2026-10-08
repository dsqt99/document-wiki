"use client";

import React from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { EmptyState } from "@/components/shared/empty-state";
import { FacetGroup, countFacet } from "@/components/wiki/wiki-facets";
import { LegalDoc, LegalDocList } from "@/types/legal-doc";
import {
  VALIDITY_INFO,
  VALIDITY_ORDER,
  docTypeOf,
  formatViDate,
  legalDocHref,
  validityOf,
} from "@/lib/legal-doc";

const PAGE_CHUNK = 30;
const NEW_WINDOW_MS = 7 * 24 * 3600 * 1000;
const NONE = "__none";

type SortKey = "issued_desc" | "issued_asc" | "effective_desc" | "title";
type FacetKey = "field" | "validity" | "authority" | "year";

const EMPTY_FACETS = (): Record<FacetKey, Set<string>> => ({
  field: new Set(),
  validity: new Set(),
  authority: new Set(),
  year: new Set(),
});

const FACET_KEYS: Record<FacetKey, (d: LegalDoc) => string[]> = {
  field: (d) => [d.meta.field || NONE],
  validity: (d) => [validityOf(d)],
  authority: (d) => [d.meta.issuing_authority || NONE],
  year: (d) => [d.meta.issued_date?.slice(0, 4) || NONE],
};

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
  const ktParam = searchParams.get("kt") || "all";

  const [data, setData] = React.useState<LegalDocList | null>(null);
  const [error, setError] = React.useState("");

  const [query, setQuery] = React.useState("");
  const [searchMode, setSearchMode] = React.useState<"title" | "content">("title");
  const [sort, setSort] = React.useState<SortKey>("issued_desc");
  const [docType, setDocType] = React.useState("all");
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
  const listKey = [query, searchMode, sort, docType, facets, ktParam] as const;
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

  // 2) knowledge-type tabs (from Knowledge setup) — counts reflect the search
  const ktTabs = React.useMemo(() => {
    const counts = new Map<string, number>();
    for (const d of searched) {
      const k = d.knowledge_type?.slug ?? NONE;
      counts.set(k, (counts.get(k) ?? 0) + 1);
    }
    const tabs = (data?.knowledge_types ?? [])
      .map((kt) => ({ id: kt.slug, label: kt.name, color: kt.color, count: counts.get(kt.slug) ?? 0 }))
      .filter((t) => t.count > 0 || t.id === ktParam);
    if (counts.get(NONE)) tabs.push({ id: NONE, label: "Chưa phân loại", color: "#94a3b8", count: counts.get(NONE)! });
    return [{ id: "all", label: "Tất cả", color: "", count: searched.length }, ...tabs];
  }, [searched, data, ktParam]);

  const setKt = (id: string) => {
    const params = new URLSearchParams(searchParams.toString());
    if (id === "all") params.delete("kt");
    else params.set("kt", id);
    const qs = params.toString();
    const base = window.location.pathname;
    router.replace(qs ? `${base}?${qs}` : base, { scroll: false });
  };

  const byKt = React.useMemo(
    () => (ktParam === "all" ? searched : searched.filter((d) => (d.knowledge_type?.slug ?? NONE) === ktParam)),
    [searched, ktParam],
  );

  // 3) doc-type tabs
  const docTypeTabs = React.useMemo(() => {
    const opts = countFacet(byKt, (d) => [docTypeOf(d)], (k) => k);
    return [{ value: "all", label: "Tất cả", count: byKt.length }, ...opts];
  }, [byKt]);
  const effectiveDocType = docTypeTabs.some((t) => t.value === docType) ? docType : "all";
  const byType = React.useMemo(
    () => (effectiveDocType === "all" ? byKt : byKt.filter((d) => docTypeOf(d) === effectiveDocType)),
    [byKt, effectiveDocType],
  );

  // 4) facets
  const facetOptions = React.useMemo(
    () => ({
      field: countFacet(byType, FACET_KEYS.field, (k) => (k === NONE ? "Chưa phân loại" : k)),
      validity: countFacet(
        byType,
        FACET_KEYS.validity,
        (k) => VALIDITY_INFO[k as keyof typeof VALIDITY_INFO]?.label ?? k,
        VALIDITY_ORDER,
      ).map((o) => ({ ...o, color: VALIDITY_INFO[o.value as keyof typeof VALIDITY_INFO]?.color })),
      authority: countFacet(byType, FACET_KEYS.authority, (k) => (k === NONE ? "Không rõ" : k)),
      year: countFacet(byType, FACET_KEYS.year, (k) => (k === NONE ? "Không rõ" : k)).sort((a, b) =>
        b.value.localeCompare(a.value),
      ),
    }),
    [byType],
  );

  const filtered = React.useMemo(() => {
    let list = byType;
    for (const key of Object.keys(facets) as FacetKey[]) {
      const sel = facets[key];
      if (sel.size === 0) continue;
      list = list.filter((d) => FACET_KEYS[key](d).some((v) => sel.has(v)));
    }
    return sortDocs(list, sort);
  }, [byType, facets, sort]);

  const activeFilterCount =
    Object.values(facets).reduce((n, s) => n + s.size, 0) + (effectiveDocType !== "all" ? 1 : 0);

  const toggleFacet = (key: FacetKey, value: string) =>
    setFacets((prev) => {
      const next = new Set(prev[key]);
      if (next.has(value)) next.delete(value);
      else next.add(value);
      return { ...prev, [key]: next };
    });

  const clearFilters = () => {
    setFacets(EMPTY_FACETS());
    setDocType("all");
  };

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
            Trang wiki
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

      {/* Knowledge-type tabs (from Knowledge setup) */}
      <div className="flex items-center gap-1 border-b border-border overflow-x-auto overflow-y-hidden">
        {ktTabs.map((tab) => {
          const active = ktParam === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setKt(tab.id)}
              className={cn(
                "flex items-center gap-1.5 px-3 py-2 -mb-px text-sm font-medium border-b-2 whitespace-nowrap transition-colors cursor-pointer",
                active ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground",
              )}
            >
              {tab.color && <span className="size-2 rounded-full shrink-0" style={{ backgroundColor: tab.color }} />}
              {tab.label}
              <span className="text-xs tabular-nums text-muted-foreground">({tab.count})</span>
            </button>
          );
        })}
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
              <div className="flex items-center gap-2 flex-wrap">
                <div className="flex items-center gap-1.5 flex-wrap mr-auto">
                  {docTypeTabs.map((t) => {
                    const active = effectiveDocType === t.value;
                    return (
                      <button
                        key={t.value}
                        onClick={() => setDocType(t.value)}
                        className={cn(
                          "px-3 py-1 rounded-full text-xs font-medium border transition-colors cursor-pointer",
                          active
                            ? "bg-primary text-primary-foreground border-primary"
                            : "bg-background border-border text-muted-foreground hover:text-foreground",
                        )}
                      >
                        {t.label} <span className="tabular-nums opacity-80">({t.count})</span>
                      </button>
                    );
                  })}
                </div>
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
            </div>

            <p className="text-sm text-muted-foreground">
              Tìm thấy <span className="font-semibold text-foreground tabular-nums">{filtered.length}</span> văn bản
            </p>

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
                              {d.title}
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
                            <p className="mt-0.5 text-sm text-muted-foreground line-clamp-1">{m.official_title}</p>
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
          <aside className="bg-card border border-border rounded-xl px-4 pt-3 pb-1 lg:sticky lg:top-0 lg:max-h-[calc(100vh-7rem)] lg:overflow-y-auto">
            <div className="flex items-center justify-between pb-2">
              <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Tra cứu nhanh</span>
              {activeFilterCount > 0 && (
                <button onClick={clearFilters} className="text-xs font-medium text-primary hover:underline cursor-pointer">
                  Xóa điều kiện lọc
                </button>
              )}
            </div>
            <FacetGroup
              title="Lĩnh vực"
              options={facetOptions.field}
              selected={facets.field}
              onToggle={(v) => toggleFacet("field", v)}
              searchable
              searchPlaceholder="Tìm lĩnh vực..."
            />
            <FacetGroup
              title="Tình trạng hiệu lực"
              options={facetOptions.validity}
              selected={facets.validity}
              onToggle={(v) => toggleFacet("validity", v)}
            />
            <FacetGroup
              title="Cơ quan ban hành"
              options={facetOptions.authority}
              selected={facets.authority}
              onToggle={(v) => toggleFacet("authority", v)}
              searchable
              searchPlaceholder="Tìm cơ quan..."
              defaultOpen={false}
            />
            <FacetGroup
              title="Năm ban hành"
              options={facetOptions.year}
              selected={facets.year}
              onToggle={(v) => toggleFacet("year", v)}
              defaultOpen={false}
            />
          </aside>
        </div>
      )}
    </div>
  );
}
