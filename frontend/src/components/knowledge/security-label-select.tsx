"use client";

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useAuth } from "@/lib/auth";
import { selectableSecurityLabels } from "@/lib/security-label";

export type SecurityLabel = "PUBLIC" | "INTERNAL" | "RESTRICTED" | "CONFIDENTIAL";

export const DEFAULT_LABEL: SecurityLabel = "INTERNAL";

/** Same four levels and Vietnamese names as the chatbot upload form. */
export const LABELS: { value: SecurityLabel; label: string; hint: string }[] = [
  { value: "PUBLIC", label: "Công khai", hint: "Mọi cán bộ trong phạm vi đều xem được" },
  { value: "INTERNAL", label: "Nội bộ", hint: "Cần mức tiếp cận Nội bộ trở lên" },
  { value: "RESTRICTED", label: "Hạn chế", hint: "Cần mức tiếp cận Hạn chế trở lên" },
  { value: "CONFIDENTIAL", label: "Mật", hint: "Chỉ cán bộ có mức tiếp cận Mật" },
];

const RANK: Record<string, number> = { PUBLIC: 0, INTERNAL: 1, RESTRICTED: 2, CONFIDENTIAL: 3 };

export function normalizeLabel(value?: string | null): SecurityLabel {
  const v = (value ?? "").trim().toUpperCase();
  return v in RANK ? (v as SecurityLabel) : DEFAULT_LABEL;
}

type Props = {
  value: SecurityLabel;
  onChange: (value: SecurityLabel) => void;
  disabled?: boolean;
};

/** Document sensitivity; non-admins cannot pick above their own clearance (the API enforces it too). */
export function SecurityLabelSelect({ value, onChange, disabled }: Props) {
  const { user } = useAuth();
  const allowed = selectableSecurityLabels(user);
  const options = LABELS.filter((o) => allowed.includes(o.value));
  const current = LABELS.find((o) => o.value === value);

  return (
    <div className="flex flex-col gap-2">
      <Select value={value} onValueChange={(v) => v && onChange(v as SecurityLabel)} disabled={disabled}>
        <SelectTrigger className="h-9 w-full text-sm">
          <SelectValue>
            {() => (
              <span className="flex min-w-0 items-center gap-2">
                <span className="material-symbols-outlined shrink-0 text-muted-foreground" style={{ fontSize: 16 }}>
                  shield_lock
                </span>
                <span className="truncate">{current?.label ?? value}</span>
              </span>
            )}
          </SelectValue>
        </SelectTrigger>
        <SelectContent>
          {options.map((o) => (
            <SelectItem key={o.value} value={o.value}>
              {o.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {current && <p className="text-[11px] text-muted-foreground">{current.hint}</p>}
    </div>
  );
}
