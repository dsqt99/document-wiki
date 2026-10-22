"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import { DropdownMenuGroup, DropdownMenuItem, DropdownMenuLabel } from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { SummaryJobDetailsDialog, type SummaryJobItem } from "./summary-job-details";

export type SummaryJob = {
  job_id: string;
  status: "queued" | "running" | "completed" | "failed";
  only_missing: boolean;
  engine?: "llm" | "extract";
  total: number;
  processed: number;
  updated: number;
  failed: number;
  index_failed: number;
  message: string;
  errors: string[];
  unchanged?: number;
  skipped?: number;
  current?: Pick<SummaryJobItem, "page_id" | "title" | "slug" | "scope_type" | "scope_id" | "stage" | "status" | "message"> | null;
};

type SummaryCounts = { total: number; needs_update: number; active_job: SummaryJob | null; recent_job?: SummaryJob | null; source_matches_count?: number; source_matches?: SummaryJobItem[] };
const active = (job: SummaryJob | null) => !!job && (job.status === "queued" || job.status === "running");

export function useSummaryMaintenance(enabled: boolean, onComplete: () => void) {
  const [counts, setCounts] = useState<SummaryCounts | null>(null);
  const [job, setJob] = useState<SummaryJob | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sourceNotesOpen, setSourceNotesOpen] = useState(false);
  const [confirmAllOpen, setConfirmAllOpen] = useState(false);
  const completed = useRef(new Set<string>());
  const submitting = useRef(false);

  const acceptJob = useCallback((next: SummaryJob) => {
    setJob(next);
    if (!active(next) && !completed.current.has(next.job_id)) {
      completed.current.add(next.job_id);
      onComplete();
    }
  }, [onComplete]);

  const refresh = useCallback(async () => {
    if (!enabled) return;
    try {
      const next = await api<SummaryCounts>("/api/wiki/summaries/status");
      setCounts(next);
      if (next.active_job || next.recent_job) acceptJob((next.active_job || next.recent_job)!);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không tải được trạng thái tóm tắt.");
    }
  }, [enabled, acceptJob]);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    api<SummaryCounts>("/api/wiki/summaries/status").then((next) => {
      if (cancelled) return;
      setCounts(next);
      if (next.active_job || next.recent_job) acceptJob((next.active_job || next.recent_job)!);
    }).catch((err: unknown) => {
      if (!cancelled) setError(err instanceof Error ? err.message : "Không tải được trạng thái tóm tắt.");
    });
    return () => { cancelled = true; };
  }, [enabled, acceptJob]);

  const jobId = active(job) ? job?.job_id : null;
  useEffect(() => {
    if (!enabled || !jobId) return;
    let cancelled = false;
    const timer = setInterval(() => {
      api<SummaryJob>(`/api/wiki/summaries/jobs/${encodeURIComponent(jobId)}`).then((next) => {
        if (cancelled) return;
        acceptJob(next);
        setError(null);
        if (!active(next)) void refresh();
      }).catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Không đọc được tiến độ. Đang thử lại...");
        if (err instanceof ApiError && err.status === 404) {
          setJob((previous) => previous && previous.job_id === jobId
            ? { ...previous, status: "failed", message: "Thông tin tác vụ đã hết hạn. Vui lòng kiểm tra và chạy lại." }
            : previous);
        }
      });
    }, 2000);
    return () => { cancelled = true; clearInterval(timer); };
  }, [enabled, jobId, acceptJob, refresh]);

  const start = async (onlyMissing: boolean, pageIds?: string[], confirmed = false) => {
    if (!enabled || submitting.current || active(job)) return;
    if (!onlyMissing && !pageIds && !confirmed) { setConfirmAllOpen(true); return; }
    setConfirmAllOpen(false);
    submitting.current = true;
    setStarting(true);
    setError(null);
    try {
      const next = await api<SummaryJob>("/api/wiki/summaries/rebuild", {
        method: "POST", body: { only_missing: onlyMissing, engine: "llm", ...(pageIds ? { page_ids: pageIds } : {}) },
      });
      acceptJob(next);
      if (!active(next)) void refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không chạy được tác vụ tóm tắt.");
    } finally {
      submitting.current = false;
      setStarting(false);
    }
  };

  return { counts, job: enabled ? job : null, error: enabled ? error : null,
    confirmAllOpen, closeConfirmation: () => setConfirmAllOpen(false), confirmAll: () => start(false, undefined, true),
    busy: starting || active(job), refresh, start, sourceNotesOpen, openSourceNotes: () => setSourceNotesOpen(true), closeSourceNotes: () => setSourceNotesOpen(false), dismiss: () => { setJob(null); setError(null); } };
}

