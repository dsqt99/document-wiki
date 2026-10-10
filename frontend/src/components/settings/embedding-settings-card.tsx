"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { ActivateBar, canActivate } from "./model-catalog-card";
import { ActiveModelChip, ProviderModelPicker } from "./provider-model-picker";
import { Stat } from "./test-lab";

type EmbeddingTestResp = {
  success: boolean;
  model: string;
  dimension: number;
  expected_dimension: number;
  latency_ms: number;
  similarities: number[];
  preview: number[];
  error: string | null;
};

const SAMPLE_QUERY = "Thủ tục đăng ký thường trú cần giấy tờ gì?";
const SAMPLE_PASSAGES = [
  "Hồ sơ đăng ký thường trú gồm tờ khai thay đổi thông tin cư trú và giấy tờ chứng minh chỗ ở hợp pháp.",
  "Người điều khiển xe mô tô không đội mũ bảo hiểm bị phạt tiền từ 400.000 đến 600.000 đồng.",
  "Công dân có quyền tự do cư trú theo quy định của Luật Cư trú.",
].join("\n");

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
  // Ping + test lab results are tied to the spec they were run against.
  const [pinging, setPinging] = useState(false);
  const [ping, setPing] = useState<(EmbeddingTestResp & { id: string }) | null>(null);
  const [query, setQuery] = useState(SAMPLE_QUERY);
  const [passages, setPassages] = useState(SAMPLE_PASSAGES);
  const [testing, setTesting] = useState(false);
  const [test, setTest] = useState<(EmbeddingTestResp & { id: string; passages: string[] }) | null>(null);

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

  const conn = ping && ping.id === selected ? ping : null;
  const lab = test && test.id === selected ? test : null;

  async function runTest(specId: string, q: string, ps: string[]) {
    try {
      return await api<EmbeddingTestResp>("/api/settings/embeddings/test", {
        method: "POST",
        body: { model_spec_id: specId, query: q, passages: ps },
      });
    } catch (e) {
      return {
        success: false,
        model: specId,
        dimension: 0,
        expected_dimension: 0,
        latency_ms: 0,
        similarities: [],
        preview: [],
        error: e instanceof Error ? e.message : "Request failed",
      } satisfies EmbeddingTestResp;
    }
  }

  async function handlePing() {
    if (!selected) return;
    setPinging(true);
    const res = await runTest(selected, "ping", []);
    setPing({ ...res, id: selected });
    setPinging(false);
  }

  async function handleRunTest() {
    if (!selected) return;
    const ps = passages
      .split("\n")
      .map((p) => p.trim())
      .filter(Boolean)
      .slice(0, 8);
    setTesting(true);
    const res = await runTest(selected, query.trim(), ps);
    setTest({ ...res, id: selected, passages: ps });
    setTesting(false);
  }

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
        <Button
          variant="outline"
          size="sm"
          onClick={handlePing}
          disabled={pinging || !selectedSpec}
          className="h-9 gap-1 text-xs"
          title="Embed thử 1 câu ngắn bằng model đang chọn"
        >
          <span className={`material-symbols-outlined text-sm ${pinging ? "animate-spin" : ""}`}>
            {pinging ? "progress_activity" : "network_ping"}
          </span>
          Ping
        </Button>
        {conn && (
          <span
            className={`flex items-center gap-1 text-xs ${
              conn.success && conn.dimension === conn.expected_dimension
                ? "text-emerald-600 dark:text-emerald-400"
                : "text-destructive"
            }`}
          >
            <span className="material-symbols-outlined text-sm">
              {conn.success && conn.dimension === conn.expected_dimension ? "check_circle" : "error"}
            </span>
            <span className="max-w-[320px] truncate" title={conn.error ?? undefined}>
              {!conn.success
                ? conn.error
                : conn.dimension === conn.expected_dimension
                  ? `OK · ${conn.dimension} chiều`
                  : `Trả về ${conn.dimension} chiều, cấu hình ${conn.expected_dimension}`}
            </span>
            {conn.latency_ms > 0 && <span className="font-mono">· {conn.latency_ms} ms</span>}
          </span>
        )}
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

      {/* Test lab */}
      <div className="rounded-xl border border-border/70 bg-muted/10 p-4">
        <div className="mb-3 flex items-center justify-between">
          <span className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            <span className="material-symbols-outlined text-sm text-primary">science</span>
            Thử embedding
          </span>
          {selectedSpec && (
            <span className="truncate text-[11px] text-muted-foreground">
              Model thử: <span className="font-medium text-foreground">{selectedSpec.label}</span>
            </span>
          )}
        </div>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
          <div className="flex flex-col gap-2 lg:col-span-5">
            <label className="text-[11px] font-medium text-muted-foreground">Câu hỏi</label>
            <Input value={query} onChange={(e) => setQuery(e.target.value)} className="bg-background text-xs" />
            <label className="text-[11px] font-medium text-muted-foreground">
              Đoạn văn so sánh (mỗi dòng 1 đoạn, tối đa 8)
            </label>
            <textarea
              value={passages}
              onChange={(e) => setPassages(e.target.value)}
              rows={6}
              className="rounded-md border border-input bg-background p-2 text-xs leading-relaxed focus:outline-none focus:ring-1 focus:ring-primary"
            />
            <Button
              size="sm"
              onClick={handleRunTest}
              disabled={testing || !selectedSpec || !query.trim()}
              className="h-9 w-full gap-2 text-xs font-medium"
            >
              <span className={`material-symbols-outlined text-sm ${testing ? "animate-spin" : ""}`}>
                {testing ? "progress_activity" : "compare_arrows"}
              </span>
              {testing ? "Đang embed..." : "Chạy so khớp"}
            </Button>
          </div>

          <div className="flex min-h-[220px] flex-col rounded-lg border border-border bg-background lg:col-span-7">
            {!lab ? (
              <div className="flex flex-1 flex-col items-center justify-center gap-1 p-6 text-center text-xs text-muted-foreground">
                <span className="material-symbols-outlined text-2xl opacity-50">scatter_plot</span>
                Chạy thử để xem độ tương đồng cosine giữa câu hỏi và từng đoạn.
              </div>
            ) : !lab.success ? (
              <div className="m-3 rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-destructive dark:border-red-800 dark:bg-red-950/30">
                {lab.error || "Embedding thất bại"}
              </div>
            ) : (
              <>
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-border px-3 py-2 text-[11px] text-muted-foreground">
                  <Stat icon="data_array">
                    <span className={lab.dimension === lab.expected_dimension ? "" : "text-destructive"}>
                      {lab.dimension} chiều
                      {lab.dimension !== lab.expected_dimension && ` (cấu hình ${lab.expected_dimension})`}
                    </span>
                  </Stat>
                  <Stat icon="timer">{lab.latency_ms} ms</Stat>
                  <Stat icon="memory">
                    <span className="font-mono">{lab.model}</span>
                  </Stat>
                </div>
                <div className="flex flex-1 flex-col gap-2 p-3">
                  {lab.passages.length === 0 && (
                    <p className="text-xs text-muted-foreground">Không có đoạn văn để so sánh.</p>
                  )}
                  {lab.passages
                    .map((p, i) => ({ p, s: lab.similarities[i] ?? 0, i }))
                    .sort((a, b) => b.s - a.s)
                    .map(({ p, s, i }, rank) => (
                      <div key={i} className="flex flex-col gap-1">
                        <div className="flex items-start justify-between gap-3 text-xs">
                          <span className={`line-clamp-2 ${rank === 0 ? "font-medium text-foreground" : "text-muted-foreground"}`}>
                            {p}
                          </span>
                          <span className="shrink-0 font-mono tabular-nums">{s.toFixed(4)}</span>
                        </div>
                        <div className="h-1.5 overflow-hidden rounded bg-muted">
                          <div
                            className={`h-full ${rank === 0 ? "bg-primary" : "bg-primary/40"}`}
                            style={{ width: `${Math.max(0, Math.min(1, s)) * 100}%` }}
                          />
                        </div>
                      </div>
                    ))}
                </div>
                {lab.preview.length > 0 && (
                  <div className="truncate border-t border-border px-3 py-2 font-mono text-[10px] text-muted-foreground">
                    [{lab.preview.map((v) => v.toFixed(4)).join(", ")}, …]
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
