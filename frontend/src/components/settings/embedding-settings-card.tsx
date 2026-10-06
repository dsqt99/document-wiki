"use client";

import { useEffect, useState } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { CustomModelForm, deleteCustomModel, saveCustomModelKey } from "./custom-model-form";

type EmbeddingSpec = {
  id: string;
  provider: string;
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
  const [selected, setSelected] = useState<string | null>(null);
  // Masked keys per provider, e.g. {"google": "••••••••P258"}. Loaded from
  // /api/settings; the bullet character means "key already saved server-side".
  const [maskedKeys, setMaskedKeys] = useState<Record<string, string>>({});
  const [apiKey, setApiKey] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [backfilling, setBackfilling] = useState(false);
  const [backfillQueued, setBackfillQueued] = useState(false);
  const [adding, setAdding] = useState(false);

  useEffect(() => {
    void refresh();
  }, []);

  // When the user picks a different model, prefill the input with that
  // provider's masked key (or empty if none).
  useEffect(() => {
    const spec = catalog?.specs.find((s) => s.id === selected);
    if (!spec) setApiKey("");
    else if (spec.custom) setApiKey(spec.api_key_configured ? "••••••••" : "");
    else setApiKey(maskedKeys[spec.provider] ?? "");
  }, [selected, maskedKeys, catalog]);

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
      const [c, s, settings] = await Promise.all([
        api<CatalogResp>("/api/settings/embeddings/catalog"),
        api<StatusResp>("/api/settings/embeddings/status"),
        api<Record<string, unknown>>("/api/settings"),
      ]);
      setCatalog(c);
      setStatus(s);
      setSelected((prev) => (prev && c.specs.some((x) => x.id === prev) ? prev : c.active_spec_id));

      // Extract masked embedding API keys from the general settings payload.
      // Keys follow the convention `embedding_api_key__<provider>`.
      const masked: Record<string, string> = {};
      for (const [k, v] of Object.entries(settings || {})) {
        if (k.startsWith("embedding_api_key__") && typeof v === "string" && v) {
          const provider = k.replace("embedding_api_key__", "");
          masked[provider] = v;
        }
      }
      setMaskedKeys(masked);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Load failed");
    }
  }

  const selectedSpec = catalog?.specs.find((s) => s.id === selected) ?? null;
  const job = status?.current_job ?? null;
  const jobBusy = job && (job.status === "pending" || job.status === "running");
  const isActiveSelected = selectedSpec?.id === catalog?.active_spec_id;
  const willSwitch = !!selectedSpec && !isActiveSelected;
  // The current input value is "the saved masked one" if it contains the
  // bullet character — in that case treat it as "no change".
  const isMaskedKey = apiKey.includes("•");
  const hasNewKey = apiKey.trim().length > 0 && !isMaskedKey;
  const canSave =
    !!selectedSpec &&
    !jobBusy &&
    (hasNewKey || (willSwitch && (selectedSpec.custom || selectedSpec.api_key_configured)));

  async function handleSave() {
    if (!selectedSpec) return;
    setSaving(true);
    setError("");
    try {
      // 1. Save API key for this provider only if user typed a new one.
      if (hasNewKey && selectedSpec.custom) {
        await saveCustomModelKey("embedding", selectedSpec, apiKey.trim());
      } else if (hasNewKey) {
        await api("/api/settings", {
          method: "PUT",
          body: {
            settings: {
              [`embedding_api_key__${selectedSpec.provider}`]: apiKey.trim(),
            },
          },
        });
      }
      // 2. Trigger switch if the selected model differs from active.
      if (willSwitch) {
        await api("/api/settings/embeddings/switch", {
          method: "POST",
          body: { model_spec_id: selectedSpec.id },
        });
      }
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
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

  async function handleDelete(spec: EmbeddingSpec) {
    if (!confirm(`Xóa model "${spec.label}"?`)) return;
    setError("");
    try {
      await deleteCustomModel("embedding", spec.id);
      if (selected === spec.id) setSelected(null);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
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
      </div>
    );
  }

  return (
    <div className="bg-card rounded-xl p-6 border border-border shadow-sahara">
      <div className="flex items-center gap-3 mb-4">
        <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center">
          <span className="material-symbols-outlined text-primary text-base">data_array</span>
        </div>
        <div className="flex-1">
          <h3 className="text-base font-semibold text-foreground">
            {t("settings.embeddingTitle", "Embedding Model")}
          </h3>
          <p className="text-xs text-muted-foreground">
            {t("settings.embeddingDesc", "Choose a model and save its API key.")}
          </p>
        </div>
        {!adding && (
          <button
            onClick={() => setAdding(true)}
            disabled={!!jobBusy}
            className="flex items-center gap-1 border border-border px-2.5 py-1.5 rounded-lg text-xs font-medium hover:bg-muted disabled:opacity-50"
          >
            <span className="material-symbols-outlined text-sm">add</span>
            Thêm model
          </button>
        )}
      </div>

      {adding && (
        <CustomModelForm
          kind="embedding"
          onCancel={() => setAdding(false)}
          onSaved={async (id) => {
            setAdding(false);
            setSelected(id);
            await refresh();
          }}
        />
      )}

      {/* Job progress */}
      {jobBusy && (
        <div className="mb-4 p-3 rounded-lg bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-800">
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
        <div className="mb-4 p-3 rounded-lg bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 text-xs">
          <strong>Migration failed:</strong> {job.error_message || "unknown"}
        </div>
      )}

      {/* Model list — name + provider only */}
      <div className="flex flex-col gap-2 mb-4">
        {catalog.specs.map((spec) => {
          const isActive = spec.id === catalog.active_spec_id;
          const isChecked = spec.id === selected;
          return (
            <label
              key={spec.id}
              className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                isChecked ? "border-primary bg-primary/5" : "border-border hover:bg-accent/30"
              }`}
            >
              <input
                type="radio"
                name="embedding-spec"
                value={spec.id}
                checked={isChecked}
                onChange={() => setSelected(spec.id)}
                disabled={!!jobBusy}
              />
              <span className="text-sm font-medium flex-1 min-w-0">
                {spec.custom ? spec.label : spec.model_id}
                {spec.custom && (
                  <span className="block text-[11px] font-normal text-muted-foreground font-mono break-all">
                    {spec.model_id} · {spec.base_url}
                  </span>
                )}
              </span>
              <span className="text-xs text-muted-foreground">
                {spec.custom ? `Tự thêm · ${spec.dimension}d` : spec.provider}
              </span>
              {isActive && (
                <span className="text-[10px] uppercase tracking-wide bg-green-500/15 text-green-700 dark:text-green-400 px-1.5 py-0.5 rounded">
                  {t("settings.active", "Active")}
                </span>
              )}
              {spec.custom && !isActive && (
                <button
                  type="button"
                  disabled={!!jobBusy}
                  onClick={(e) => {
                    e.preventDefault();
                    void handleDelete(spec);
                  }}
                  title="Xóa model"
                  className="text-muted-foreground hover:text-destructive disabled:opacity-50"
                >
                  <span className="material-symbols-outlined text-base">delete</span>
                </button>
              )}
            </label>
          );
        })}
      </div>

      {/* API key */}
      {selectedSpec && (
        <div className="mb-4 flex flex-col gap-1.5">
          <Label className="text-xs">
            {t("settings.apiKeyFor", "API key for")} {selectedSpec.custom ? selectedSpec.label : selectedSpec.provider}
            {selectedSpec.api_key_configured && (
              <span className="ml-2 text-green-600 dark:text-green-400">
                {t("settings.apiKeySaved", "✓ saved")}
              </span>
            )}
          </Label>
          <Input
            type={isMaskedKey ? "text" : "password"}
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            onFocus={() => {
              if (isMaskedKey) setApiKey("");
            }}
            placeholder={
              selectedSpec.api_key_configured
                ? t("settings.replaceKey", "Replace existing key…")
                : t("settings.pasteKey", "Paste API key")
            }
            className="bg-background"
          />
        </div>
      )}

      {/* Single Save button */}
      <div className="flex items-center gap-3">
        <button
          disabled={!canSave || saving}
          onClick={handleSave}
          className="bg-primary text-primary-foreground px-4 py-2 rounded-lg text-sm font-medium hover:bg-primary/90 disabled:opacity-50"
        >
          {saving ? t("settings.saving", "Saving…") : t("common.save", "Save")}
        </button>
        <button
          disabled={backfilling || !!jobBusy}
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
        {error &&<p className="text-xs text-destructive">{error}</p>}
      </div>
    </div>
  );
}