/** Shared by the source processing menu and the Wiki library's contextual menu. */
export function SummaryMaintenanceMenuGroup({ maintenance }: { maintenance: ReturnType<typeof useSummaryMaintenance> }) {
  return (
    <DropdownMenuGroup>
      <DropdownMenuLabel>Tóm tắt Wiki bằng AI</DropdownMenuLabel>
      <DropdownMenuItem disabled={maintenance.busy || maintenance.counts?.needs_update === 0} onClick={() => void maintenance.start(true)}>
        <span aria-hidden="true" className="material-symbols-outlined text-[17px]!">short_text</span>
        <span className="flex-1">AI tạo tóm tắt thiếu / bị cắt</span>
        <span className="ml-auto pl-3 text-xs tabular-nums text-muted-foreground">{maintenance.counts?.needs_update ?? "…"}</span>
      </DropdownMenuItem>
      <DropdownMenuItem disabled={maintenance.busy || maintenance.counts?.total === 0} onClick={() => void maintenance.start(false)}>
        <span aria-hidden="true" className="material-symbols-outlined text-[17px]!">refresh</span>
        <span className="flex-1">AI tạo lại toàn bộ tóm tắt</span>
        <span className="ml-auto pl-3 text-xs tabular-nums text-muted-foreground">{maintenance.counts?.total ?? "…"}</span>
      </DropdownMenuItem>
      {!!maintenance.counts?.source_matches_count && <DropdownMenuItem onClick={maintenance.openSourceNotes}><span aria-hidden="true" className="material-symbols-outlined text-[17px]!">info</span><span className="flex-1">Trang có dấu ... trong nội dung Wiki</span><span className="ml-auto pl-3 text-xs tabular-nums text-muted-foreground">{maintenance.counts.source_matches_count}</span></DropdownMenuItem>}
    </DropdownMenuGroup>
  );
}

