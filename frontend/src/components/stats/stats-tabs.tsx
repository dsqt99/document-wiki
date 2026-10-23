"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { BarList, CHART_COLORS, LineChart } from "./charts";
import {
  ChartCard,
  ExportCsvButton,
  KpiCard,
  StatsSkeleton,
  formatAsOf,
  formatDuration,
  formatNumber,
  listOf,
  seriesOf,
  type GapItem,
  type KpiTone,
  type LintReport,
  type StatsGaps,
  type StatsOverview,
  type StatsSection,
} from "./stats-parts";

type Range = { from: string; to: string };

/* ------------------------------------------------------------------ */
/* Overview                                                             */
/* ------------------------------------------------------------------ */

type KpiDef = {
  labelKey: string;
  fallback: string;
  kpi: string;
  icon: string;
  duration?: boolean;
  warnWhenPositive?: boolean;
};

const OVERVIEW_KPIS: KpiDef[] = [
  { labelKey: "stats.kpiTotalPages", fallback: "Total wiki pages", kpi: "wiki.pages.total", icon: "auto_stories" },
  { labelKey: "stats.kpiStalePages", fallback: "Stale pages (30d)", kpi: "wiki.pages.stale_30d", icon: "hourglass_empty", warnWhenPositive: true },
  { labelKey: "stats.kpiOrphanPages", fallback: "Orphan pages", kpi: "wiki.pages.orphan", icon: "link_off", warnWhenPositive: true },
  { labelKey: "stats.kpiPagesUpdatedToday", fallback: "Pages updated today", kpi: "wiki.pages.updated", icon: "edit_note" },
  { labelKey: "stats.kpiDraftsPending", fallback: "Drafts pending", kpi: "draft.pending", icon: "rate_review" },
  { labelKey: "stats.kpiAvgTimeToReview", fallback: "Avg time-to-review", kpi: "draft.time_to_review_avg_seconds", icon: "schedule", duration: true },
  { labelKey: "stats.kpiPlansAwaitingReview", fallback: "Plans awaiting review", kpi: "compile_plan.pending_review", icon: "task_alt" },
  { labelKey: "stats.kpiDeniedAccess", fallback: "Denied access (today)", kpi: "audit.denied", icon: "block", warnWhenPositive: true },
  { labelKey: "stats.kpiMcpActiveUsers", fallback: "MCP active users (today)", kpi: "mcp.active_users", icon: "person" },
  { labelKey: "stats.kpiMcpWau", fallback: "MCP WAU", kpi: "mcp.weekly_active_users", icon: "group" },
  { labelKey: "stats.kpiMcpQueries", fallback: "MCP queries (today)", kpi: "mcp.queries.total", icon: "search" },
  { labelKey: "stats.kpiZeroResultQueries", fallback: "Zero-result queries (today)", kpi: "mcp.queries.zero_result", icon: "search_off", warnWhenPositive: true },
];

