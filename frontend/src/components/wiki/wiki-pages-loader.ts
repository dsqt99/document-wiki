// Shared loader for the full wiki page list, backed by the wiki-store cache.

import { api } from "@/lib/api";
import { getCachedPages, setCachedPages } from "@/lib/wiki-store";
import type { WikiPageSummary } from "@/types/wiki";

export const WIKI_PAGES_URL = "/api/wiki/pages";

const inflight = new Map<string, Promise<WikiPageSummary[]>>();

/**
 * Return the cached page list for `url`, or fetch it once (concurrent callers share the
 * request) and cache it. Non-array responses become an empty list; errors propagate.
 */
export function loadWikiPages(url: string = WIKI_PAGES_URL, opts: { force?: boolean } = {}): Promise<WikiPageSummary[]> {
  if (!opts.force) {
    const cached = getCachedPages(url);
    if (cached) return Promise.resolve(cached);
  }
  const pending = inflight.get(url);
  if (pending) return pending;
  const p = api<WikiPageSummary[]>(url)
    .then((res) => {
      const list = Array.isArray(res) ? res : [];
      setCachedPages(url, list);
      return list;
    })
    .finally(() => inflight.delete(url));
  inflight.set(url, p);
  return p;
}

/** Fallback title for a slug: last path segment with hyphens turned into spaces. */
export function slugToTitle(slug: string): string {
  const last = slug.split("/").filter(Boolean).pop() ?? slug;
  return last.replace(/-/g, " ");
}

/** Encode each "/"-separated segment of a slug for use in a URL path. */
export function encodeSlugPath(slug: string): string {
  return slug.split("/").map(encodeURIComponent).join("/");
}
