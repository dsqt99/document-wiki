"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { type Source, type SourceListResponse } from "./types";

/** Keep only source ids in this tab; metadata is always reloaded with current access checks. */
export function useUploadBatch(userId?: string) {
  const [uploaded, setUploaded] = useState<Source[]>([]);
  const [restoreError, setRestoreError] = useState(false);
  const [restoreTick, setRestoreTick] = useState(0);
  const key = userId ? `wiki-upload-batch:${userId}` : null;
  useEffect(() => {
    if (!key) return;
    let active = true;
    const restore = async () => {
      try {
        const stored: unknown = JSON.parse(sessionStorage.getItem(key) || "[]");
        if (!Array.isArray(stored) || !stored.every((id) => typeof id === "string" && /^[0-9a-f-]{36}$/i.test(id))) return;
        const ids = stored.slice(0, 1000) as string[];
        if (!ids.length) return;
        const sources: Source[] = [];
        for (let i = 0; i < ids.length && active; i += 100) {
          const result = await api<SourceListResponse>(`/api/sources?source_ids=${ids.slice(i, i + 100).join(",")}&page_size=100`);
          sources.push(...result.items);
        }
        if (active) { setUploaded(sources); setRestoreError(false); }
      } catch { if (active) setRestoreError(true); }
    };
    void restore();
    return () => { active = false; };
  }, [key, restoreTick]);
  const showBatch = (sources: Source[], merge = false) => {
    const next = merge ? [...sources, ...uploaded.filter((source) => !sources.some((added) => added.id === source.id))] : sources;
    setUploaded(next);
    setRestoreError(false);
    if (key) {
      try { if (next.length) sessionStorage.setItem(key, JSON.stringify(next.slice(0, 1000).map((source) => source.id))); else sessionStorage.removeItem(key); }
      catch { /* Storage is optional; sources remain available in the server-side document list. */ }
    }
  };
  return { uploaded, showBatch, restoreError, retryRestore: () => setRestoreTick((tick) => tick + 1) };
}
