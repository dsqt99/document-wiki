"use client";

import React from "react";
import { cn } from "@/lib/utils";

export type FacetOption = { value: string; label: string; count: number; color?: string };

export const STATUS_LABEL_VI: Record<string, string> = {
  evergreen: "Cốt lõi ổn định",
  mature: "Tương đối đầy đủ",
  developing: "Đang phát triển",
  seed: "Sơ khởi",
};

export const STATUS_ORDER = ["evergreen", "mature", "developing", "seed"];

/** Collapsible checkbox facet ("TRA CỨU NHANH" sidebar). */
export function FacetGroup({
  title,
  options,
  selected,
  onToggle,
  searchable = false,
  searchPlaceholder = "Tìm...",
  defaultOpen = true,
}: {
  title: string;
  options: FacetOption[];
  selected: Set<string>;
  onToggle: (value: string) => void;
  searchable?: boolean;
  searchPlaceholder?: string;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = React.useState(defaultOpen);
  const [q, setQ] = React.useState("");

  const visible = React.useMemo(() => {
    const needle = q.trim().toLowerCase();
    return needle ? options.filter((o) => o.label.toLowerCase().includes(needle)) : options;
  }, [options, q]);

  if (options.length === 0) return null;

  return (
    <div className="border-t border-border first:border-t-0">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between gap-2 py-2.5 text-sm font-semibold text-foreground cursor-pointer"
      >
        <span className="flex items-center gap-1.5">
          {title}
          {selected.size > 0 && (
            <span className="px-1.5 py-px rounded-full text-[10px] font-bold bg-primary/15 text-primary tabular-nums">
              {selected.size}
            </span>
          )}
        </span>
        <span className="material-symbols-outlined text-base text-muted-foreground">
          {open ? "expand_less" : "expand_more"}
        </span>
      </button>
      {open && (
        <div className="pb-3">
          {searchable && options.length > 6 && (
            <div className="relative mb-2">
              <span className="material-symbols-outlined text-sm text-muted-foreground absolute left-2 top-1/2 -translate-y-1/2">
                search
              </span>
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder={searchPlaceholder}
                className="h-7 w-full pl-7 pr-2 text-xs rounded-md border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30 placeholder:text-muted-foreground/60"
              />
            </div>
          )}
          <div className={cn("flex flex-col gap-0.5", searchable && "max-h-56 overflow-y-auto pr-1")}>
            {visible.map((o) => {
              const checked = selected.has(o.value);
              return (
                <label
                  key={o.value}
                  className="flex items-center gap-2 px-1 py-1 rounded-md text-[13px] cursor-pointer hover:bg-muted/60"
                  title={o.label}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => onToggle(o.value)}
                    className="size-3.5 accent-primary shrink-0"
                  />
                  <span
                    className={cn("flex-1 truncate", checked ? "text-foreground font-medium" : "text-foreground/80")}
                    style={o.color ? { color: o.color } : undefined}
                  >
                    {o.label}
                  </span>
                  <span className="text-[11px] text-muted-foreground tabular-nums">{o.count}</span>
                </label>
              );
            })}
            {visible.length === 0 && (
              <p className="text-xs text-muted-foreground px-1 py-1">Không có kết quả</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/** Count values produced by `keysOf` across `items`, sorted by count desc. */
export function countFacet<T>(
  items: T[],
  keysOf: (item: T) => string[],
  labelOf: (key: string) => string,
  order?: string[],
): FacetOption[] {
  const counts = new Map<string, number>();
  for (const it of items) {
    for (const k of new Set(keysOf(it))) counts.set(k, (counts.get(k) ?? 0) + 1);
  }
  const out = Array.from(counts, ([value, count]) => ({ value, label: labelOf(value), count }));
  if (order) {
    out.sort((a, b) => order.indexOf(a.value) - order.indexOf(b.value));
  } else {
    out.sort((a, b) => b.count - a.count || a.label.localeCompare(b.label, "vi"));
  }
  return out;
}
