"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";

export type ScopeMode = "global" | "department" | "personal";

type ScopePickerProps = {
  mode: ScopeMode;
  onModeChange: (mode: ScopeMode) => void;
  departments: { id: string; name: string }[];
  selected: string[];
  onSelectedChange: (ids: string[]) => void;
  disabled?: boolean;
  allowPersonal?: boolean;
};

const OPTIONS: { value: ScopeMode; icon: string; label: string; hint: string }[] = [
  { value: "personal", icon: "person", label: "Cá nhân", hint: "Chỉ mình bạn xem được" },
  { value: "department", icon: "apartment", label: "Theo phòng ban", hint: "Chỉ các phòng ban được chọn xem được" },
  { value: "global", icon: "public", label: "Toàn hệ thống", hint: "Mọi cán bộ đều xem được" },
];

/** Visibility picker: segmented radio group plus a filterable department checklist. */
export function ScopePicker({
  mode,
  onModeChange,
  departments,
  selected,
  onSelectedChange,
  disabled,
  allowPersonal = false,
}: ScopePickerProps) {
  const [filter, setFilter] = useState("");
  const options = OPTIONS.filter((o) => allowPersonal || o.value !== "personal");
  const current = OPTIONS.find((o) => o.value === mode);

  const pick = (next: ScopeMode) => {
    if (disabled) return;
    if (next !== "department") onSelectedChange([]);
    onModeChange(next);
  };

  const toggle = (id: string, checked: boolean) => {
    if (checked) onSelectedChange(selected.includes(id) ? selected : [...selected, id]);
    else onSelectedChange(selected.filter((x) => x !== id));
  };

  const needle = filter.trim().toLowerCase();
  const visible = needle ? departments.filter((d) => d.name.toLowerCase().includes(needle)) : departments;

  return (
    <div className="flex flex-col gap-2">
      <div role="radiogroup" className="flex gap-1 rounded-lg bg-muted p-1">
        {options.map((o) => {
          const active = o.value === mode;
          return (
            <button
              key={o.value}
              type="button"
              role="radio"
              aria-checked={active}
              title={o.hint}
              disabled={disabled}
              onClick={() => pick(o.value)}
              className={cn(
                "flex flex-1 items-center justify-center gap-1.5 rounded-md px-2 py-1.5 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
                active
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
                {o.icon}
              </span>
              {o.label}
            </button>
          );
        })}
      </div>
      {current && <p className="text-[11px] text-muted-foreground">{current.hint}</p>}

      {mode === "department" && (
        <div className={cn("rounded-lg border", disabled && "opacity-60")}>
          <div className="flex items-center gap-2 border-b px-2.5 py-1.5">
            <span className="material-symbols-outlined text-muted-foreground" style={{ fontSize: 16 }}>
              search
            </span>
            <input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Tìm phòng ban..."
              disabled={disabled}
              className="h-6 min-w-0 flex-1 bg-transparent text-xs outline-none placeholder:text-muted-foreground"
            />
            <span className="shrink-0 text-[11px] text-muted-foreground tabular-nums">
              Đã chọn {selected.length}/{departments.length}
            </span>
          </div>
          <div className="max-h-40 overflow-y-auto p-1">
            {departments.length === 0 ? (
              <p className="px-2 py-3 text-center text-xs text-muted-foreground">Chưa có phòng ban</p>
            ) : visible.length === 0 ? (
              <p className="px-2 py-3 text-center text-xs text-muted-foreground">Không tìm thấy phòng ban</p>
            ) : (
              visible.map((d) => (
                <label
                  key={d.id}
                  className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-xs hover:bg-muted"
                >
                  <input
                    type="checkbox"
                    className="size-3.5 accent-primary"
                    checked={selected.includes(d.id)}
                    disabled={disabled}
                    onChange={(e) => toggle(d.id, e.target.checked)}
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
