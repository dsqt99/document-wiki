"use client";

import React from "react";
import { cn } from "@/lib/utils";

export type ScopeMode = "global" | "department";

type Department = { id: string; name: string };

const OPTIONS: { value: ScopeMode; icon: string; title: string; hint: string }[] = [
  { value: "global", icon: "public", title: "Toàn hệ thống", hint: "Mọi cán bộ đều xem được" },
  { value: "department", icon: "apartment", title: "Theo phòng ban", hint: "Chỉ các phòng ban được chọn" },
];

/** Visibility selector shared by the upload and edit dialogs. */
export function ScopePicker({
  mode,
  onModeChange,
  departments,
  selected,
  onSelectedChange,
  disabled,
}: {
  mode: ScopeMode;
  onModeChange: (m: ScopeMode) => void;
  departments: Department[];
  selected: string[];
  onSelectedChange: (ids: string[]) => void;
  disabled?: boolean;
}) {
  const [query, setQuery] = React.useState("");
  const q = query.trim().toLowerCase();
  const shown = q ? departments.filter((d) => d.name.toLowerCase().includes(q)) : departments;
  const toggle = (id: string) =>
    onSelectedChange(selected.includes(id) ? selected.filter((d) => d !== id) : [...selected, id]);

  return (
    <div className="flex flex-col gap-2">
      <div className="grid grid-cols-2 gap-2" role="radiogroup">
        {OPTIONS.map((o) => {
          const active = mode === o.value;
          return (
            <button
              key={o.value}
              type="button"
              role="radio"
              aria-checked={active}
              disabled={disabled}
              onClick={() => {
                onModeChange(o.value);
                if (o.value === "global") onSelectedChange([]);
              }}
              className={cn(
                "flex items-start gap-2.5 rounded-lg border px-3 py-2.5 text-left transition-colors cursor-pointer disabled:cursor-not-allowed disabled:opacity-60",
                active
                  ? "border-primary bg-primary/5 ring-1 ring-primary/30"
                  : "border-border bg-background hover:bg-muted/50",
              )}
            >
              <span
                className={cn("material-symbols-outlined mt-px", active ? "text-primary" : "text-muted-foreground")}
                style={{ fontSize: 18 }}
              >
                {o.icon}
              </span>
              <span className="min-w-0">
                <span className="block text-sm font-medium text-foreground">{o.title}</span>
                <span className="block text-[11px] text-muted-foreground">{o.hint}</span>
              </span>
            </button>
          );
        })}
      </div>

      {mode === "department" && (
        <div className="rounded-lg border border-border bg-background">
          <div className="flex items-center gap-2 border-b border-border px-2.5">
            <span className="material-symbols-outlined text-muted-foreground" style={{ fontSize: 16 }}>search</span>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Tìm phòng ban..."
              className="h-8 flex-1 bg-transparent text-xs focus:outline-none"
            />
            <span className="text-[11px] text-muted-foreground tabular-nums shrink-0">
              Đã chọn {selected.length}/{departments.length}
            </span>
          </div>
          <div className="max-h-40 overflow-y-auto p-1">
            {shown.length === 0 ? (
              <p className="px-2 py-3 text-center text-xs text-muted-foreground">
                {departments.length === 0 ? "Chưa có phòng ban" : "Không tìm thấy phòng ban"}
              </p>
            ) : (
              shown.map((d) => (
                <label
                  key={d.id}
                  className="flex items-center gap-2 rounded px-2 py-1.5 text-xs hover:bg-muted/60 cursor-pointer"
                >
                  <input
                    type="checkbox"
                    checked={selected.includes(d.id)}
                    onChange={() => toggle(d.id)}
                    disabled={disabled}
                    className="rounded border-border accent-[var(--primary)]"
                  />
                  <span className="truncate">{d.name}</span>
                </label>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
