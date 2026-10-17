"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { CaretCoords } from "@/lib/textarea-caret";
import type { WikiPageSummary } from "@/types/wiki";
import { wikiTypeColor, wikiTypeIcon } from "@/components/wiki/wiki-type-badge";
import { cn } from "@/lib/utils";

const WIDTH = 340;
const MAX_HEIGHT = 280;
const LIMIT = 8;

type Props = {
  pages: WikiPageSummary[];
  query: string;
  caret: CaretCoords;
  onPick: (page: WikiPageSummary) => void;
  onClose: () => void;
};

function score(field: string, q: string): number {
  const f = field.toLowerCase();
  if (f === q) return 100;
  if (f.startsWith(q)) return 50;
  if (f.includes(q)) return 20;
  return 0;
}

export function WikilinkAutocomplete({ pages, query, caret, onPick, onClose }: Props) {
  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return pages.slice(0, LIMIT);
    return pages
      .map((p) => ({ p, s: Math.max(score(p.slug, q), score(p.title ?? "", q)) }))
      .filter((x) => x.s > 0)
      .sort((a, b) => b.s - a.s)
      .slice(0, LIMIT)
      .map((x) => x.p);
  }, [pages, query]);

  const [activeState, setActive] = useState<{ query: string; index: number }>({ query, index: 0 });
  // Reset the highlighted row whenever the query changes.
  const active = activeState.query === query ? Math.min(activeState.index, Math.max(0, results.length - 1)) : 0;

  const latest = useRef({ results, active, onPick, onClose, query });
  useEffect(() => {
    latest.current = { results, active, onPick, onClose, query };
  });

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const { results: list, active: idx, onPick: pick, onClose: close, query: q } = latest.current;
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        e.stopPropagation();
        if (list.length === 0) return;
        const delta = e.key === "ArrowDown" ? 1 : -1;
        setActive({ query: q, index: (idx + delta + list.length) % list.length });
      } else if (e.key === "Enter" || e.key === "Tab") {
        if (list.length === 0) return;
        e.preventDefault();
        e.stopPropagation();
        pick(list[idx]);
      } else if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        close();
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, []);

  if (typeof document === "undefined") return null;

  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const below = caret.top + caret.lineHeight + 4;
  const top = below + MAX_HEIGHT > vh - 16 ? Math.max(8, caret.top - MAX_HEIGHT - 4) : below;
  const left = Math.max(8, Math.min(caret.left, vw - WIDTH - 16));

  return createPortal(
    <div
      role="listbox"
      onMouseDown={(e) => e.preventDefault()}
      className="flex flex-col overflow-hidden rounded-lg border bg-popover text-popover-foreground shadow-lg"
      style={{ position: "fixed", top, left, width: WIDTH, maxHeight: MAX_HEIGHT, zIndex: 100 }}
    >
      <div className="flex items-center justify-between border-b px-3 py-1.5 text-[11px] text-muted-foreground">
        <span className="font-medium">Link to page</span>
        <span>↑↓ Enter</span>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto py-1">
        {results.length === 0 ? (
          <div className="px-3 py-3 text-xs text-muted-foreground">No pages match “{query}”.</div>
        ) : (
          results.map((p, i) => {
            const nonGlobal = p.scope_type && p.scope_type !== "global";
            return (
              <button
                key={`${p.slug}:${p.scope_type ?? ""}:${p.scope_id ?? ""}`}
                type="button"
                role="option"
                aria-selected={i === active}
                onMouseEnter={() => setActive({ query, index: i })}
                onClick={() => onPick(p)}
                className={cn(
                  "flex w-full items-start gap-2 px-3 py-1.5 text-left",
                  i === active && "bg-primary/10",
                )}
              >
                <span
                  className="material-symbols-outlined mt-0.5 shrink-0"
                  style={{ fontSize: 16, color: wikiTypeColor(p.page_type) }}
                >
                  {wikiTypeIcon(p.page_type)}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm">{p.title || p.slug}</span>
                  <span className="block truncate font-mono text-[11px] text-muted-foreground">
                    {p.slug}
                    {nonGlobal && p.scope_name ? ` · ${p.scope_name}` : ""}
                  </span>
                </span>
              </button>
            );
          })
        )}
      </div>
    </div>,
    document.body,
  );
}