export function SummaryJobProgress({ job, error, onDismiss }: {
  job: SummaryJob | null; error: string | null; onDismiss: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  if (!job && !error) return null;
  const running = active(job);
  const warning = !!error || job?.status === "failed" || !!job?.failed || !!job?.index_failed;
  const percent = job?.total ? Math.min(100, Math.round(job.processed / job.total * 100)) : 0;
  return (
    <div className={cn("rounded-xl border px-4 py-3 text-sm", warning ? "border-amber-500/30 bg-amber-500/5" : "bg-muted/30")}>
      <div className="flex items-start gap-3" role="status" aria-live="polite">
        <span className={cn("material-symbols-outlined mt-0.5 text-primary", running && "animate-spin")} style={{ fontSize: 19 }}>
          {running ? "progress_activity" : warning ? "info" : "check_circle"}
        </span>
        <div className="min-w-0 flex-1">
          <p className="font-medium">{job?.message || "Không tải được trạng thái tóm tắt"}</p>
          {job && <p className="mt-1 text-xs text-muted-foreground">
            {job.engine === "llm" && "AI · "}
            {job.status === "queued" ? `Đang chờ xử lý ${job.total} trang` : `Đã xử lý ${job.processed}/${job.total} · Cập nhật ${job.updated}`}
            {!!job.failed && ` · Lỗi ${job.failed} trang`}
            {!!job.unchanged && ` · Đã khớp ${job.unchanged}`}
            {!!job.skipped && ` · Bỏ qua ${job.skipped}`}
            {!!job.index_failed && ` · ${job.index_failed} trang đã lưu tóm tắt, chưa cập nhật được chỉ mục tìm kiếm`}
          </p>}
          {error && <p className="mt-1 text-xs text-destructive">{error}</p>}
          {running && job?.current && <p className="mt-1 truncate text-xs text-muted-foreground" title={job.current.title}>Đang xử lý: {job.current.title} · {job.current.message}</p>}
        </div>
        {job && <Button variant="outline" size="sm" aria-label="Mở rộng chi tiết tiến trình tóm tắt" onClick={() => setExpanded(true)}><span aria-hidden className="material-symbols-outlined text-[16px]">open_in_full</span>Mở rộng</Button>}
        {!running && <button type="button" aria-label="Đóng thông báo tóm tắt" onClick={onDismiss}
          className="rounded p-1 text-muted-foreground hover:bg-muted focus-visible:outline-2 focus-visible:outline-ring">
          <span className="material-symbols-outlined" style={{ fontSize: 16 }}>close</span>
        </button>}
      </div>
      {running && <div role="progressbar" aria-label="Tiến độ cập nhật tóm tắt" aria-valuemin={0} aria-valuemax={100}
        aria-valuenow={percent} className="mt-3 h-1.5 overflow-hidden rounded-full bg-muted">
        <div className="h-full rounded-full bg-primary transition-[width] duration-300" style={{ width: `${percent}%` }} />
      </div>}
      {expanded && job && <SummaryJobDetailsDialog key={job.job_id} job={job} onClose={() => setExpanded(false)} />}
    </div>
  );
}

export function SummarySourceNotes({ maintenance }: { maintenance: ReturnType<typeof useSummaryMaintenance> }) {
  return <>
    {maintenance.sourceNotesOpen && <SummaryJobDetailsDialog knownItems={maintenance.counts?.source_matches ?? []} onClose={maintenance.closeSourceNotes} />}
    <Dialog open={maintenance.confirmAllOpen} onOpenChange={(open) => { if (!open) maintenance.closeConfirmation(); }}>
      <DialogContent className="sm:max-w-lg">
        <DialogTitle>Tạo lại tóm tắt bằng AI?</DialogTitle>
        <DialogDescription>Mô hình AI đã cấu hình sẽ đọc toàn bộ nội dung của {maintenance.counts?.total ?? "tất cả"} trang Wiki và thay thế các tóm tắt hiện có. Trang dài được chia phần rồi tổng hợp; có thể theo dõi từng trang trong chi tiết tiến trình.</DialogDescription>
        <div className="flex justify-end gap-2"><Button variant="outline" onClick={maintenance.closeConfirmation}>Hủy</Button><Button disabled={maintenance.busy} onClick={() => void maintenance.confirmAll()}>Tạo lại bằng AI</Button></div>
      </DialogContent>
    </Dialog>
  </>;
}

export function WikiPageSummaryAI({ pageId, onComplete }: { pageId: string; onComplete: () => void }) {
  const maintenance = useSummaryMaintenance(true, onComplete);
  return <div className="space-y-3">
    <div className="flex justify-end"><Button variant="outline" size="sm" disabled={maintenance.busy} onClick={() => void maintenance.start(false, [pageId])}><span aria-hidden className="material-symbols-outlined text-[16px]">auto_awesome</span>{maintenance.busy ? "AI đang xử lý…" : "Tóm tắt trang bằng AI"}</Button></div>
    <SummaryJobProgress job={maintenance.job} error={maintenance.error} onDismiss={maintenance.dismiss} />
  </div>;
}
