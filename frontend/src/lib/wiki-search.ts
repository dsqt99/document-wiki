import type { WikiPageSummary } from "@/types/wiki";

export type WikiSearchMeta = {
  mode: "rerank" | "hybrid" | "hybrid_fallback";
  warning?: string | null;
  threshold?: number | null;
  candidate_limit: number;
  candidate_count: number;
};

export type WikiLibraryResponse = {
  items: WikiPageSummary[]; total: number; limit: number; offset: number; search?: WikiSearchMeta;
};
