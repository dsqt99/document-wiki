"use client";

import React from "react";
import Link from "next/link";
import { EmptyState } from "@/components/shared/empty-state";
import { cn } from "@/lib/utils";
import { WikiSourceItem, displaySourceTitle } from "@/lib/wiki-store";
import { parseSourceLegalMeta, LegalCategory } from "@/components/knowledge/knowledge-table/utils";
import { SourceArticlesDrawer } from "@/components/knowledge/knowledge-table/source-articles-drawer";

/** "Tủ sách văn bản": source documents as cards, filtered by legal category. */
export function WikiLibraryView({
  sources,
  sourceArticleCountMap,
}: {
  sources: WikiSourceItem[];
  sourceArticleCountMap: Map<string, number>;
}) {
  const [libraryCategoryFilter, setLibraryCategoryFilter] = React.useState<LegalCategory>("all");
  const [librarySearch, setLibrarySearch] = React.useState("");
  const [selectedDrawerSource, setSelectedDrawerSource] = React.useState<WikiSourceItem | null>(null);

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

  const filteredLibrarySources = React.useMemo(() => {
    let list = sources;
    if (libraryCategoryFilter !== "all") {
      list = list.filter((s) => {
        const meta = parseSourceLegalMeta(s);
        return meta.category === libraryCategoryFilter;
      });
    }
    if (librarySearch.trim()) {
      const q = librarySearch.trim().toLowerCase();
      list = list.filter((s) => {
        const meta = parseSourceLegalMeta(s);
        const text = `${s.title || ""} ${s.file_name || ""} ${meta.docNumber || ""} ${meta.authority || ""}`.toLowerCase();
        return text.includes(q);
      });
    }
    return list;
  }, [sources, libraryCategoryFilter, librarySearch]);

  return (
    <>
                  <div className="space-y-4">
                    <div className="flex items-center gap-3 flex-wrap">
                    <div className="relative w-full sm:w-72">
                      <span className="material-symbols-outlined text-sm text-muted-foreground absolute left-2.5 top-1/2 -translate-y-1/2">
                        search
                      </span>
                      <input
                        type="text"
                        value={librarySearch}
                        onChange={(e) => setLibrarySearch(e.target.value)}
                        placeholder="Tìm theo số hiệu, tên văn bản..."
                        className="h-8 w-full pl-8 pr-7 text-xs rounded-md border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary/50 placeholder:text-muted-foreground/60"
                      />
                      {librarySearch && (
                        <button
                          onClick={() => setLibrarySearch("")}
                          className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                        >
                          <span className="material-symbols-outlined text-xs">close</span>
                        </button>
                      )}
                    </div>
                    {/* Legal Category Filter Pills */}
                    <div className="flex items-center gap-1.5 overflow-x-auto scrollbar-none">
                        {(
                          [
                            { id: "all", label: "Tất cả", icon: "library_books" },
                            { id: "luat", label: "Luật", icon: "gavel" },
                            { id: "nghi_dinh", label: "Nghị định", icon: "policy" },
                            { id: "thong_tu", label: "Thông tư", icon: "description" },
                            { id: "vbhn", label: "Văn bản hợp nhất", icon: "integration_instructions" },
                            { id: "quyet_dinh", label: "Quyết định", icon: "verified" },
                          ] as const
                        ).map((tab) => {
                          const count = categoryCounts[tab.id] ?? 0;
                          if (tab.id !== "all" && count === 0) return null;
                          const active = libraryCategoryFilter === tab.id;
                          return (
                            <button
                              key={tab.id}
                              type="button"
                              onClick={() => setLibraryCategoryFilter(tab.id)}
                              className={cn(
                                "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium border transition-all cursor-pointer shrink-0 shadow-2xs",
                                active
                                  ? "bg-primary text-primary-foreground border-primary font-semibold shadow-xs"
                                  : "bg-card border-border text-muted-foreground hover:text-foreground hover:bg-secondary/70"
                              )}
                            >
                              <span className="material-symbols-outlined text-[14px]">{tab.icon}</span>
                              <span>{tab.label}</span>
                              <span
                                className={cn(
                                  "px-1.5 py-px rounded-full text-[10px] tabular-nums font-semibold",
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
                    </div>

                    {/* Cards Grid */}
                    {filteredLibrarySources.length === 0 ? (
                      <EmptyState
                        icon="search_off"
                        title="Không tìm thấy văn bản phù hợp"
                        description={librarySearch ? `Không có kết quả khớp với "${librarySearch}"` : "Chưa có văn bản nào trong nhóm này."}
                      />
                    ) : (
                      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-3">
                        {filteredLibrarySources.map((source) => {
                          const meta = parseSourceLegalMeta(source);
                          const artCount = sourceArticleCountMap.get(source.id) || 0;

                          return (
                            <div
                              key={source.id}
                              className="group bg-card border border-border rounded-xl p-4 hover:border-primary/50 hover:shadow-sahara transition-all flex flex-col justify-between"
                            >
                              <div>
                                {/* Header: Badge & Doc Number & Article Count */}
                                <div className="flex items-center justify-between gap-2 mb-3">
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

                                  <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-primary bg-primary/10 px-2 py-0.5 rounded-full border border-primary/20 shrink-0">
                                    <span className="material-symbols-outlined text-[13px]">menu_book</span>
                                    {artCount} Điều
                                  </span>
                                </div>

                                {/* Title */}
                                <Link
                                  href={`/wiki/source/${source.id}`}
                                  className="font-heading text-sm font-semibold text-foreground group-hover:text-primary transition-colors line-clamp-2 mb-2 leading-snug block"
                                  title={source.title}
                                >
                                  {displaySourceTitle(source)}
                                </Link>

                                {/* Metadata */}
                                <div className="flex items-center gap-2.5 text-xs text-muted-foreground flex-wrap mb-4">
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
                                </div>
                              </div>

                              {/* Actions Footer */}
                              <div className="flex items-center gap-2 pt-3 border-t border-border/60">
                                <Link
                                  href={`/wiki/source/${source.id}`}
                                  className="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-primary/10 text-primary hover:bg-primary/20 transition-colors"
                                >
                                  <span className="material-symbols-outlined text-sm">visibility</span>
                                  Tổng quan
                                </Link>
                                <button
                                  type="button"
                                  onClick={() => setSelectedDrawerSource(source)}
                                  className="inline-flex items-center justify-center gap-1 px-3 py-1.5 rounded-lg text-xs font-semibold border border-border bg-background hover:bg-accent text-foreground transition-colors cursor-pointer"
                                  title="Xem danh sách các Điều trong văn bản"
                                >
                                  <span className="material-symbols-outlined text-sm">format_list_bulleted</span>
                                  Tra cứu Điều
                                </button>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>

      {/* Modal Drawer to Browse Articles of Selected Document */}
      {selectedDrawerSource && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-xs p-4 animate-in fade-in duration-200">
          <div className="bg-card border border-border rounded-2xl shadow-2xl w-full max-w-4xl max-h-[85vh] flex flex-col overflow-hidden animate-in zoom-in-95 duration-200">
            <div className="px-6 py-4 border-b border-border flex items-center justify-between gap-3 bg-muted/20">
              <div className="min-w-0">
                <span className="text-xs font-bold text-primary uppercase tracking-wider block mb-1">
                  Tra cứu danh sách Điều
                </span>
                <h2 className="text-sm font-semibold text-foreground truncate" title={selectedDrawerSource.title}>
                  {selectedDrawerSource.title}
                </h2>
              </div>
              <button
                onClick={() => setSelectedDrawerSource(null)}
                className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors cursor-pointer"
              >
                <span className="material-symbols-outlined text-lg">close</span>
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-4">
              <SourceArticlesDrawer
                source={selectedDrawerSource}
                onClose={() => setSelectedDrawerSource(null)}
              />
            </div>
          </div>
        </div>
      )}
    </>
  );
}
