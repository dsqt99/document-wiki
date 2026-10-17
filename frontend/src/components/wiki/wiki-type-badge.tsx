"use client";

import { cn } from "@/lib/utils";

type TypeConfig = { icon: string; label: string; color: string };

// Neutral grey used for index/log and as the fallback colour.
const NEUTRAL = "#8a8580";

const TYPE_CONFIG: Record<string, TypeConfig> = {
  entity: { icon: "article", label: "Page", color: "#c0603a" }, // terracotta
  concept: { icon: "article", label: "Page", color: "#8c7b6b" }, // warm taupe
  topic: { icon: "article", label: "Page", color: "#6f8f72" }, // sage
  source: { icon: "description", label: "Source", color: "#8a78a6" }, // muted lavender
  index: { icon: "list_alt", label: "Index", color: NEUTRAL },
  log: { icon: "history", label: "Log", color: NEUTRAL },
  hot: { icon: "local_fire_department", label: "Hot Cache", color: "#c0603a" },
};

const GROUP_LABEL: Record<string, string> = {
  entity: "Pages",
  concept: "Pages",
  topic: "Pages",
  source: "Sources",
  index: "Index",
  log: "Log",
  hot: "Hot Cache",
};

/** Material Symbols ligature for a page type (defaults to "article"). */
export function wikiTypeIcon(type: string): string {
  return TYPE_CONFIG[type]?.icon ?? "article";
}

/** Display colour for a page type (defaults to neutral grey). */
export function wikiTypeColor(type: string): string {
  return TYPE_CONFIG[type]?.color ?? NEUTRAL;
}

/** Group heading for a page type; unknown types are returned unchanged. */
export function wikiTypeGroupLabel(type: string): string {
  return GROUP_LABEL[type] ?? type;
}

export function WikiTypeBadge({ type, className }: { type: string; className?: string }) {
  const cfg = TYPE_CONFIG[type] ?? TYPE_CONFIG.concept;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] leading-4 font-medium whitespace-nowrap",
        className,
      )}
      style={{
        color: cfg.color,
        backgroundColor: `color-mix(in srgb, ${cfg.color} 10%, transparent)`,
        borderColor: `color-mix(in srgb, ${cfg.color} 30%, transparent)`,
      }}
    >
      <span className="material-symbols-outlined" style={{ fontSize: 13 }}>
        {cfg.icon}
      </span>
      {cfg.label}
    </span>
  );
}
