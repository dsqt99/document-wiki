"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { LintReport, StatsGaps, StatsOverview, StatsSection } from "@/components/stats/stats-parts";
import {
  ContentTab,
  ContributionTab,
  DiagnosticsTab,
  GapsTab,
  OverviewTab,
  UsageTab,
} from "@/components/stats/stats-tabs";
import WikiLawPage from "./wiki/law/page";

type TabKey = "overview" | "content" | "contribution" | "usage" | "gaps" | "diagnostics";

const TABS: { key: TabKey; labelKey: string; fallback: string }[] = [
  { key: "overview", labelKey: "stats.tabOverview", fallback: "Overview" },
  { key: "content", labelKey: "stats.tabContent", fallback: "Content" },
  { key: "contribution", labelKey: "stats.tabContribution", fallback: "Contribution" },
  { key: "usage", labelKey: "stats.tabUsage", fallback: "Usage" },
  { key: "gaps", labelKey: "stats.tabGaps", fallback: "Gaps" },
  { key: "diagnostics", labelKey: "stats.tabLinter", fallback: "Linter" },
];

const DAY_MS = 86_400_000;
const isoDay = (offsetDays: number) => new Date(Date.now() - offsetDays * DAY_MS).toISOString().slice(0, 10);

type StatsBundle = {
  overview: StatsOverview;
  content: StatsSection;
  contribution: StatsSection;
  usage: StatsSection;
  gaps: StatsGaps;
  lint: LintReport;
};

function errorMessage(err: unknown, fallback: string): string {
  return err instanceof Error && err.message ? err.message : fallback;
}

/** Shown while the session user is not resolved yet. */
function ResolvingScreen() {
  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <div className="relative">
        <div className="absolute -inset-6 rounded-full bg-gradient-to-r from-primary/40 to-purple-500/40 opacity-60 blur-2xl" />
        <div className="relative flex flex-col items-center gap-4 rounded-3xl border border-white/10 bg-slate-900/60 px-10 py-8 text-center shadow-2xl backdrop-blur-xl">
          <div
            className="size-12 animate-spin rounded-full border-4 border-white/10 border-t-primary border-r-primary"
            style={{ animationDuration: "0.8s" }}
          />
          <p className="animate-pulse text-lg font-semibold text-slate-100">Resolving Workspace Scope</p>
          <p className="max-w-[280px] text-xs text-slate-400">Loading data and resolving workspace scope...</p>
        </div>
      </div>
    </div>
  );
}

function StatsDashboard() {
  const { t } = useI18n();
  const [tab, setTab] = useState<TabKey>("overview");
  const [from, setFrom] = useState(() => isoDay(30));
  const [to, setTo] = useState(() => isoDay(1));
  const [data, setData] = useState<Partial<StatsBundle>>({});
  const [loading, setLoading] = useState(false);
  const [rolling, setRolling] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async (fromDate: string, toDate: string) => {
    setLoading(true);
    setError("");
    const range = new URLSearchParams({ from: fromDate, to: toDate }).toString();
    try {
      const [overview, content, contribution, usage, gaps, lint] = await Promise.all([
        api<StatsOverview>("/api/admin/stats/overview"),
        api<StatsSection>(`/api/admin/stats/content?${range}`),
        api<StatsSection>(`/api/admin/stats/contribution?${range}`),
        api<StatsSection>(`/api/admin/stats/usage?${range}`),
        api<StatsGaps>(`/api/admin/stats/gaps?${range}&limit=50`),
        api<LintReport>("/api/wiki/lint"),
      ]);
      setData({ overview, content, contribution, usage, gaps, lint });
    } catch (err) {
      setError(errorMessage(err, "Failed to load statistics"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // Microtask hop: keep the state updates out of the synchronous effect body.
    let active = true;
    void Promise.resolve().then(() => {
      if (active) void load(from, to);
    });
    return () => {
      active = false;
    };
  }, [from, to, load]);

  const rollup = async () => {
    setRolling(true);
    setError("");
    try {
      await api(`/api/admin/stats/rollup?target=${encodeURIComponent(to)}`, { method: "POST" });
      await load(from, to);
    } catch (err) {
      setError(errorMessage(err, "Backfill failed"));
    } finally {
      setRolling(false);
    }
  };

  const range = { from, to };

  return (
    <>
      <div className="flex flex-col gap-12">
        <PageHeader
          title={t("stats.title", "Thống kê & Chẩn đoán")}
          description={t("stats.description")}
          action={
            <>
              <Button variant="outline" onClick={() => void load(from, to)} disabled={loading}>
                <span className={cn("material-symbols-outlined", loading && "animate-spin")} style={{ fontSize: 24, width: 32 }}>
                  refresh
                </span>
                {t("stats.refresh", "Làm mới")}
              </Button>
              <Button variant="outline" onClick={rollup} disabled={rolling}>
                <span className={cn("material-symbols-outlined", rolling && "animate-spin")} style={{ fontSize: 24, width: 32 }}>
                  calculate
                </span>
                {rolling ? t("stats.rolling", "Đang tính…") : `${t("stats.rollup", "Tổng hợp dữ liệu")} ${to}`}
              </Button>
            </>
          }
        />

        <div className="flex flex-wrap items-end gap-3 rounded-xl border bg-card p-3">
          <label className="flex flex-col gap-1.5">
            <span className="text-[10px] font-medium tracking-wider text-muted-foreground uppercase">
              {t("stats.from", "Từ ngày")}
            </span>
            <Input type="date" value={from} onChange={(e) => e.target.value && setFrom(e.target.value)} className="h-9 w-[141px] rounded-md px-2 py-0" />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-[10px] font-medium tracking-wider text-muted-foreground uppercase">
              {t("stats.to", "Đến ngày")}
            </span>
            <Input type="date" value={to} onChange={(e) => e.target.value && setTo(e.target.value)} className="h-9 w-[141px] rounded-md px-2 py-0" />
          </label>
          <div className="ml-auto flex flex-wrap gap-1" role="group">
            {TABS.map((tb) => (
              <button
                key={tb.key}
                type="button"
                aria-pressed={tab === tb.key}
                onClick={() => setTab(tb.key)}
                className={cn(
                  "h-9 rounded-md border px-3 text-sm font-normal transition-colors",
                  tab === tb.key
                    ? "border-foreground bg-foreground text-background"
                    : "bg-background hover:bg-muted",
                )}
              >
                {t(tb.labelKey, tb.fallback)}
              </button>
            ))}
          </div>
        </div>

        {error && (
          <div className="flex items-center gap-2 rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">
            <span className="material-symbols-outlined" style={{ fontSize: 18 }}>
              error
            </span>
            {error}
          </div>
        )}

        <div>
          {tab === "overview" && <OverviewTab data={data.overview ?? null} />}
          {tab === "content" && <ContentTab data={data.content ?? null} range={range} />}
          {tab === "contribution" && <ContributionTab data={data.contribution ?? null} range={range} />}
          {tab === "usage" && <UsageTab data={data.usage ?? null} range={range} />}
          {tab === "gaps" && <GapsTab data={data.gaps ?? null} range={range} />}
          {tab === "diagnostics" && <DiagnosticsTab data={data.lint ?? null} loading={loading} />}
        </div>
      </div>
    </>
  );
}

export default function HomePage() {
  const { user } = useAuth();

  if (!user) return <ResolvingScreen />;

  // Non-admins land on the legal wiki list: it is their knowledge home.
  if (user.role !== "admin") {
    return (
      <Suspense fallback={null}>
        <WikiLawPage />
      </Suspense>
    );
  }

  return <StatsDashboard />;
}
