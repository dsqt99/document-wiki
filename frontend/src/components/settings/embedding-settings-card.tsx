"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { ActivateBar, canActivate } from "./model-catalog-card";
import { ActiveModelChip, ProviderModelPicker } from "./provider-model-picker";

type EmbeddingSpec = {
  id: string;
  provider: string;
  group: string;
  model_id: string;
  dimension: number;
  label: string;
  cost_per_1m_tokens: number | null;
  notes: string | null;
  api_key_configured: boolean;
  api_key_config_key: string | null;
  custom: boolean;
  base_url: string | null;
};

type CatalogResp = {
  active_spec_id: string | null;
  specs: EmbeddingSpec[];
};

type StatusResp = {
  active_spec_id: string | null;
  total_pages: number;
  embedded_pages: number;
  current_job: JobResp | null;
};

type JobResp = {
  id: string;
  model_spec_id: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  total_pages: number;
  done_pages: number;
  error_message: string | null;
};

export function EmbeddingSettingsCard() {
  const { t } = useI18n();
  const [catalog, setCatalog] = useState<CatalogResp | null>(null);
  const [status, setStatus] = useState<StatusResp | null>(null);
  const [settings, setSettings] = useState<Record<string, unknown>>({});
  const [selected, setSelected] = useState<string | null>(null);
  const [switching, setSwitching] = useState(false);
  const [error, setError] = useState("");
  const [backfilling, setBackfilling] = useState(false);
  const [backfillQueued, setBackfillQueued] = useState(false);

  useEffect(() => {
    void refresh();
  }, []);

  // Poll active job every 2s while one is running.
  useEffect(() => {
    if (!status?.current_job || (status.current_job.status !== "pending" && status.current_job.status !== "running")) {
      return;
    }
    const timer = setInterval(() => {
      void refresh();
    }, 2000);
    return () => clearInterval(timer);
  }, [status]);

  async function refresh() {
    try {
      const [c, s, st] = await Promise.all([
        api<CatalogResp>("/api/settings/embeddings/catalog"),
        api<StatusResp>("/api/settings/embeddings/status"),
        api<Record<string, unknown>>("/api/settings"),
      ]);
      setCatalog(c);
      setStatus(s);
      setSettings(st);
      setSelected((prev) => (prev && c.specs.some((x) => x.id === prev) ? prev : c.active_spec_id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Load failed");
    }
  }

  const selectedSpec = catalog?.specs.find((s) => s.id === selected) ?? null;
  const activeSpec = catalog?.specs.find((s) => s.id === catalog.active_spec_id) ?? null;
  const job = status?.current_job ?? null;
  const jobBusy = !!job && (job.status === "pending" || job.status === "running");
  const willSwitch = !!selectedSpec && selectedSpec.id !== catalog?.active_spec_id;

  async function handleSwitch() {
    if (!selectedSpec) return;
    if (
      !confirm(
        `Chuyển sang ${selectedSpec.label} sẽ embed lại toàn bộ ${status?.total_pages ?? ""} trang wiki. Tiếp tục?`,
      )
    )
      return;
    setSwitching(true);
    setError("");
    try {
      await api("/api/settings/embeddings/switch", {
        method: "POST",
        body: { model_spec_id: selectedSpec.id },
      });
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Switch failed");
    } finally {
      setSwitching(false);
    }
  }

  async function handleBackfill() {
    setBackfilling(true);
    setError("");
    setBackfillQueued(false);
    try {
      // Returns {job_id}; the worker enqueues the per-source chunk jobs.
      await api<{ job_id: string }>(
        "/api/settings/embeddings/backfill-source-chunks?limit=500",
        { method: "POST" },
      );
      setBackfillQueued(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Backfill failed");
    } finally {
      setBackfilling(false);
    }
  }

  async function cancelJob() {
    if (!job) return;
    try {
      await api(`/api/settings/embeddings/jobs/${job.id}/cancel`, {
        method: "POST",
      });
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Cancel failed");
    }
  }

  if (!catalog || !status) {
    return (
      <div className="bg-card rounded-xl p-6 border border-border shadow-sahara">
        <p className="text-sm text-muted-foreground">Loading embedding catalog…</p>
        {error && <p className="text-xs text-destructive mt-2">{error}</p>}
      </div>
    );
  }

  return (
    <div className="bg-card rounded-xl p-6 border border-border shadow-sahara flex flex-col gap-4">
      <div className="flex items-start gap-3">
        <div className="w-9 h-9 shrink-0 rounded-lg bg-primary/10 flex items-center justify-center">
          <span className="material-symbols-outlined text-primary text-base">data_array</span>
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-base font-semibold text-foreground">
            {t("settings.embeddingTitle", "Embedding Model")}
          </h3>
          <p className="text-xs text-muted-foreground">
            Đã embed {status.embedded_pages}/{status.total_pages} trang. Đổi model sẽ embed lại toàn bộ.
          </p>
        </div>
        <ActiveModelChip spec={activeSpec} />
      </div>

      {/* Job progress */}
      {jobBusy && (
        <div className="p-3 rounded-lg bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-800">
          <div className="flex items-center justify-between text-xs mb-1.5">
            <span>
              Migrating to <strong>{job.model_spec_id}</strong> — {job.done_pages}/{job.total_pages} pages
            </span>
            <button onClick={cancelJob} className="text-xs underline hover:no-underline">
              {t("settings.cancel", "Cancel")}
            </button>
          </div>
          <div className="h-2 rounded bg-blue-100 dark:bg-blue-900 overflow-hidden">
            <div
              className="h-full bg-blue-500 transition-all"
              style={{
                width: `${
                  job.total_pages > 0 ? Math.round((job.done_pages / job.total_pages) * 100) : 0
                }%`,
              }}
            />
          </div>
        </div>
      )}

      {job?.status === "failed" && (
        <div className="p-3 rounded-lg bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 text-xs">
          <strong>Migration failed:</strong> {job.error_message || "unknown"}
        </div>
      )}

      <ProviderModelPicker
        kind="embedding"
        specs={catalog.specs}
        activeId={catalog.active_spec_id}
        selectedId={selected}
        onSelect={setSelected}
        settings={settings}
        onChanged={refresh}
        disabled={jobBusy}
        renderMeta={(s) =>
          s.cost_per_1m_tokens != null ? `$${s.cost_per_1m_tokens}/1M tokens` : null
        }
      />

      <ActivateBar
        willSwitch={willSwitch}
        disabled={jobBusy}
        ready={canActivate(selectedSpec)}
        busy={switching}
        saved={false}
        error={error}
        label={selectedSpec?.label}
        onActivate={handleSwitch}
        actionText="Chuyển & embed lại"
      >
        <button
          disabled={backfilling || jobBusy}
          onClick={handleBackfill}
          title={t(
            "settings.backfillChunksHint",
            "Index raw chunks for documents uploaded before the dual pipeline",
          )}
          className="border border-border px-4 py-2 rounded-lg text-sm font-medium hover:bg-muted disabled:opacity-50"
        >
          {backfilling
            ? t("settings.backfillingChunks", "Queuing…")
            : t("settings.backfillChunks", "Backfill raw chunks")}
        </button>
        {backfillQueued && (
          <p className="text-xs text-muted-foreground">
            {t("settings.backfillQueued", "Backfill job queued")}
          </p>
        )}
      </ActivateBar>
    </div>
  );
}
