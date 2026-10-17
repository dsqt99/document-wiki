"use client";

import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

export type WikiStatus = "seed" | "developing" | "mature" | "evergreen";

/** Shared maturity palette (also used by the page tree dots and the graph). */
export const WIKI_STATUS_COLORS: Record<WikiStatus, string> = {
  seed: "#c8a96a", // sand
  developing: "#e08a3c", // orange
  mature: "#2f8f8a", // teal
  evergreen: "#3f9a4f", // green
};

const LABELS: Record<WikiStatus, string> = {
  seed: "Seed",
  developing: "Developing",
  mature: "Mature",
  evergreen: "Evergreen",
};

export function normalizeWikiStatus(status: string | null | undefined): WikiStatus {
  const s = (status ?? "").toLowerCase();
  return s in LABELS ? (s as WikiStatus) : "seed";
}

export function WikiStatusBadge({ status, className }: { status: string; className?: string }) {
  const { t } = useI18n();
  const s = normalizeWikiStatus(status);
  const color = WIKI_STATUS_COLORS[s];
  return (
    <span
      title={t(`wiki.status.${s}`)}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] leading-4 font-medium whitespace-nowrap",
        className,
      )}
      style={{
        color,
        backgroundColor: `color-mix(in srgb, ${color} 10%, transparent)`,
        borderColor: `color-mix(in srgb, ${color} 30%, transparent)`,
      }}
    >
      <span className="size-1.5 rounded-full" style={{ backgroundColor: color }} />
      {LABELS[s]}
    </span>
  );
}
