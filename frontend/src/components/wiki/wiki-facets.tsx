"use client";

import { useMemo, useState } from "react";
import { cn } from "@/lib/utils";

export type FacetOption = {
  value: string;
  label: string;
  count: number;
  color?: string;
};

export const STATUS_LABEL_VI: Record<string, string> = {
  evergreen: "Cốt lõi ổn định",
  mature: "Tương đối đầy đủ",
  developing: "Đang phát triển",
  seed: "Sơ khởi",
};

export const STATUS_ORDER: string[] = ["evergreen", "mature", "developing", "seed"];

type FacetGroupProps = {
  title: string;
  options: FacetOption[];
  selected: Set<string>;
  onToggle: (value: string) => void;
  searchable?: boolean;
  searchPlaceholder?: string;
  defaultOpen?: boolean;
};

/** Collapsible checkbox facet used in the wiki / legal document filter rails. */
export function FacetGroup({
  title,
  options,
  selected,
  onToggle,
  searchable = false,
  searchPlaceholder = "Tìm...",
  defaultOpen = true,
}: FacetGroupProps) {
  const [open, setOpen] = useState(defaultOpen);
  const [query, setQuery] = useState("");

  const showSearch = searchable && options.length > 6;
  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!showSearch || !q) return options;
    return options.filter((o) => o.label.toLowerCase().includes(q));
  }, [options, query, showSearch]);

  if (options.length === 0) return null;

  const selectedCount = options.filter((o) => selected.has(o.value)).length;

  return (
    <section className="py-2 [&+&]:border-t">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 py-2.5 text-left text-sm leading-5 font-semibold"
      >
        <span>{title}</span>
        {selectedCount > 0 && (
          <span className="rounded-full bg-primary/10 px-1.5 text-[10px] leading-4 font-semibold text-primary">
            {selectedCount}
          </span>
        )}
        <span className="material-symbols-outlined ml-auto text-muted-foreground" style={{ fontSize: 18 }}>
          {open ? "expand_less" : "expand_more"}
        </span>
      </button>
      {open && (
        <div className="mt-1">
          {showSearch && (
            <div className="relative mb-1.5">
              <span
                className="material-symbols-outlined pointer-events-none absolute top-1/2 left-2 -translate-y-1/2 text-muted-foreground"
                style={{ fontSize: 14 }}
              >
                search
              </span>
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={searchPlaceholder}
                className="h-7 w-full rounded-md border bg-background pr-2 pl-7 text-xs outline-none focus:ring-2 focus:ring-primary/30"
              />
            </div>
          )}
          <div className={cn(searchable && "max-h-60 overflow-y-auto")}>
            {visible.map((opt) => {
              const checked = selected.has(opt.value);
              return (
                <label
                  key={opt.value}
                  title={opt.label}
                  className="flex cursor-pointer items-center gap-2 rounded-md px-1 py-[5px] text-[13px] hover:bg-muted"
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => onToggle(opt.value)}
                    className="size-3.5 shrink-0 accent-primary"
                  />
                  <span
                    className={cn("min-w-0 flex-1 truncate", checked && "font-medium")}
                    style={opt.color ? { color: opt.color } : undefined}
                  >
                    {opt.label}
                  </span>
                  <span className="shrink-0 text-[11px] text-muted-foreground tabular-nums">{opt.count}</span>
                </label>
              );
            })}
            {showSearch && query.trim() && visible.length === 0 && (
              <p className="px-1 py-1 text-xs text-muted-foreground">Không có kết quả</p>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

/**
 * Tally how many items carry each key. Keys are de-duplicated per item.
 * With `order`, options follow that order (unknown values first); otherwise by count desc, then label.
 */
export function countFacet<T>(
  items: T[],
  keysOf: (item: T) => string[],
  labelOf: (value: string) => string,
  order?: string[],
): FacetOption[] {
  const counts = new Map<string, number>();
  for (const item of items) {
    for (const key of new Set(keysOf(item))) {
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
  }
  const options: FacetOption[] = [...counts.entries()].map(([value, count]) => ({
    value,
    label: labelOf(value),
    count,
  }));
  if (order) {
    options.sort((a, b) => order.indexOf(a.value) - order.indexOf(b.value));
  } else {
    options.sort((a, b) => b.count - a.count || a.label.localeCompare(b.label, "vi"));
  }
  return options;
}
