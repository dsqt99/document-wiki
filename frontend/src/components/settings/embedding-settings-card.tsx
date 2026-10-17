"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { canActivate } from "./model-catalog-card";
import { ActiveModelChip, ProviderModelPicker } from "./provider-model-picker";
import { Stat } from "./test-lab";

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

type EmbeddingCatalog = { active_spec_id: string | null; specs: EmbeddingSpec[] };

type JobStatus = "pending" | "running" | "completed" | "failed" | "cancelled";

type EmbeddingJob = {
  id: string;
  model_spec_id: string;
  status: JobStatus;
  total_pages: number;
  done_pages: number;
  error_message: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  created_at?: string | null;
};

type EmbeddingStatus = {
  active_spec_id: string | null;
  total_pages: number;
  embedded_pages: number;
  total_sources?: number;
  embedded_sources?: number;
  wiki_chunks_count?: number;
  source_chunks_count?: number;
  current_job: EmbeddingJob | null;
  latest_job?: EmbeddingJob | null;
};

type TestResult = {
  success: boolean;
  model?: string;
  dimension?: number;
  expected_dimension?: number;
  latency_ms?: number;
  similarities?: number[];
  preview?: number[];
  error?: string | null;
};

type BackfillResult = {
  job_id: string | null;
  candidates: number;
  enqueued: number;
  message: string;
};

const DEFAULT_QUERY = "Thủ tục đăng ký thường trú cần chuẩn bị những giấy tờ gì?";
const DEFAULT_PASSAGES = [
  "Hồ sơ đăng ký thường trú gồm tờ khai thay đổi thông tin cư trú và giấy tờ, tài liệu chứng minh chỗ ở hợp pháp của người đăng ký.",
  "Người điều khiển, người ngồi trên xe mô tô không đội mũ bảo hiểm khi tham gia giao thông sẽ bị phạt tiền theo quy định.",
  "Công dân có quyền tự do cư trú trên lãnh thổ Việt Nam theo quy định của Hiến pháp và pháp luật.",
].join("\n");
const MAX_PASSAGES = 8;

function errMsg(err: unknown, fallback: string): string {
  return err instanceof Error && err.message ? err.message : fallback;
}

function formatTime(iso?: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString("vi-VN", { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit" });
}

async function runEmbeddingTest(modelSpecId: string, query: string, passages: string[]): Promise<TestResult> {
  try {
    return await api<TestResult>("/api/settings/embeddings/test", {
      method: "POST",
      body: { model_spec_id: modelSpecId, query, passages },
    });
  } catch (err) {
    return { success: false, error: errMsg(err, "Request failed") };
  }
}

function MetricTile({
  icon,
  tone,
  title,
  value,
  sub,
}: {
  icon: string;
  tone: string;
  title: string;
  value: string;
  sub: string;
}) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-border/70 bg-background p-3.5">
      <div className={cn("flex size-9 shrink-0 items-center justify-center rounded-lg", tone)}>
        <span className="material-symbols-outlined text-[20px]">{icon}</span>
      </div>
      <div className="min-w-0">
        <p className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">{title}</p>
        <p className="truncate text-sm font-semibold text-foreground tabular-nums">{value}</p>
        <p className="truncate text-[11px] text-muted-foreground">{sub}</p>
      </div>
    </div>
  );
}