export function OverviewTab({ data }: { data: StatsOverview | null }) {
  const { t } = useI18n();
  if (!data) return <StatsSkeleton />;

  const kpis = data.kpis ?? {};
  const gap = data.top_gap_topic;
  const contributor = data.top_contributor;

  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {OVERVIEW_KPIS.map((def) => {
          const raw = kpis[def.kpi];
          const value = typeof raw === "number" ? raw : null;
          const tone: KpiTone = def.warnWhenPositive && value !== null && value > 0 ? "warn" : "default";
          return (
            <KpiCard
              key={def.kpi}
              icon={def.icon}
              label={t(def.labelKey, def.fallback)}
              value={def.duration ? formatDuration(value) : formatNumber(value)}
              tone={tone}
            />
          );
        })}
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="rounded-xl border bg-card p-4">
          <h3 className="text-sm font-medium">{t("stats.topGapTitle", "Top knowledge gap")}</h3>
          {gap ? (
            <>
              <p className="mt-2 text-lg">{gap.normalized || "—"}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Asked {gap.count ?? 0} times. Sample: “{gap.samples?.[0] ?? ""}”
              </p>
            </>
          ) : (
            <p className="mt-2 text-sm text-muted-foreground">{t("stats.noGapNotice", "No zero-result queries.")}</p>
          )}
        </div>
        <div className="rounded-xl border bg-card p-4">
          <h3 className="text-sm font-medium">{t("stats.topContributorTitle", "Top contributor (last 30d)")}</h3>
          {contributor ? (
            <>
              <p className="mt-2 text-lg">{contributor.name || "—"}</p>
              <p className="mt-1 text-xs text-muted-foreground">{contributor.count ?? 0} drafts submitted</p>
            </>
          ) : (
            <p className="mt-2 text-sm text-muted-foreground">
              {t("stats.noContributorNotice", "No drafts in the window.")}
            </p>
          )}
        </div>
      </div>

      <p className="text-xs text-muted-foreground">As of {formatAsOf(data.as_of)}</p>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Content                                                              */
/* ------------------------------------------------------------------ */

export function ContentTab({ data, range }: { data: StatsSection | null; range: Range }) {
  if (!data) return <StatsSkeleton />;

  const byType = listOf(data, "wiki.pages.by_type").map((row) => {
    const dims = (row.dimensions ?? {}) as Record<string, unknown>;
    return {
      name: (dims.page_type as string) || (row.page_type as string) || "—",
      count: typeof row.count === "number" ? row.count : Number(row.count) || 0,
    };
  });
  const topPages = listOf(data, "wiki.top_pages").map((row) => ({
    name: (row.title as string) || (row.slug as string),
    revisions: row.revisions,
  }));

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <ChartCard title="Pages updated per day">
          <LineChart data={seriesOf(data, "wiki.pages.updated")} color={CHART_COLORS.blue} />
        </ChartCard>
        <ChartCard title="Revisions per day">
          <LineChart data={seriesOf(data, "wiki.revisions.daily")} color={CHART_COLORS.earth} />
        </ChartCard>
        <ChartCard title="Stale pages (>30d, snapshot)">
          <LineChart data={seriesOf(data, "wiki.pages.stale_30d")} color={CHART_COLORS.wine} />
        </ChartCard>
        <ChartCard title="Orphan pages (snapshot)">
          <LineChart data={seriesOf(data, "wiki.pages.orphan")} color={CHART_COLORS.lilac} />
        </ChartCard>
      </div>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <ChartCard title="Pages by type">
          <BarList items={byType} color={CHART_COLORS.blue} />
        </ChartCard>
        <ChartCard title="Top edited pages" action={<ExportCsvButton section="content" {...range} />}>
          <BarList items={topPages} valueKey="revisions" color={CHART_COLORS.blue} />
        </ChartCard>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Contribution                                                         */
/* ------------------------------------------------------------------ */

export function ContributionTab({ data, range }: { data: StatsSection | null; range: Range }) {
  if (!data) return <StatsSkeleton />;

  const bySource = listOf(data, "draft.created.by_source").map((row) => {
    const dims = (row.dimensions ?? {}) as Record<string, unknown>;
    return { name: (dims.source as string) || (row.source as string) || "—", count: row.count };
  });

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <ChartCard title="Drafts created per day">
          <LineChart data={seriesOf(data, "draft.created")} color={CHART_COLORS.blue} />
        </ChartCard>
        <ChartCard title="Drafts approved / rejected">
          <div className="flex flex-col gap-3">
            <LineChart data={seriesOf(data, "draft.approved")} color={CHART_COLORS.green} label="Approved" />
            <LineChart data={seriesOf(data, "draft.rejected")} color={CHART_COLORS.wine} label="Rejected" />
          </div>
        </ChartCard>
        <ChartCard title="Pending drafts (snapshot)">
          <LineChart data={seriesOf(data, "draft.pending")} color={CHART_COLORS.earth} />
        </ChartCard>
        <ChartCard title="Avg time-to-review (seconds)">
          <LineChart data={seriesOf(data, "draft.time_to_review_avg_seconds")} color={CHART_COLORS.blue} />
        </ChartCard>
      </div>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <ChartCard title="Top contributors" action={<ExportCsvButton section="contribution" {...range} />}>
          <BarList items={listOf(data, "draft.top_contributors")} />
        </ChartCard>
        <ChartCard title="Top reviewers">
          <BarList items={listOf(data, "draft.top_reviewers")} />
        </ChartCard>
        <ChartCard title="By source">
          <BarList items={bySource} />
        </ChartCard>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Usage                                                                */
/* ------------------------------------------------------------------ */

export function UsageTab({ data, range }: { data: StatsSection | null; range: Range }) {
  if (!data) return <StatsSkeleton />;

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <ChartCard title="MCP queries per day">
          <LineChart data={seriesOf(data, "mcp.queries.total")} color={CHART_COLORS.blue} />
        </ChartCard>
        <ChartCard title="Zero-result queries">
          <LineChart data={seriesOf(data, "mcp.queries.zero_result")} color={CHART_COLORS.wine} />
        </ChartCard>
        <ChartCard title="Daily active users">
          <LineChart data={seriesOf(data, "mcp.active_users")} color={CHART_COLORS.green} />
        </ChartCard>
        <ChartCard title="Avg latency (ms)">
          <LineChart data={seriesOf(data, "mcp.latency_ms_avg")} color={CHART_COLORS.lilac} />
        </ChartCard>
      </div>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <ChartCard title="Queries by tool" action={<ExportCsvButton section="usage" {...range} />}>
          <BarList items={listOf(data, "mcp.queries.by_tool")} labelKey="tool_name" />
        </ChartCard>
        <ChartCard title="Top employees by query count">
          <BarList items={listOf(data, "mcp.top_employees")} />
        </ChartCard>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Gaps                                                                 */
/* ------------------------------------------------------------------ */

const TH = "px-4 py-2 text-[11px] font-medium tracking-wide text-muted-foreground uppercase";

export function GapsTab({ data, range }: { data: StatsGaps | null; range: Range }) {
  if (!data) return <StatsSkeleton />;
  const items: GapItem[] = data.items ?? [];

  if (items.length === 0) {
    return (
      <div className="rounded-xl border bg-card p-8 text-center text-sm text-muted-foreground">
        No zero-result queries in this window — your KB is covering what people search for.
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border bg-card">
      <div className="flex items-center justify-between border-b px-4 py-3">
        <h3 className="text-sm font-medium">Top knowledge gaps (zero-result queries)</h3>
        <ExportCsvButton section="gaps" {...range} />
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-muted/40">
            <tr>
              <th className={cn(TH, "text-left")}>Topic (normalized)</th>
              <th className={cn(TH, "text-right")}>Count</th>
              <th className={cn(TH, "text-left")}>Sample queries</th>
              <th className={cn(TH, "text-right")}>Action</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item, i) => {
              const title = item.samples?.[0] || item.normalized;
              return (
                <tr key={`${item.normalized}-${i}`} className="border-t hover:bg-muted/30">
                  <td className="px-4 py-2 align-top font-medium">{item.normalized}</td>
                  <td className="px-4 py-2 text-right align-top tabular-nums">{item.count}</td>
                  <td className="px-4 py-2 align-top">
                    <div className="flex flex-col gap-0.5">
                      {(item.samples ?? []).slice(0, 2).map((s, j) => (
                        <span key={j} className="block max-w-[420px] truncate text-xs text-muted-foreground" title={s}>
                          “{s}”
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="px-4 py-2 text-right align-top">
                    <Link
                      href={`/wiki?new=1&title=${encodeURIComponent(title)}`}
                      className="text-xs whitespace-nowrap hover:underline"
                    >
                      Create draft →
                    </Link>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Diagnostics (wiki linter)                                            */
/* ------------------------------------------------------------------ */

type Group = "amber" | "earth" | "red";

const GROUP_STYLE: Record<Group, { card: string; head: string; title: string; pill: string; icon: string }> = {
  amber: {
    card: "border-amber-300/60 bg-amber-50 dark:border-amber-500/30 dark:bg-amber-500/10",
    head: "bg-amber-50 dark:bg-amber-500/10",
    title: "text-amber-800 dark:text-amber-300",
    pill: "bg-amber-100 text-amber-800 dark:bg-amber-500/20 dark:text-amber-300",
    icon: "text-amber-600 dark:text-amber-400",
  },
  earth: {
    card: "border-orange-300/60 bg-orange-50 dark:border-orange-500/30 dark:bg-orange-500/10",
    head: "bg-orange-50 dark:bg-orange-500/10",
    title: "text-orange-800 dark:text-orange-300",
    pill: "bg-orange-100 text-orange-800 dark:bg-orange-500/20 dark:text-orange-300",
    icon: "text-orange-600 dark:text-orange-400",
  },
  red: {
    card: "border-red-300/60 bg-red-50 dark:border-red-500/30 dark:bg-red-500/10",
    head: "bg-red-50 dark:bg-red-500/10",
    title: "text-red-800 dark:text-red-300",
    pill: "bg-red-100 text-red-800 dark:bg-red-500/20 dark:text-red-300",
    icon: "text-red-600 dark:text-red-400",
  },
};

function SummaryCard({
  icon,
  iconClass,
  label,
  count,
  description,
  group,
}: {
  icon: string;
  iconClass: string;
  label: string;
  count: number;
  description: string;
  group: Group;
}) {
  return (
    <div className={cn("rounded-xl border p-4", count > 0 ? GROUP_STYLE[group].card : "border-border bg-card")}>
      <div className="flex items-center gap-1.5 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
        <span className={cn("material-symbols-outlined", iconClass)} style={{ fontSize: 16 }}>
          {icon}
        </span>
        {label}
      </div>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{count}</p>
      <p className="mt-0.5 text-[11px] text-muted-foreground">{description}</p>
    </div>
  );
}

function IssueTable({
  group,
  icon,
  title,
  badge,
  headers,
  children,
}: {
  group: Group;
  icon: string;
  title: string;
  badge: string;
  headers: { label: string; right?: boolean }[];
  children: ReactNode;
}) {
  const s = GROUP_STYLE[group];
  return (
    <div className="overflow-hidden rounded-xl border bg-card">
      <div className={cn("flex items-center gap-2 border-b px-4 py-3", s.head)}>
        <span className={cn("material-symbols-outlined", s.icon)} style={{ fontSize: 18 }}>
          {icon}
        </span>
        <h3 className={cn("text-sm font-medium", s.title)}>{title}</h3>
        <span className={cn("ml-auto rounded-full px-2 py-0.5 font-mono text-[11px] font-bold", s.pill)}>{badge}</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-muted/40">
            <tr>
              {headers.map((h) => (
                <th key={h.label} className={cn(TH, h.right ? "text-right" : "text-left")}>
                  {h.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>{children}</tbody>
        </table>
      </div>
    </div>
  );
}

const ROW = "border-b last:border-b-0 hover:bg-muted/30";
const CELL = "px-4 py-3 align-top";

function PageCell({ slug, title }: { slug: string; title: string }) {
  return (
    <>
      <Link href={`/wiki/${slug}`} className="font-medium hover:underline">
        {title || slug}
      </Link>
      <p className="font-mono text-[10px] text-muted-foreground">slug: {slug}</p>
    </>
  );
}

function ActionLink({ href, icon, label }: { href: string; icon: string; label: string }) {
  return (
    <Link href={href} className="inline-flex items-center gap-1 text-xs whitespace-nowrap text-primary hover:underline">
      <span className="material-symbols-outlined" style={{ fontSize: 14 }}>
        {icon}
      </span>
      {label}
    </Link>
  );
}

export function DiagnosticsTab({ data, loading }: { data: LintReport | null; loading: boolean }) {
  if (loading || !data) return <StatsSkeleton />;

  const deadLinks = data.dead_links ?? [];
  const orphans = data.orphans ?? [];
  const contradictions = data.contradictions ?? [];
  const total = deadLinks.length + orphans.length + contradictions.length;

  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <SummaryCard
          icon="link_off"
          iconClass="text-amber-600 dark:text-amber-400"
          label="Dead Links"
          count={deadLinks.length}
          description="Broken internal links pointing to non-existent wiki pages."
          group="amber"
        />
        <SummaryCard
          icon="article"
          iconClass="text-amber-600 dark:text-amber-400"
          label="Orphan Pages"
          count={orphans.length}
          description="Wiki pages that have no incoming links from other pages."
          group="earth"
        />
        <SummaryCard
          icon="warning"
          iconClass="text-red-600 dark:text-red-400"
          label="Contradictions"
          count={contradictions.length}
          description="Wiki pages containing logical conflicts identified by AI Verifier."
          group="red"
        />
      </div>

      {total === 0 ? (
        <div className="flex flex-col items-center rounded-xl border border-emerald-300/60 bg-emerald-50 p-8 text-center text-emerald-800 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300">
          <span className="material-symbols-outlined text-emerald-600 dark:text-emerald-400" style={{ fontSize: 36 }}>
            check_circle
          </span>
          <p className="mt-2 font-semibold">Knowledge Base is perfectly healthy!</p>
          <p className="mt-1 max-w-md text-xs">
            No dead links, orphan pages, or logical contradictions were detected in your flat wiki workspace.
          </p>
        </div>
      ) : (
        <>
          {deadLinks.length > 0 && (
            <IssueTable
              group="amber"
              icon="link_off"
              title="Dead Links"
              badge={`${deadLinks.length} errors`}
              headers={[{ label: "Source Page" }, { label: "Broken Target Link" }, { label: "Action", right: true }]}
            >
              {deadLinks.map((d, i) => (
                <tr key={`${d.from_slug}-${d.to_slug}-${i}`} className={ROW}>
                  <td className={CELL}>
                    <PageCell slug={d.from_slug} title={d.from_title} />
                  </td>
                  <td className={cn(CELL, "font-mono text-xs font-bold text-destructive")}>[[{d.to_slug}]]</td>
                  <td className={cn(CELL, "text-right")}>
                    <ActionLink href={`/wiki/${d.from_slug}?edit=1`} icon="edit" label="Edit Source →" />
                  </td>
                </tr>
              ))}
            </IssueTable>
          )}

          {orphans.length > 0 && (
            <IssueTable
              group="earth"
              icon="article"
              title="Orphan Pages"
              badge={`${orphans.length} pages`}
              headers={[{ label: "Page Title" }, { label: "Action", right: true }]}
            >
              {orphans.map((o) => (
                <tr key={o.slug} className={ROW}>
                  <td className={CELL}>
                    <PageCell slug={o.slug} title={o.title} />
                  </td>
                  <td className={cn(CELL, "text-right")}>
                    <ActionLink href={`/wiki/${o.slug}`} icon="visibility" label="View Page →" />
                  </td>
                </tr>
              ))}
            </IssueTable>
          )}

          {contradictions.length > 0 && (
            <IssueTable
              group="red"
              icon="warning"
              title="Knowledge Contradictions"
              badge={`${contradictions.length} issues`}
              headers={[{ label: "Conflicted Page" }, { label: "Error Details" }, { label: "Action", right: true }]}
            >
              {contradictions.map((c) => (
                <tr key={c.slug} className={ROW}>
                  <td className={CELL}>
                    <PageCell slug={c.slug} title={c.title} />
                  </td>
                  <td className={cn(CELL, "text-xs text-red-600/80 dark:text-red-400/80")}>
                    Detected a{" "}
                    <code className="rounded border border-red-300/60 bg-red-50 px-1 font-mono text-[10px] dark:border-red-500/30 dark:bg-red-500/10">
                      [!contradiction]
                    </code>{" "}
                    alert badge pinned on this page by the AI Verifier.
                  </td>
                  <td className={cn(CELL, "text-right")}>
                    <ActionLink href={`/wiki/${c.slug}`} icon="rule" label="Review Contradiction →" />
                  </td>
                </tr>
              ))}
            </IssueTable>
          )}
        </>
      )}
    </div>
  );
}
