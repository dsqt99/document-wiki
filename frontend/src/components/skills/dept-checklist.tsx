"use client";

import { Checkbox } from "@/components/ui/checkbox";
import { cn } from "@/lib/utils";
import { scrollCls } from "./skill-markdown";
import type { Department } from "./types";

/** Bordered, scrollable list of department checkboxes. */
export function DeptChecklist({
  departments,
  selected,
  onChange,
  maxHeight = 200,
  emptyText = "Chưa có phòng ban",
  disabled,
}: {
  departments: Department[];
  selected: string[];
  onChange: (ids: string[]) => void;
  maxHeight?: number;
  emptyText?: string;
  disabled?: boolean;
}) {
  const toggle = (id: string, on: boolean) =>
    onChange(on ? (selected.includes(id) ? selected : [...selected, id]) : selected.filter((x) => x !== id));

  return (
    <div
      className={cn("space-y-0.5 overflow-y-auto rounded-lg border border-border p-2", scrollCls.thin)}
      style={{ maxHeight }}
    >
      {departments.length === 0 ? (
        <p className="px-1 py-1 text-xs italic text-muted-foreground">{emptyText}</p>
      ) : (
        departments.map((d) => (
          <label
            key={d.id}
            className="flex cursor-pointer items-center gap-2 rounded-md px-1.5 py-1 text-sm transition-colors hover:text-primary"
          >
            <Checkbox checked={selected.includes(d.id)} disabled={disabled} onCheckedChange={(on) => toggle(d.id, on)} />
            <span className="truncate">{d.name}</span>
          </label>
        ))
      )}
    </div>
  );
}

export const fieldLabelCls = "text-[11px] font-bold uppercase tracking-wider text-muted-foreground";
