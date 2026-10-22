const DEFAULT_LIBRARY_RETURN_TO = "/wiki/law?view=wiki";

/** Only the exact local library route is an allowed return destination. */
export function sanitizeWikiLibraryReturnTo(value: string | null | undefined): string {
  if (!value || !["/knowledge", "/wiki/law"].includes(value.split(/[?#]/, 1)[0]) || /[\\\u0000-\u001f\u007f]/.test(value)) {
    return DEFAULT_LIBRARY_RETURN_TO;
  }
  try {
    const url = new URL(value, "https://wiki.local");
    if (url.origin !== "https://wiki.local" || !["/knowledge", "/wiki/law"].includes(url.pathname)) return DEFAULT_LIBRARY_RETURN_TO;
    url.pathname = "/wiki/law";
    url.searchParams.delete("tab");
    url.searchParams.delete("wiki_status");
    url.searchParams.set("view", "wiki");
    return `${url.pathname}?${url.searchParams}${url.hash}`;
  } catch {
    return DEFAULT_LIBRARY_RETURN_TO;
  }
}

/** Carry the same library context through page links, editor links and scope changes. */
export function wikiPageQuery(
  scopeType: string | null | undefined,
  scopeId: string | null | undefined,
  returnTo: string | null | undefined,
  edit = false,
): string {
  const params = new URLSearchParams();
  if (scopeType && scopeType !== "global") {
    params.set("scopeType", scopeType);
    if (scopeId) params.set("scopeId", scopeId);
  }
  params.set("returnTo", sanitizeWikiLibraryReturnTo(returnTo));
  if (edit) params.set("edit", "1");
  return `?${params}`;
}
