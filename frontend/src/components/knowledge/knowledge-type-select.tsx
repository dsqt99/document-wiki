"use client";

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import type { KnowledgeType } from "./types";

// base-ui Select treats an empty value as "nothing selected"; use a sentinel for "unclassified".
const NONE = "__none__";
const UNCLASSIFIED = "Chưa phân loại";

function Dot({ color }: { color?: string | null }) {
  return (
    <span
      className="inline-block size-2.5 shrink-0 rounded-full border border-border"
      style={color ? { backgroundColor: color, borderColor: color } : undefined}
    />
  );
}

type Props = {
  types: KnowledgeType[];
  /** Selected type id, "" for unclassified */
  value: string;
  onChange: (id: string) => void;
  disabled?: boolean;
  className?: string;
};

/** Knowledge type picker with a colour dot per entry; "" means unclassified. */
export function KnowledgeTypeSelect({ types, value, onChange, disabled, className }: Props) {
  const current = types.find((t) => t.id === value);
  return (
    <Select
      value={value || NONE}
      onValueChange={(v) => onChange(!v || v === NONE ? "" : String(v))}
      disabled={disabled}
    >
      <SelectTrigger className={cn("h-9 w-full text-sm", className)}>
        <SelectValue>
          {() =>
            current ? (
              <span className="flex min-w-0 items-center gap-2">
                <Dot color={current.color} />
                <span className="truncate">{current.name}</span>
              </span>
            ) : (
              <span className="text-muted-foreground">{UNCLASSIFIED}</span>
            )
          }
        </SelectValue>
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={NONE}>
          <span className="text-muted-foreground">{UNCLASSIFIED}</span>
        </SelectItem>
        {types.map((t) => (
          <SelectItem key={t.id} value={t.id}>
            <span className="flex items-center gap-2">
              <Dot color={t.color} />
              {t.name}
            </span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
