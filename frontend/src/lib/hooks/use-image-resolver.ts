"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export type ImageResolverState = {
  /** uuid -> signed image URL */
  resolved: Record<string, string>;
  denied: Set<string>;
  loading: boolean;
};

const EMPTY: ImageResolverState = { resolved: {}, denied: new Set(), loading: false };

/**
 * Resolve wiki image ids to signed URLs. Re-runs only when the de-duplicated, sorted id
 * list changes (not on every new array reference); stale responses are dropped.
 */
export function useImageResolver(ids: string[]): ImageResolverState {
  const key = [...new Set(ids)].sort().join("\n");
  const [state, setState] = useState<{ key: string; value: ImageResolverState }>({ key: "", value: EMPTY });

  useEffect(() => {
    if (!key) return;
    let cancelled = false;
    const list = key.split("\n");
    const start = setTimeout(() => {
      if (!cancelled) setState({ key, value: { resolved: {}, denied: new Set(), loading: true } });
    }, 0);
    api<{ resolved?: Record<string, string>; denied?: string[] }>("/api/wiki/images/resolve", {
      method: "POST",
      body: { ids: list },
    })
      .then((res) => {
        if (cancelled) return;
        setState({
          key,
          value: { resolved: res.resolved ?? {}, denied: new Set(res.denied ?? []), loading: false },
        });
      })
      .catch(() => {
        if (cancelled) return;
        setState({ key, value: EMPTY });
      });
    return () => {
      cancelled = true;
      clearTimeout(start);
    };
  }, [key]);

  if (!key) return EMPTY;
  // Before the effect for a new key has reported anything, treat it as loading.
  if (state.key !== key) return { resolved: {}, denied: new Set(), loading: true };
  return state.value;
}
