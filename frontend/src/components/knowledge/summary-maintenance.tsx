"use client";

import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import { DropdownMenuGroup, DropdownMenuItem, DropdownMenuLabel } from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { SummaryJobDetailsDialog } from "./summary-job-details";
import { isSummaryJobActive, isSummaryJobWarning, type SummaryJob } from "./summary-job-state";
import { useSummaryMaintenance } from "./use-summary-maintenance";
import { summaryJobPresentation } from "./summary-job-view";

export { useSummaryMaintenance };
export type { SummaryJob };

/** Shared by the source processing menu and the Wiki library's contextual menu. */
export function SummaryMaintenanceMenuGroup({ maintenance }: { maintenance: ReturnType<typeof useSummaryMaintenance> }) {
  return <DropdownMenuGroup>
    <DropdownMenuLabel>Tóm tắt Wiki bằng AI</DropdownMenuLabel>
    <DropdownMenuItem disabled={maintenance.busy || maintenance.counts?.needs_update === 0} onClick={() => void maintenance.start(true)}>
      <span aria-hidden="true" className="material-symbols-outlined text-[17px]!">short_text</span><span className="flex-1">AI tạo tóm tắt thiếu / bị cắt</span>
      <span className="ml-auto pl-3 text-xs tabular-nums text-muted-foreground">{maintenance.counts?.needs_update ?? "…"}</span>
    </DropdownMenuItem>
    <DropdownMenuItem disabled={maintenance.busy || maintenance.counts?.total === 0} onClick={() => void maintenance.start(false)}>
      <span aria-hidden="true" className="material-symbols-outlined text-[17px]!">refresh</span><span className="flex-1">AI tạo lại toàn bộ tóm tắt</span>
      <span className="ml-auto pl-3 text-xs tabular-nums text-muted-foreground">{maintenance.counts?.total ?? "…"}</span>
    </DropdownMenuItem>
    {maintenance.recentJob && <DropdownMenuItem onClick={(event) => maintenance.openDetails(maintenance.recentJob, event.currentTarget)}>
      <span aria-hidden="true" className="material-symbols-outlined text-[17px]!">history</span><span className="flex-1">{isSummaryJobActive(maintenance.recentJob) ? "Xem tiến trình đang chạy" : "Kết quả cập nhật gần nhất"}</span>
      {isSummaryJobWarning(maintenance.recentJob) && <span className="text-xs text-amber-600 dark:text-amber-400">Có lỗi</span>}
    </DropdownMenuItem>}
    {!!maintenance.counts?.source_matches_count && <DropdownMenuItem onClick={maintenance.openSourceNotes}><span aria-hidden="true" className="material-symbols-outlined text-[17px]!">info</span><span className="flex-1">Trang có dấu ... trong nội dung Wiki</span><span className="ml-auto pl-3 text-xs tabular-nums text-muted-foreground">{maintenance.counts.source_matches_count}</span></DropdownMenuItem>}
  </DropdownMenuGroup>;
}

