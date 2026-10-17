"use client";

import type { ReactNode } from "react";
import { apiUrl } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { LinePoint } from "./charts";

/* ------------------------------------------------------------------ */
/* Response shapes of /api/admin/stats/* and /api/wiki/lint            */
/* ------------------------------------------------------------------ */

export type StatsOverview = {
  as_of: string | null;
  kpis: Record<string, number | null>;
  top_gap_topic: { normalized?: string; count?: number; samples?: string[] } | null;
  top_contributor: { name?: string; count?: number; author_id?: string } | null;
};

export type SeriesPoint = {
  date: string;
  value: number | null;
  dimensions?: Record<string, unknown>;
  items?: unknown;
};

export type StatsSection = {
  from_date: string;
  to_date: string;
  series: Record<string, SeriesPoint[]>;
  latest: Record<string, number | null>;
  latest_lists: Record<string, Record<string, unknown>[]>;
};

export type GapItem = { normalized: string; count: number; samples: string[]; requester_ids: string[] };
export type StatsGaps = { items: GapItem[] };

export type LintReport = {
  dead_links?: { from_slug: string; from_title: string; to_slug: string }[];
  orphans?: { slug: string; title: string; status: string }[];
  contradictions?: { slug: string; title: string }[];
};

export type ExportSection = "content" | "contribution" | "usage" | "gaps";

/* ------------------------------------------------------------------ */
/* Formatting                                                           */
/* ------------------------------------------------------------------ */

export function formatNumber(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  if (Math.abs(v) >= 1000) return v.toLocaleString();
  if (Number.isInteger(v)) return String(v);
  return v.toFixed(1);
}

export function formatDuration(seconds: number | null | undefined): string {
  if (!seconds || !Number.isFinite(seconds)) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${(seconds / 60).toFixed(1)}m`;
  if (seconds < 86400) return `${(seconds / 3600).toFixed(1)}h`;
  return `${(seconds / 86400).toFixed(1)}d`;
}

/** Keep only date/value of a series; a missing key yields an empty list. */
export function seriesOf(section: StatsSection | null, key: string): LinePoint[] {
  const raw = section?.series?.[key];
  if (!Array.isArray(raw)) return [];
  return raw.map((p) => ({ date: p.date, value: p.value }));
}

export function listOf(section: StatsSection | null, key: string): Record<string, unknown>[] {
  const raw = section?.latest_lists?.[key];
  if (Array.isArray(raw)) return raw;
  return latestFromSeries(section, key);
}

/** Breakdown of the newest day rebuilt from a series (used when latest_lists omits the key). */
function latestFromSeries(section: StatsSection | null, key: string): Record<string, unknown>[] {
  const points = section?.series?.[key];
  if (!Array.isArray(points) || points.length === 0) return [];
  const newest = points.reduce((max, p) => (p.date > max ? p.date : max), points[0].date);
  const day = points.filter((p) => p.date === newest);
  for (const p of day) {
    if (Array.isArray(p.items)) return p.items as Record<string, unknown>[];
  }
  return day
    .filter((p) => p.dimensions && Object.keys(p.dimensions).length > 0)
    .map((p) => ({ ...p.dimensions, dimensions: p.dimensions, count: p.value ?? 0 }))
    .sort((a, b) => Number(b.count) - Number(a.count));
}

/** "As of" label: the calendar date only, whether the API sends a date or a datetime. */
export function formatAsOf(value: string | null | undefined): string {
  if (!value) return "—";
  const m = /^(\d{4}-\d{2}-\d{2})/.exec(value);
  if (m) return m[1];
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toISOString().slice(0, 10);
}

/* ------------------------------------------------------------------ */
/* Building blocks                                                      */
/* ------------------------------------------------------------------ */

export type KpiTone = "default" | "warn" | "good";

const TONE_CLASS: Record<KpiTone, string> = {
  default: "border-border bg-card",
  warn: "border-amber-300/60 bg-amber-50/40 dark:border-amber-500/30 dark:bg-amber-500/10",
  good: "border-emerald-300/60 bg-emerald-50 dark:border-emerald-500/30 dark:bg-emerald-500/10",
};

export function KpiCard({
  icon,
  label,
  value,
  hint,
  tone = "default",
}: {
  icon: string;
  label: string;
  value: string;
  hint?: string;
  tone?: KpiTone;
}) {
  return (
    <div className={cn("rounded-xl border p-3", TONE_CLASS[tone])}>
      <div className="flex items-center gap-1.5 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
        <span className="material-symbols-outlined" style={{ fontSize: 24 }}>
          {icon}
        </span>
        <span className="truncate">{label}</span>
      </div>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
      {hint && <p className="mt-0.5 text-[11px] text-muted-foreground">{hint}</p>}
    </div>
  );
}

export function ChartCard({ title, action, children }: { title: string; action?: ReactNode; children: ReactNode }) {
  return (
    <div className="rounded-xl border bg-card p-4">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-medium">{title}</h3>
        {action}
      </div>
      <div className="mt-3">{children}</div>
    </div>
  );
}

export function StatsSkeleton() {
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      {Array.from({ length: 8 }).map((_, i) => (
        <div key={i} className="h-24 animate-pulse rounded-xl border bg-card" />
      ))}
    </div>
  );
}

/** Download a CSV export with the bearer token; silent on success and failure. */
export function ExportCsvButton({ section, from, to }: { section: ExportSection; from: string; to: string }) {
  const onClick = async () => {
    let token: string | null = null;
    try {
      token = localStorage.getItem("arkon_token");
    } catch {
      token = null;
    }
    if (!token) return;
    try {
      const params = new URLSearchParams({ from, to });
      const res = await fetch(apiUrl(`/api/admin/stats/export/${section}.csv?${params.toString()}`), {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) return;
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `stats_${section}_${from}_${to}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch {
      /* intentionally silent */
    }
  };

  return (
    <button
      type="button"
      onClick={onClick}
      className="text-xs text-muted-foreground hover:text-foreground hover:underline"
    >
      Export CSV
    </button>
  );
}
