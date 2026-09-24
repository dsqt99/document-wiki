import React from "react";
import { WikiPageDetail, WikiPageSummary } from "@/types/wiki";

export type WikiSourceItem = {
  id: string;
  title: string;
  file_name?: string;
  status: string;
  source_type?: string;
};

interface WikiStoreState {
  // UI State
  selectedSourceId: string | null;
  categoryFilter: "all" | "articles" | "overview";
  groupByDocument: boolean;
  expandedDocuments: Set<string>;
  expandedScopes: Set<string>;
  search: string;
  sidebarScrollTop: number;

  // Data Cache
  pagesCache: Map<string, WikiPageSummary[]>;
  sourcesCache: WikiSourceItem[] | null;
  pageDetailCache: Map<string, WikiPageDetail>;
  sourceDataCache: Map<string, Record<string, unknown>>;
}

// In-memory persistent state across client-side navigations and component remounts
export const wikiStore: WikiStoreState = {
  selectedSourceId: null,
  categoryFilter: "all",
  groupByDocument: true,
  expandedDocuments: new Set<string>(),
  expandedScopes: new Set<string>(["global"]),
  search: "",
  sidebarScrollTop: 0,

  pagesCache: new Map(),
  sourcesCache: null,
  pageDetailCache: new Map(),
  sourceDataCache: new Map(),
};

// Listeners for UI state changes
type Listener = () => void;
const listeners = new Set<Listener>();

export function subscribeWikiStore(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function notifyWikiStore() {
  for (const l of listeners) {
    try {
      l();
    } catch (e) {
      console.error(e);
    }
  }
}

/** Hook for components to subscribe and update wikiStore state */
export function useWikiStore() {
  const [, forceUpdate] = React.useReducer((x) => x + 1, 0);

  React.useEffect(() => {
    return subscribeWikiStore(() => {
      forceUpdate();
    });
  }, []);

  const setSelectedSourceId = React.useCallback((id: string | null) => {
    wikiStore.selectedSourceId = id;
    notifyWikiStore();
  }, []);

  const setCategoryFilter = React.useCallback((cat: "all" | "articles" | "overview") => {
    wikiStore.categoryFilter = cat;
    notifyWikiStore();
  }, []);

  const setGroupByDocument = React.useCallback((val: boolean | ((prev: boolean) => boolean)) => {
    const next = typeof val === "function" ? val(wikiStore.groupByDocument) : val;
    wikiStore.groupByDocument = next;
    notifyWikiStore();
  }, []);

  const setSearch = React.useCallback((val: string) => {
    wikiStore.search = val;
    notifyWikiStore();
  }, []);

  const setExpandedDocuments = React.useCallback((val: Set<string> | ((prev: Set<string>) => Set<string>)) => {
    const next = typeof val === "function" ? val(wikiStore.expandedDocuments) : val;
    wikiStore.expandedDocuments = new Set(next);
    notifyWikiStore();
  }, []);

  const setExpandedScopes = React.useCallback((val: Set<string> | ((prev: Set<string>) => Set<string>)) => {
    const next = typeof val === "function" ? val(wikiStore.expandedScopes) : val;
    wikiStore.expandedScopes = new Set(next);
    notifyWikiStore();
  }, []);

  const resetFilters = React.useCallback(() => {
    wikiStore.selectedSourceId = null;
    wikiStore.categoryFilter = "all";
    wikiStore.search = "";
    notifyWikiStore();
  }, []);

  return {
    selectedSourceId: wikiStore.selectedSourceId,
    categoryFilter: wikiStore.categoryFilter,
    groupByDocument: wikiStore.groupByDocument,
    search: wikiStore.search,
    expandedDocuments: wikiStore.expandedDocuments,
    expandedScopes: wikiStore.expandedScopes,
    sidebarScrollTop: wikiStore.sidebarScrollTop,
    setSelectedSourceId,
    setCategoryFilter,
    setGroupByDocument,
    setSearch,
    setExpandedDocuments,
    setExpandedScopes,
    resetFilters,
  };
}

/** Maps a page to its corresponding source document (if any) */
export function getDocForPage(p: WikiPageSummary, sources: WikiSourceItem[]): WikiSourceItem | null {
  if (!sources || sources.length === 0) return null;
  // 1. Check explicit source_ids
  if (p.source_ids && p.source_ids.length > 0) {
    for (const sid of p.source_ids) {
      const src = sources.find((s) => s.id === sid);
      if (src) return src;
    }
  }
  // 2. Check title suffix: " - [Doc Title]"
  for (const src of sources) {
    const srcTitle = src.title || src.file_name;
    if (srcTitle && p.title.endsWith(` - ${srcTitle}`)) {
      return src;
    }
    if (srcTitle && (p.title === srcTitle || p.slug === src.id)) {
      return src;
    }
  }
  return null;
}

export interface ComputedSourceStats {
  sources: Array<{ id: string; title: string; count: number }>;
  otherCount: number;
  articlesCount: number;
  overviewsCount: number;
  totalCount: number;
}

export function computeSourceStats(
  pages: WikiPageSummary[],
  sources: WikiSourceItem[]
): ComputedSourceStats {
  const counts = new Map<string, number>();
  let otherCount = 0;
  let articlesCount = 0;
  let overviewsCount = 0;

  for (const p of pages) {
    if (p.page_type === "index" || p.page_type === "log" || p.page_type === "hot") continue;
    if (p.title.startsWith("Điều ")) {
      articlesCount++;
    } else {
      overviewsCount++;
    }

    const doc = getDocForPage(p, sources);
    if (doc) {
      counts.set(doc.id, (counts.get(doc.id) || 0) + 1);
    } else {
      otherCount++;
    }
  }

  return {
    sources: sources.map((s) => ({
      id: s.id,
      title: s.title || s.file_name || "Untitled",
      count: counts.get(s.id) || 0,
    })),
    otherCount,
    articlesCount,
    overviewsCount,
    totalCount: pages.filter(
      (p) => p.page_type !== "index" && p.page_type !== "log" && p.page_type !== "hot"
    ).length,
  };
}

// Helper methods for pages cache
export function getCachedPages(url: string): WikiPageSummary[] | null {
  return wikiStore.pagesCache.get(url) || null;
}

export function setCachedPages(url: string, pages: WikiPageSummary[]) {
  wikiStore.pagesCache.set(url, pages);
}

export function removeCachedPage(slug: string) {
  for (const [url, list] of wikiStore.pagesCache.entries()) {
    wikiStore.pagesCache.set(
      url,
      list.filter((p) => p.slug !== slug)
    );
  }
  wikiStore.pageDetailCache.delete(slug);
}

// Helper methods for sources cache
export function getCachedSources(): WikiSourceItem[] | null {
  return wikiStore.sourcesCache;
}

export function setCachedSources(sources: WikiSourceItem[]) {
  wikiStore.sourcesCache = sources;
}

// Helper methods for page detail cache
export function getCachedPageDetail(key: string): WikiPageDetail | null {
  return wikiStore.pageDetailCache.get(key) || null;
}

export function setCachedPageDetail(key: string, page: WikiPageDetail) {
  wikiStore.pageDetailCache.set(key, page);
}

// Helper methods for source detail cache
export function getCachedSourceData(id: string): Record<string, unknown> | null {
  return wikiStore.sourceDataCache.get(id) || null;
}

export function setCachedSourceData(id: string, data: Record<string, unknown>) {
  wikiStore.sourceDataCache.set(id, data);
}


