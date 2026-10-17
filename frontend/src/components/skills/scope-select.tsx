"use client";

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export type GlobalOrDept = "global" | "department";

type Labels = {
  /** Text shown in the closed trigger. */
  global: string;
  department: string;
  /** Text of the options in the popup (defaults to the trigger text). */
  globalItem?: string;
  departmentItem?: string;
};

/** Two-way visibility select (whole system vs. some departments), 44px tall. */
export function ScopeSelect({
  value,
  onChange,
  labels,
  disabled,
  id,
}: {
  value: GlobalOrDept;
  onChange: (v: GlobalOrDept) => void;
  labels: Labels;
  disabled?: boolean;
  id?: string;
}) {
  return (
    <Select
      value={value}
      onValueChange={(v) => {
        if (v === "global" || v === "department") onChange(v);
      }}
      disabled={disabled}
    >
      <SelectTrigger id={id} className="h-11! w-full">
        <SelectValue>
          {(v: string | null) => (
            <span className="flex items-center gap-2">
              <span className="material-symbols-outlined text-muted-foreground" style={{ fontSize: 18 }}>
                {v === "department" ? "corporate_fare" : "public"}
              </span>
              {v === "department" ? labels.department : labels.global}
            </span>
          )}
        </SelectValue>
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="global">
          <span className="material-symbols-outlined" style={{ fontSize: 18 }}>public</span>
          {labels.globalItem ?? labels.global}
        </SelectItem>
        <SelectItem value="department">
          <span className="material-symbols-outlined" style={{ fontSize: 18 }}>corporate_fare</span>
          {labels.departmentItem ?? labels.department}
        </SelectItem>
      </SelectContent>
    </Select>
  );
}
