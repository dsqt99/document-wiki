"use client";

import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { useRouter } from "next/navigation";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { wikiTypeColor, wikiTypeGroupLabel, wikiTypeIcon } from "@/components/wiki/wiki-type-badge";
import { encodeSlugPath, loadWikiPages, WIKI_PAGES_URL } from "@/components/wiki/wiki-pages-loader";
import { useI18n } from "@/lib/i18n";
import { getCachedPages } from "@/lib/wiki-store";
import { cn } from "@/lib/utils";
import type { WikiPageSummary } from "@/types/wiki";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSelectPage?: (slug: string) => void;
};

const MAX_RESULTS = 60;
const TYPE_ORDER = ["entity", "concept", "topic", "source"];

export function WikiSearchDialog({ open, onOpenChange, onSelectPage }: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent showCloseButton={false} className="gap-0 overflow-hidden p-0 sm:max-w-2xl">
        {/* Mounted only while open: closing discards the query. */}
        {open && <SearchBody onOpenChange={onOpenChange} onSelectPage={onSelectPage} />}
      </DialogContent>
    </Dialog>
  );
}

function SearchBody({ onOpenChange, onSelectPage }: Omit<Props, "open">) {
  const { t } = useI18n();
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const [pages, setPages] = useState<WikiPageSummary[]>(() => getCachedPages(WIKI_PAGES_URL) ?? []);
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [activeState, setActive] = useState<{ q: string; i: number }>({ q: "", i: 0 });

  useEffect(() => {
    let cancelled = false;
    loadWikiPages()
      .then((list) => {
        if (!cancelled) setPages(list);
      })
      .catch(() => {
        /* the dialog just shows the "no pages" hint */
      });
    const focusTimer = setTimeout(() => inputRef.current?.focus(), 50);
    return () => {
      cancelled = true;
      clearTimeout(focusTimer);
    };
  }, []);

  useEffect(() => {
    const id = setTimeout(() => setDebounced(query), 120);
    return () => clearTimeout(id);
  }, [query]);

  const { flat, groups } = useMemo(() => {
    const q = debounced.trim().toLowerCase();
    const matched = pages
      .filter((p) => p.page_type !== "index" && p.page_type !== "log")
      .filter(
        (p) =>
          !q ||
          (p.title ?? "").toLowerCase().includes(q) ||
          p.slug.toLowerCase().includes(q) ||
          (p.summary ?? "").toLowerCase().includes(q),
      )
      .slice(0, MAX_RESULTS);
    const rank = (type: string) => {
      const i = TYPE_ORDER.indexOf(type);
      return i === -1 ? TYPE_ORDER.length : i;
    };
    const byType = new Map<string, WikiPageSummary[]>();
    for (const p of matched) {
      const list = byType.get(p.page_type) ?? [];
      list.push(p);
      byType.set(p.page_type, list);
    }
    const ordered = [...byType.entries()].sort((a, b) => rank(a[0]) - rank(b[0]));
    return { groups: ordered, flat: ordered.flatMap(([, list]) => list) };
  }, [pages, debounced]);

  const active = activeState.q === debounced ? Math.min(activeState.i, Math.max(0, flat.length - 1)) : 0;

  useEffect(() => {
    listRef.current?.querySelector<HTMLElement>(`[data-idx="${active}"]`)?.scrollIntoView({ block: "nearest" });
  }, [active]);

  const choose = (page: WikiPageSummary) => {
    if (onSelectPage) onSelectPage(page.slug);
    else router.push(`/wiki/${encodeSlugPath(page.slug)}`);
    onOpenChange(false);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (flat.length === 0) return;
      const delta = e.key === "ArrowDown" ? 1 : -1;
      setActive({ q: debounced, i: (active + delta + flat.length) % flat.length });
    } else if (e.key === "Enter") {
      e.preventDefault();
      const hit = flat[active];
      if (hit) choose(hit);
    }
  };

  let rowIndex = -1;

  return (
    <>
      <DialogTitle className="sr-only">{t("wiki.searchDialogPlaceholder", "Search wiki pages")}</DialogTitle>
      <div className="flex items-center gap-2 border-b px-4 py-3">
        <span className="material-symbols-outlined text-muted-foreground" style={{ fontSize: 20 }}>
          search
        </span>
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={t("wiki.searchDialogPlaceholder", "Search wiki pages...")}
          className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
        />
      </div>

      <div ref={listRef} className="max-h-[60vh] overflow-y-auto py-2">
        {flat.length === 0 ? (
          <p className="px-4 py-8 text-center text-sm text-muted-foreground">
            {debounced.trim() ? t("wiki.noSearchMatch") : t("wiki.noSearchYet")}
          </p>
        ) : (
          groups.map(([type, list]) => (
            <div key={type} className="mb-1">
              <div className="flex items-center gap-1.5 px-4 py-1 text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">
                <span className="material-symbols-outlined" style={{ fontSize: 14, color: wikiTypeColor(type) }}>
                  {wikiTypeIcon(type)}
                </span>
                {wikiTypeGroupLabel(type)}
              </div>
              {list.map((p) => {
                rowIndex += 1;
                const idx = rowIndex;
                return (
                  <button
                    key={`${p.slug}:${p.scope_type ?? ""}:${p.scope_id ?? ""}`}
                    type="button"
                    data-idx={idx}
                    onMouseEnter={() => setActive({ q: debounced, i: idx })}
                    onClick={() => choose(p)}
                    className={cn(
                      "flex w-full items-center gap-3 px-4 py-2 text-left",
                      idx === active ? "bg-primary/10" : "hover:bg-muted",
                    )}
                  >
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium">{p.title || p.slug}</span>
                      {p.summary && (
                        <span className="block truncate text-xs text-muted-foreground">{p.summary}</span>
                      )}
                    </span>
                    <span className="max-w-[40%] shrink-0 truncate font-mono text-[11px] text-muted-foreground">
                      {p.slug}
                    </span>
                  </button>
                );
              })}
            </div>
          ))
        )}
      </div>

      <div className="flex items-center gap-4 border-t px-4 py-2 text-[11px] text-muted-foreground">
        <span>
          <kbd className="rounded border px-1 font-mono">↑↓</kbd> {t("wiki.navHint")}
        </span>
        <span>
          <kbd className="rounded border px-1 font-mono">↵</kbd> {t("wiki.selectHint", "chọn")}
        </span>
        <span>
          <kbd className="rounded border px-1 font-mono">Esc</kbd> {t("wiki.closeHint")}
        </span>
        <span className="ml-auto tabular-nums">
          {flat.length} {t("wiki.pagesCount")}
        </span>
      </div>
    </>
  );
}
