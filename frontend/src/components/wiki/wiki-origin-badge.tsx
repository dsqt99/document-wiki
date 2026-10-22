"use client";

import { useI18n } from "@/lib/i18n";

export function WikiOriginBadge({ tag }: { tag?: "extracted" | "generated" | null }) {
  const { t } = useI18n();
  const label = tag ? t(`wiki.origin.${tag}`) : "—";
  const description = t(`wiki.origin.${tag ?? "unknown"}.description`);
  return <span title={description} className="inline-flex whitespace-nowrap rounded-md border bg-muted/40 px-2 py-0.5 text-[11px] font-medium text-muted-foreground">{label}</span>;
}