export function SummaryJobProgress({ job, error, onDismiss, onDetails, onRetry, detailsOpen = false }: {
  job: SummaryJob | null; error: string | null; onDismiss: () => void;
  onDetails: (trigger?: HTMLElement | null) => void; onRetry: () => void; detailsOpen?: boolean;
}) {
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const running = isSummaryJobActive(job);
  const warning = !!error || isSummaryJobWarning(job);
  const jobId = job?.job_id;
  useEffect(() => {
    if (!jobId || running || warning || hovered || focused || detailsOpen) return;
    const timer = setTimeout(onDismiss, 6000);
    return () => clearTimeout(timer);
  }, [jobId, running, warning, hovered, focused, detailsOpen, onDismiss]);
  if (!job && !error) return null;
  const presentation = job ? summaryJobPresentation(job) : null;
  const percent = job?.total ? Math.min(100, Math.round(job.processed / job.total * 100)) : 0;
  const title = !job ? "Không tải được trạng thái tóm tắt" : running
    ? `${presentation?.label} cập nhật tóm tắt` : warning ? "Tóm tắt có mục cần kiểm tra"
      : job.total === 0 ? "Không có trang cần cập nhật" : "Đã hoàn tất cập nhật tóm tắt";
  return <section aria-label="Trạng thái cập nhật tóm tắt"
    onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}
    onFocusCapture={() => setFocused(true)} onBlurCapture={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setFocused(false); }}
    className={cn("relative overflow-hidden rounded-lg border px-3 py-2.5 text-sm", warning ? "border-amber-500/30 bg-amber-500/5" : "border-border/70 bg-muted/20")}>
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
      <span aria-hidden="true" className={cn("material-symbols-outlined text-[18px]!", running ? "animate-spin text-primary motion-reduce:animate-none" : warning ? "text-amber-600 dark:text-amber-400" : "text-emerald-700 dark:text-emerald-400")}>{running ? "progress_activity" : warning ? "info" : "check_circle"}</span>
      <div className="min-w-0 flex-1 basis-44" role="status" aria-live="polite">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1"><p className="font-medium">{title}</p>{job && job.total > 0 && <span className="text-xs tabular-nums text-muted-foreground">{job.processed}/{job.total} trang{!running && job.updated > 0 ? ` · Cập nhật ${job.updated}` : ""}</span>}</div>
        {error ? <p className="mt-0.5 break-words text-xs text-destructive">{error}</p>
          : warning && job ? <p className="mt-0.5 break-words text-xs text-muted-foreground">{job.message}{job.index_failed > 0 ? ` · ${job.index_failed} trang chưa cập nhật được chỉ mục` : ""}</p>
            : running && job?.current ? <p className="mt-0.5 truncate text-xs text-muted-foreground" title={job.current.title}>{job.current.title} · {job.current.message}</p> : null}
      </div>
      <div className="ml-auto flex items-center gap-1">
        {error && <Button variant="ghost" size="sm" onClick={onRetry}>Thử lại</Button>}
        {job && <Button variant="ghost" size="sm" onClick={(event) => onDetails(event.currentTarget)}>{running ? "Xem tiến trình" : "Xem kết quả"}<span aria-hidden="true" className="material-symbols-outlined text-[16px]!">arrow_forward</span></Button>}
        {!running && <Button variant="ghost" size="icon-sm" aria-label="Đóng thông báo tóm tắt" onClick={onDismiss}><span aria-hidden="true" className="material-symbols-outlined text-[16px]!">close</span></Button>}
      </div>
    </div>
    {running && <div role="progressbar" aria-label="Tiến độ cập nhật tóm tắt" aria-valuemin={0} aria-valuemax={100}
      aria-valuenow={job?.total ? percent : undefined} aria-valuetext={job?.total ? `${job.processed}/${job.total} trang` : "Đang chờ xử lý"} className="absolute inset-x-0 bottom-0 h-0.5 bg-muted">
      <div className="h-full bg-primary transition-[width] duration-300 motion-reduce:transition-none" style={{ width: `${percent}%` }} />
    </div>}
  </section>;
}

export function SummarySourceNotes({ maintenance }: { maintenance: ReturnType<typeof useSummaryMaintenance> }) {
  return <>
    {maintenance.detailsOpen && maintenance.detailsJob && <SummaryJobDetailsDialog key={maintenance.detailsJob.job_id} job={maintenance.detailsJob} onClose={maintenance.closeDetails} returnFocus={maintenance.detailsReturnFocus} />}
    {maintenance.sourceNotesOpen && <SummaryJobDetailsDialog knownItems={maintenance.counts?.source_matches ?? []} onClose={maintenance.closeSourceNotes} returnFocus={maintenance.detailsReturnFocus} />}
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
    <div className="flex flex-wrap items-center justify-end gap-x-3 gap-y-2">
      {maintenance.recentJob && <Button data-summary-result-trigger variant="link" size="sm" className="text-muted-foreground" onClick={(event) => maintenance.openDetails(maintenance.recentJob, event.currentTarget)}>{isSummaryJobActive(maintenance.recentJob) ? "Xem tiến trình" : "Kết quả cập nhật gần nhất"}</Button>}
      <Button variant="outline" size="sm" disabled={maintenance.busy} onClick={() => void maintenance.start(false, [pageId])}><span aria-hidden className="material-symbols-outlined text-[16px]!">auto_awesome</span>{maintenance.busy ? "AI đang xử lý…" : "Tóm tắt trang bằng AI"}</Button>
    </div>
    <SummaryJobProgress job={maintenance.job} error={maintenance.error} onDismiss={maintenance.dismiss} onRetry={() => void maintenance.refresh()} onDetails={(trigger) => maintenance.openDetails(maintenance.job, trigger)} detailsOpen={maintenance.detailsOpen} />
    <SummarySourceNotes maintenance={maintenance} />
  </div>;
}
