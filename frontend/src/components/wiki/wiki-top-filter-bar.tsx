"use client";

import React from "react";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { WikiPageSummary } from "@/types/wiki";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import {
  useWikiStore,
  getCachedPages,
  setCachedPages,
  getCachedSources,
  setCachedSources,
  computeSourceStats,
  WikiSourceItem,
} from "@/lib/wiki-store";

interface WikiTopFilterBarProps {
  pages?: WikiPageSummary[];
  sources?: WikiSourceItem[];
  onSelectPage?: (slug: string) => void;
  className?: string;
}

export function WikiTopFilterBar({
  pages: propPages,
  sources: propSources,
  className,
}: WikiTopFilterBarProps) {
  const {
    selectedSourceId,
    categoryFilter,
    setSelectedSourceId,
    setCategoryFilter,
    resetFilters,
  } = useWikiStore();

  const [internalPages, setInternalPages] = React.useState<WikiPageSummary[]>(() => {
    return propPages || getCachedPages("/api/wiki/pages") || [];
  });
  const [prevPropPages, setPrevPropPages] = React.useState(propPages);
  if (propPages && propPages !== prevPropPages) {
    setPrevPropPages(propPages);
    setInternalPages(propPages);
  }

  const [internalSources, setInternalSources] = React.useState<WikiSourceItem[]>(() => {
    return propSources || getCachedSources() || [];
  });
  const [prevPropSources, setPrevPropSources] = React.useState(propSources);
  if (propSources && propSources !== prevPropSources) {
    setPrevPropSources(propSources);
    setInternalSources(propSources);
  }

  // Fetch only if neither props nor cache provided data
  React.useEffect(() => {
    if (!propPages && internalPages.length === 0) {
      api<WikiPageSummary[]>("/api/wiki/pages")
        .then((data) => {
          const list = Array.isArray(data) ? data : [];
          setInternalPages(list);
          setCachedPages("/api/wiki/pages", list);
        })
        .catch(() => {});
    }
  }, [propPages, internalPages.length]);

  React.useEffect(() => {
    if (!propSources && internalSources.length === 0) {
      api<{ items: WikiSourceItem[] }>("/api/sources?status=ready&page_size=1000")
        .then((data) => {
          const items = data.items || [];
          setInternalSources(items);
          setCachedSources(items);
        })
        .catch(() => {});
    }
  }, [propSources, internalSources.length]);

  const sourceStats = React.useMemo(() => {
    return computeSourceStats(internalPages, internalSources);
  }, [internalPages, internalSources]);

  const selectedDoc = React.useMemo(() => {
    if (!selectedSourceId) return null;
    if (selectedSourceId === "other") {
      return { id: "other", title: "Khác / Chưa phân loại", count: sourceStats.otherCount };
    }
    return sourceStats.sources.find((s) => s.id === selectedSourceId) || null;
  }, [selectedSourceId, sourceStats]);

  const isFiltered = Boolean(selectedSourceId || categoryFilter !== "all");

  return (
    <div
      className={cn(
        "sticky top-0 z-10 bg-background/95 backdrop-blur-sm border-b border-border px-4 py-2 flex flex-wrap items-center justify-between gap-3 text-xs shadow-2xs transition-all",
        className
      )}
    >
      {/* Left: Document Selector Dropdown */}
      <div className="flex items-center gap-2 min-w-0">
        <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider hidden sm:inline-block shrink-0">
          Văn bản:
        </span>
        <DropdownMenu>
          <DropdownMenuTrigger
            className={cn(
              "flex items-center gap-2 h-8 px-3 rounded-lg border text-xs font-medium transition-all cursor-pointer outline-none shadow-xs max-w-[280px] sm:max-w-[380px] md:max-w-[440px]",
              selectedDoc
                ? "bg-primary/10 border-primary/30 text-primary hover:bg-primary/15"
                : "bg-card border-border hover:bg-accent/60 text-foreground"
            )}
          >
            <span className="material-symbols-outlined text-[16px] shrink-0 text-primary">
              {selectedDoc ? "description" : "folder_open"}
            </span>
            <span className="truncate" title={selectedDoc ? selectedDoc.title : "Tất cả văn bản"}>
              {selectedDoc ? selectedDoc.title : "Tất cả văn bản"}
            </span>
            <span className="text-[10px] opacity-70 tabular-nums shrink-0">
              ({selectedDoc ? selectedDoc.count : sourceStats.totalCount})
            </span>
            <span className="material-symbols-outlined text-[14px] opacity-60 ml-1 shrink-0">
              expand_more
            </span>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            align="start"
            className="w-(--anchor-width) min-w-[280px] max-w-[460px] max-h-[340px] overflow-y-auto"
          >
            <DropdownMenuItem
              onClick={() => setSelectedSourceId(null)}
              className={cn(
                "flex items-center gap-2 text-xs cursor-pointer py-2",
                !selectedSourceId && "bg-accent/70 font-semibold"
              )}
            >
              <span className="material-symbols-outlined text-primary shrink-0" style={{ fontSize: 16 }}>
                folder_open
              </span>
              <span className="flex-1 truncate">Tất cả văn bản</span>
              <span className="text-[11px] text-muted-foreground tabular-nums">
                ({sourceStats.totalCount})
              </span>
              {!selectedSourceId && (
                <span className="material-symbols-outlined text-primary text-sm ml-1 shrink-0">
                  check
                </span>
              )}
            </DropdownMenuItem>

            {sourceStats.sources.length > 0 && <DropdownMenuSeparator />}

            {sourceStats.sources.map((s) => {
              const isSel = selectedSourceId === s.id;
              return (
                <DropdownMenuItem
                  key={s.id}
                  onClick={() => setSelectedSourceId(s.id)}
                  className={cn(
                    "flex items-center gap-2 text-xs cursor-pointer py-1.5",
                    isSel && "bg-accent/70 font-semibold text-primary"
                  )}
                >
                  <span className="material-symbols-outlined text-muted-foreground shrink-0" style={{ fontSize: 15 }}>
                    description
                  </span>
                  <span className="flex-1 truncate" title={s.title}>
                    {s.title}
                  </span>
                  <span className="text-[11px] text-muted-foreground tabular-nums shrink-0">
                    ({s.count})
                  </span>
                  {isSel && (
                    <span className="material-symbols-outlined text-primary text-sm ml-1 shrink-0">
                      check
                    </span>
                  )}
                </DropdownMenuItem>
              );
            })}

            {sourceStats.otherCount > 0 && (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  onClick={() => setSelectedSourceId("other")}
                  className={cn(
                    "flex items-center gap-2 text-xs cursor-pointer py-1.5",
                    selectedSourceId === "other" && "bg-accent/70 font-semibold text-primary"
                  )}
                >
                  <span className="material-symbols-outlined text-muted-foreground shrink-0" style={{ fontSize: 15 }}>
                    folder
                  </span>
                  <span className="flex-1 truncate">Khác / Chưa phân loại</span>
                  <span className="text-[11px] text-muted-foreground tabular-nums shrink-0">
                    ({sourceStats.otherCount})
                  </span>
                  {selectedSourceId === "other" && (
                    <span className="material-symbols-outlined text-primary text-sm ml-1 shrink-0">
                      check
                    </span>
                  )}
                </DropdownMenuItem>
              </>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {/* Middle: Category Segmented Pills */}
      <div className="flex items-center p-0.5 bg-muted/60 border border-border/50 rounded-lg text-xs select-none">
        <button
          type="button"
          onClick={() => setCategoryFilter("all")}
          className={cn(
            "px-3 py-1 rounded-md text-xs font-medium transition-all cursor-pointer",
            categoryFilter === "all"
              ? "bg-background text-foreground font-semibold shadow-xs"
              : "text-muted-foreground hover:text-foreground"
          )}
        >
          Tất cả{" "}
          <span className="text-[10px] opacity-60 tabular-nums">
            ({sourceStats.totalCount})
          </span>
        </button>
        <button
          type="button"
          onClick={() => setCategoryFilter("articles")}
          className={cn(
            "px-3 py-1 rounded-md text-xs font-medium transition-all cursor-pointer flex items-center gap-1",
            categoryFilter === "articles"
              ? "bg-background text-foreground font-semibold shadow-xs"
              : "text-muted-foreground hover:text-foreground"
          )}
        >
          <span>Điều luật / Bài viết</span>
          <span className="text-[10px] opacity-60 tabular-nums">
            ({sourceStats.articlesCount})
          </span>
        </button>
        <button
          type="button"
          onClick={() => setCategoryFilter("overview")}
          className={cn(
            "px-3 py-1 rounded-md text-xs font-medium transition-all cursor-pointer flex items-center gap-1",
            categoryFilter === "overview"
              ? "bg-background text-foreground font-semibold shadow-xs"
              : "text-muted-foreground hover:text-foreground"
          )}
        >
          <span>Tổng quan</span>
          <span className="text-[10px] opacity-60 tabular-nums">
            ({sourceStats.overviewsCount})
          </span>
        </button>
      </div>

      {/* Right: Reset Action & Status Badge */}
      <div className="flex items-center gap-2 ml-auto">
        {isFiltered && (
          <button
            type="button"
            onClick={resetFilters}
            className="flex items-center gap-1 px-2 py-1 rounded-md text-xs text-muted-foreground hover:text-foreground hover:bg-accent/80 transition-colors cursor-pointer"
            title="Đặt lại bộ lọc (Hiển thị tất cả)"
          >
            <span className="material-symbols-outlined" style={{ fontSize: 14 }}>
              close
            </span>
            <span>Bỏ lọc</span>
          </button>
        )}
      </div>
    </div>
  );
}