export function EmbeddingSettingsCard() {
  const { t } = useI18n();

  const [catalog, setCatalog] = useState<EmbeddingCatalog | null>(null);
  const [status, setStatus] = useState<EmbeddingStatus | null>(null);
  const [settings, setSettings] = useState<Record<string, unknown>>({});
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loadError, setLoadError] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [actionError, setActionError] = useState("");
  const [cancelling, setCancelling] = useState(false);

  const [backfilling, setBackfilling] = useState(false);
  const [forceBackfill, setForceBackfill] = useState(false);
  const [backfillNote, setBackfillNote] = useState<{ ok: boolean; text: string } | null>(null);

  const [pinging, setPinging] = useState(false);
  const [ping, setPing] = useState<{ id: string; res: TestResult } | null>(null);

  const [query, setQuery] = useState(DEFAULT_QUERY);
  const [passagesText, setPassagesText] = useState(DEFAULT_PASSAGES);
  const [testing, setTesting] = useState(false);
  const [test, setTest] = useState<{ id: string; res: TestResult; passages: string[] } | null>(null);

  async function refresh() {
    try {
      const [cat, st, s] = await Promise.all([
        api<EmbeddingCatalog>("/api/settings/embeddings/catalog"),
        api<EmbeddingStatus>("/api/settings/embeddings/status"),
        api<Record<string, unknown>>("/api/settings"),
      ]);
      setCatalog(cat);
      setStatus(st);
      setSettings(s);
      setLoadError("");
      setSelectedId((prev) => (prev && cat.specs.some((x) => x.id === prev) ? prev : cat.active_spec_id));
    } catch (err) {
      setLoadError(errMsg(err, "Load failed"));
    }
  }

  useEffect(() => {
    // Initial load only; later refreshes are triggered explicitly or by polling.
    // refresh() only sets state after awaiting the network, so no cascading render.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refresh();
  }, []);

  const job = status?.current_job ?? null;
  const jobBusy = !!job && (job.status === "pending" || job.status === "running");
  const polling = jobBusy || submitting || backfilling;

  useEffect(() => {
    if (!polling) return;
    const timer = setInterval(() => void refresh(), 2000);
    return () => clearInterval(timer);
  }, [polling]);

  if (!catalog || !status) {
    return (
      <div className="flex flex-col gap-1 rounded-2xl border border-border/80 bg-card p-6 shadow-lift">
        <p className="text-sm text-muted-foreground">Loading embedding catalog…</p>
        {loadError && <p className="text-xs text-destructive">{loadError}</p>}
      </div>
    );
  }

  const activeId = catalog.active_spec_id;
  const active = catalog.specs.find((s) => s.id === activeId) ?? null;
  const selected = catalog.specs.find((s) => s.id === selectedId) ?? null;
  const willSwitch = !!selected && selected.id !== activeId;

  const totalPages = status.total_pages ?? 0;
  const totalSources = status.total_sources ?? 0;
  const embeddedSources = status.embedded_sources ?? 0;
  const latest = status.latest_job ?? null;

  const pingShown = ping && ping.id === selectedId ? ping.res : null;
  const testShown = test && test.id === selectedId ? test : null;

  async function handleSwitch() {
    if (!selected) return;
    if (!window.confirm(`Chuyển sang ${selected.label} sẽ embed lại toàn bộ ${totalPages} trang wiki. Tiếp tục?`)) return;
    setSubmitting(true);
    setActionError("");
    try {
      await api<{ job_id: string }>("/api/settings/embeddings/switch", {
        method: "POST",
        body: { model_spec_id: selected.id },
      });
      await refresh();
    } catch (err) {
      setActionError(errMsg(err, "Switch failed"));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleReindex() {
    const label = active?.label ?? activeId ?? "";
    if (
      !window.confirm(
        `Xác nhận chạy lại toàn bộ embedding cho ${totalPages} trang wiki và ${totalSources} tài liệu theo model ${label}? Quá trình này sẽ chạy ngầm.`,
      )
    )
      return;
    setSubmitting(true);
    setActionError("");
    try {
      await api<{ job_id: string }>("/api/settings/embeddings/reindex-current", { method: "POST" });
      await refresh();
    } catch (err) {
      setActionError(errMsg(err, "Reindex failed"));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleCancel(jobId: string) {
    setCancelling(true);
    setActionError("");
    try {
      await api(`/api/settings/embeddings/jobs/${encodeURIComponent(jobId)}/cancel`, { method: "POST" });
      await refresh();
    } catch (err) {
      setActionError(errMsg(err, "Cancel failed"));
    } finally {
      setCancelling(false);
    }
  }

  async function handleBackfill() {
    setBackfilling(true);
    setBackfillNote(null);
    try {
      const res = await api<BackfillResult>(
        `/api/settings/embeddings/backfill-source-chunks?limit=500&force=${forceBackfill ? "true" : "false"}`,
        { method: "POST" },
      );
      const text =
        res.message ||
        (res.job_id ? t("settings.backfillQueued", "Đã xếp hàng job index chunk thô") : "Không có tài liệu nào cần xử lý");
      setBackfillNote({ ok: true, text });
      await refresh();
    } catch (err) {
      setBackfillNote({ ok: false, text: errMsg(err, "Backfill failed") });
    } finally {
      setBackfilling(false);
    }
  }

  async function handlePing() {
    if (!selected) return;
    const id = selected.id;
    setPinging(true);
    const res = await runEmbeddingTest(id, "ping", []);
    setPing({ id, res });
    setPinging(false);
  }

  async function handleTest() {
    if (!selected || !query.trim()) return;
    const id = selected.id;
    const passages = passagesText
      .split("\n")
      .map((p) => p.trim())
      .filter(Boolean)
      .slice(0, MAX_PASSAGES);
    setTesting(true);
    const res = await runEmbeddingTest(id, query.trim(), passages);
    setTest({ id, res, passages });
    setTesting(false);
  }

  const pct = job && job.total_pages > 0 ? Math.round((job.done_pages / job.total_pages) * 100) : 0;

  return (
    <div className="flex flex-col gap-5 rounded-2xl border border-border/80 bg-card p-6 shadow-lift">
      {/* Header */}
      <div className="flex flex-wrap items-start gap-3">
        <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
          <span className="material-symbols-outlined text-[20px]">data_array</span>
        </div>
        <div className="min-w-0 flex-1">
          <h2 className="text-base font-semibold tracking-tight text-foreground">
            {t("settings.embeddingTitle", "Embedding Model & Quản lý Vector")}
          </h2>
          <p className="text-xs text-muted-foreground">
            Đánh chỉ mục vector phục vụ tìm kiếm ngữ nghĩa cho toàn bộ bài viết Wiki và Tài liệu nguồn.
          </p>
        </div>
        <ActiveModelChip spec={active} />
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <MetricTile
          icon="psychology"
          tone="bg-primary/10 text-primary"
          title="Model Đang Dùng"
          value={active?.label ?? "Chưa kích hoạt"}
          sub={active ? `${active.dimension} chiều · ${active.group}` : "—"}
        />
        <MetricTile
          icon="menu_book"
          tone="bg-blue-500/10 text-blue-600 dark:text-blue-400"
          title="Bài Viết Wiki"
          value={`${status.embedded_pages ?? 0} / ${totalPages} trang`}
          sub={`${status.wiki_chunks_count ?? 0} vector chunks đã index`}
        />
        <MetricTile
          icon="folder_open"
          tone="bg-violet-500/10 text-violet-600 dark:text-violet-400"
          title="Tài Liệu Nguồn"
          value={`${embeddedSources} / ${totalSources} tài liệu`}
          sub={`${status.source_chunks_count ?? 0} chunk thô đã index`}
        />
      </div>

      {/* Job state */}
      {jobBusy && job ? (
        <div className="flex flex-col gap-2.5 rounded-xl border border-blue-500/25 bg-blue-500/5 p-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="material-symbols-outlined animate-spin text-lg text-blue-600 dark:text-blue-400">
              progress_activity
            </span>
            <span className="text-sm font-medium text-foreground">Đang tái đánh chỉ mục (Re-embedding)...</span>
            <span className="rounded border border-blue-500/30 bg-background px-1.5 font-mono text-[10px] text-blue-700 dark:text-blue-300">
              {job.model_spec_id}
            </span>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="ml-auto"
              disabled={cancelling}
              onClick={() => void handleCancel(job.id)}
            >
              Hủy tiến trình
            </Button>
          </div>
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>Tiến độ hoàn thành:</span>
            <span className="font-mono tabular-nums">
              {job.done_pages} / {job.total_pages} trang ({pct}%)
            </span>
          </div>
          <div className="h-2.5 overflow-hidden rounded-full bg-blue-500/15">
            <div className="h-full rounded-full bg-blue-600 transition-all dark:bg-blue-400" style={{ width: `${pct}%` }} />
          </div>
        </div>
      ) : latest?.status === "completed" ? (
        <div className="flex flex-wrap items-center gap-2 rounded-xl border border-emerald-500/25 bg-emerald-500/5 px-4 py-3 text-xs text-emerald-800 dark:text-emerald-300">
          <span className="material-symbols-outlined text-base">check_circle</span>
          <span className="flex-1">
            <strong>Đã hoàn tất embedding toàn bộ</strong> theo model {latest.model_spec_id} ({latest.done_pages}/
            {latest.total_pages} trang).
          </span>
          <span className="font-mono text-[11px] opacity-80">{formatTime(latest.finished_at)}</span>
        </div>
      ) : latest?.status === "failed" ? (
        <div className="flex flex-wrap items-center gap-2 rounded-xl border border-destructive/25 bg-destructive/5 px-4 py-3 text-xs text-destructive">
          <span className="material-symbols-outlined text-base">error</span>
          <span className="flex-1">
            <strong>Lần embedding gần nhất thất bại:</strong> {latest.error_message || "Lỗi không xác định"}
          </span>
          <span className="font-mono text-[11px] opacity-80">{formatTime(latest.finished_at)}</span>
        </div>
      ) : null}

      {/* Picker */}
      <ProviderModelPicker
        kind="embedding"
        specs={catalog.specs}
        activeId={activeId}
        selectedId={selectedId}
        onSelect={setSelectedId}
        settings={settings}
        onChanged={refresh}
        disabled={jobBusy}
        renderMeta={(spec) => (spec.cost_per_1m_tokens != null ? `$${spec.cost_per_1m_tokens}/1M tokens` : "")}
      />

      {/* Actions */}
      <div className="flex flex-col gap-2 border-t border-border/60 pt-3">
        <div className="flex flex-wrap items-center gap-2">
          {willSwitch && selected ? (
            <Button
              type="button"
              size="sm"
              className="h-9 gap-1.5"
              disabled={jobBusy || submitting || !canActivate(selected)}
              onClick={() => void handleSwitch()}
            >
              <span className={cn("material-symbols-outlined text-base", submitting && "animate-spin")}>
                {submitting ? "progress_activity" : "swap_horiz"}
              </span>
              {submitting ? "Đang chuyển & xếp hàng…" : `Chuyển sang ${selected.label} & Embed lại`}
            </Button>
          ) : (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-9 gap-1.5"
              title="Chạy lại vector embedding cho tất cả bài viết wiki và tài liệu nguồn theo model đang dùng"
              disabled={jobBusy || submitting}
              onClick={() => void handleReindex()}
            >
              <span className={cn("material-symbols-outlined text-base", submitting && "animate-spin")}>
                {submitting ? "progress_activity" : "restart_alt"}
              </span>
              {submitting ? "Đang xếp hàng…" : "Embed lại toàn bộ dữ liệu"}
            </Button>
          )}
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="gap-1"
            title="Embed thử 1 câu ngắn bằng model đang chọn"
            disabled={pinging || !selected}
            onClick={() => void handlePing()}
          >
            <span className={cn("material-symbols-outlined text-sm", pinging && "animate-spin")}>
              {pinging ? "progress_activity" : "network_ping"}
            </span>
            Kiểm tra Ping
          </Button>
          {pingShown &&
            (pingShown.success && pingShown.dimension === pingShown.expected_dimension ? (
              <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/40 px-2 py-0.5 text-[11px] text-emerald-600 dark:text-emerald-400">
                <span className="material-symbols-outlined text-sm">check_circle</span>
                OK · {pingShown.dimension} chiều · {pingShown.latency_ms}ms
              </span>
            ) : (
              <span className="inline-flex max-w-full items-center gap-1 rounded-full border border-destructive/40 px-2 py-0.5 text-[11px] text-destructive">
                <span className="material-symbols-outlined text-sm">error</span>
                <span className="truncate">
                  {pingShown.success
                    ? `Trả về ${pingShown.dimension}d (kỳ vọng ${pingShown.expected_dimension}d)`
                    : pingShown.error || "Embedding thất bại"}
                </span>
              </span>
            ))}
          {!willSwitch && (
            <span className="ml-auto inline-flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400">
              <span className="material-symbols-outlined text-sm">verified</span>
              Model đang chọn là model đang hoạt động
            </span>
          )}
        </div>
        {actionError && <p className="text-xs text-destructive">{actionError}</p>}
        <p className="text-[11px] text-muted-foreground">
          Đổi model embedding luôn chạy lại toàn bộ vector vì số chiều có thể khác (hỗ trợ 768, 1024, 1536, 3072). Trong
          lúc tiến trình chạy, danh sách model bị khóa.
        </p>
      </div>

      {/* Raw source chunks */}
      <div className="flex flex-col gap-3 rounded-xl border border-border/70 bg-muted/10 p-4">
        <div className="flex flex-wrap items-start gap-2">
          <span className="material-symbols-outlined text-lg text-primary">segment</span>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-foreground">Tách đoạn &amp; Index Chunk thô cho Tài liệu nguồn</p>
            <p className="text-xs text-muted-foreground">
              Tạo các đoạn văn thô kèm phân cấp tiêu đề từ tài liệu tải lên để phục vụ tra cứu văn bản song song.
            </p>
          </div>
          <span className="hidden text-xs text-muted-foreground sm:inline">
            Đã index:{" "}
            <strong className="text-foreground">
              {embeddedSources}/{totalSources}
            </strong>{" "}
            tài liệu
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="gap-1"
            disabled={backfilling || jobBusy}
            onClick={() => void handleBackfill()}
          >
            <span className="material-symbols-outlined text-sm">play_arrow</span>
            {backfilling
              ? t("settings.backfillingChunks", "Đang xếp hàng...")
              : t("settings.backfillChunks", "Index chunk thô cho tài liệu cũ")}
          </Button>
          <label className="flex cursor-pointer items-center gap-2 text-xs text-foreground">
            <Checkbox checked={forceBackfill} onCheckedChange={setForceBackfill} />
            Buộc chạy lại tất cả (Force re-index)
          </label>
        </div>
        {backfillNote &&
          (backfillNote.ok ? (
            <div className="flex items-start gap-2 rounded-lg border border-primary/25 bg-primary/5 px-3 py-2 text-xs text-foreground">
              <span className="material-symbols-outlined text-sm text-primary">info</span>
              {backfillNote.text}
            </div>
          ) : (
            <p className="text-xs text-destructive">{backfillNote.text}</p>
          ))}
      </div>

      {/* Test lab */}
      <div className="rounded-xl border border-border/70 bg-muted/10 p-4">
        <div className="mb-3 flex items-center justify-between gap-2">
          <span className="flex items-center gap-1.5 text-xs font-semibold tracking-wider text-muted-foreground uppercase">
            <span className="material-symbols-outlined text-sm text-primary">science</span>
            Thử embedding
          </span>
          {selected && (
            <span className="truncate text-[11px] text-muted-foreground">
              Model thử: <span className="font-medium text-foreground">{selected.label}</span>
            </span>
          )}
        </div>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
          <div className="flex flex-col gap-3 lg:col-span-5">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="embedding-test-query" className="text-xs">
                Câu hỏi
              </Label>
              <Input
                id="embedding-test-query"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                className="bg-background text-xs"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="embedding-test-passages" className="text-xs">
                Đoạn văn so sánh (mỗi dòng 1 đoạn, tối đa {MAX_PASSAGES})
              </Label>
              <Textarea
                id="embedding-test-passages"
                rows={6}
                value={passagesText}
                onChange={(e) => setPassagesText(e.target.value)}
                className="bg-background text-xs"
              />
            </div>
            <Button
              type="button"
              size="sm"
              className="h-9 w-full gap-2 text-xs"
              disabled={testing || !selected || !query.trim()}
              onClick={() => void handleTest()}
            >
              <span className={cn("material-symbols-outlined text-sm", testing && "animate-spin")}>
                {testing ? "progress_activity" : "compare_arrows"}
              </span>
              {testing ? "Đang embed..." : "Chạy so khớp"}
            </Button>
          </div>

          <div className="min-h-[220px] rounded-xl border border-border bg-background p-4 lg:col-span-7">
            <EmbeddingTestResult shown={testShown} />
          </div>
        </div>
      </div>
    </div>
  );
}

function EmbeddingTestResult({ shown }: { shown: { res: TestResult; passages: string[] } | null }) {
  if (!shown) {
    return (
      <div className="flex h-full min-h-[190px] flex-col items-center justify-center gap-2 text-center text-xs text-muted-foreground">
        <span className="material-symbols-outlined text-3xl opacity-40">scatter_plot</span>
        Chạy thử để xem độ tương đồng cosine giữa câu hỏi và từng đoạn.
      </div>
    );
  }
  const { res, passages } = shown;
  if (!res.success) {
    return (
      <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 font-mono text-xs break-all text-destructive">
        {res.error || "Embedding thất bại"}
      </div>
    );
  }

  const mismatch = res.expected_dimension != null && res.dimension !== res.expected_dimension;
  const sims = res.similarities ?? [];
  const ranked = passages
    .map((text, i) => ({ text, score: sims[i] ?? 0 }))
    .sort((a, b) => b.score - a.score);
  const preview = res.preview ?? [];

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[11px] text-muted-foreground">
        <span className={cn(mismatch && "text-destructive")}>
          <Stat icon="data_array">
            {res.dimension} chiều{mismatch ? ` (cấu hình ${res.expected_dimension})` : ""}
          </Stat>
        </span>
        <Stat icon="timer">{res.latency_ms ?? 0} ms</Stat>
        <Stat icon="memory">
          <span className="font-mono">{res.model}</span>
        </Stat>
      </div>

      {ranked.length === 0 ? (
        <p className="text-xs text-muted-foreground">Không có đoạn văn để so sánh.</p>
      ) : (
        <ul className="flex flex-col gap-2.5">
          {ranked.map((row, i) => {
            const width = Math.max(0, Math.min(1, row.score)) * 100;
            return (
              <li key={`${i}-${row.text}`} className="flex flex-col gap-1">
                <div className="flex items-start justify-between gap-3">
                  <p
                    className={cn(
                      "line-clamp-2 text-xs",
                      i === 0 ? "font-semibold text-foreground" : "text-muted-foreground",
                    )}
                  >
                    {row.text}
                  </p>
                  <span className="shrink-0 font-mono text-xs tabular-nums text-foreground">{row.score.toFixed(4)}</span>
                </div>
                <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                  <div
                    className={cn("h-full rounded-full", i === 0 ? "bg-primary" : "bg-primary/40")}
                    style={{ width: `${width}%` }}
                  />
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {preview.length > 0 && (
        <p className="truncate font-mono text-[10px] text-muted-foreground">
          [{preview.map((v) => v.toFixed(4)).join(", ")}, …]
        </p>
      )}
    </div>
  );
}
