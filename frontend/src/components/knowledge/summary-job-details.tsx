"use client";

import { useEffect, useRef, useState } from "react";
import { OptionSelect } from "@/components/ui/option-select";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import { SummaryJobResults, SUMMARY_ITEM_LABELS, SUMMARY_ITEM_STAGES } from "./summary-job-results";
import { summaryDetailControls, summaryJobPresentation, summaryJobEmptyMessage } from "./summary-job-view";
import type { SummaryJob } from "./summary-maintenance";

export type SummaryJobItem = {
  page_id: string; title: string; slug: string; scope_type: string; scope_id?: string | null;
  source_titles: string[]; status: string; stage: string; message: string; updated_at: number;
};
type DetailResult = { items: SummaryJobItem[]; total: number; counts: Record<string, number>; details_available: boolean };
const LIMIT = 50;

export function SummaryJobDetailsDialog({ job, knownItems, onClose, returnFocus }: {
  job?: SummaryJob | null; knownItems?: SummaryJobItem[]; onClose: () => void;
  returnFocus?: () => HTMLElement | null | false;
}) {
  const titleRef = useRef<HTMLHeadingElement>(null);
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [tick, setTick] = useState(0);
  const [response, setResponse] = useState<{ key: string; data: DetailResult } | null>(null);
  const [fetchError, setFetchError] = useState<{ key: string; message: string } | null>(null);
  const jobId = job?.job_id;
  const presentation = job ? summaryJobPresentation(job) : null;
  const running = !!presentation?.running;
  useEffect(() => {
    const timer = setTimeout(() => { setQuery(search.trim()); setOffset(0); }, 300);
    return () => clearTimeout(timer);
  }, [search]);
  useEffect(() => {
    if (!running || !jobId) return;
    const timer = setInterval(() => setTick((value) => value + 1), 2000);
    return () => clearInterval(timer);
  }, [running, jobId]);
  const key = `${jobId}:${offset}:${status}:${query}`;
  const error = fetchError?.key === key ? fetchError.message : null;
  useEffect(() => {
    if (!jobId || knownItems) return;
    let active = true;
    const params = new URLSearchParams({ offset: String(offset), limit: String(LIMIT) });
    if (status) params.set("status", status);
    if (query) params.set("q", query);
    api<DetailResult>(`/api/wiki/summaries/jobs/${encodeURIComponent(jobId)}/items?${params}`)
      .then((data) => { if (active) { setResponse({ key, data }); setFetchError(null); } })
      .catch((err: unknown) => {
        if (!active) return;
        const message = err instanceof ApiError && err.status === 404
          ? "Chi tiết tác vụ đã hết hạn lưu. Bạn có thể đóng cửa sổ này và kiểm tra tóm tắt trên trang Wiki."
          : err instanceof Error ? err.message : "Không tải được chi tiết. Hãy thử làm mới.";
        setFetchError({ key, message });
      });
    return () => { active = false; };
  }, [jobId, knownItems, offset, status, query, key, tick, running]);
  const local = knownItems?.filter((item) => (!status || item.status === status) && `${item.title} ${item.slug} ${item.source_titles.join(" ")}`.toLocaleLowerCase("vi").includes(query.toLocaleLowerCase("vi")));
  const data: DetailResult | null = knownItems ? { items: local!.slice(offset, offset + LIMIT), total: local!.length, counts: {}, details_available: true } : response?.key === key ? response.data : null;
  const controls = summaryDetailControls({ total: data?.total, fullTotal: knownItems?.length ?? job?.total ?? data?.total,
    offset, query: search, status, running, error: !!error });
  return <Dialog open onOpenChange={(open) => { if (!open) onClose(); }}>
    <DialogContent initialFocus={titleRef} finalFocus={returnFocus}
      className={cn("flex max-h-[85dvh] flex-col gap-0 overflow-hidden p-0", controls.compact ? "sm:max-w-2xl" : "sm:max-w-5xl")}>
      <div className="space-y-3 border-b px-5 py-4 pr-12">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <DialogTitle ref={titleRef} tabIndex={-1} className="outline-none">{knownItems ? "Các trang có dấu ... trong nội dung Wiki" : presentation?.title}</DialogTitle>
          {presentation && <span className={cn("inline-flex items-center gap-1.5 text-xs", presentation.warning ? "text-amber-600 dark:text-amber-400" : running ? "text-primary" : "text-emerald-700 dark:text-emerald-400")}><span aria-hidden className="h-1.5 w-1.5 rounded-full bg-current" />{presentation.label}</span>}
        </div>
        <DialogDescription>{knownItems ? "Các trang này đã có tóm tắt khớp nội dung Wiki. Kiểm tra tệp gốc và nội dung trích xuất nếu bạn cho rằng còn thiếu đoạn văn." : presentation?.description}</DialogDescription>
        {presentation && <dl className="flex flex-wrap gap-x-5 gap-y-1 text-xs">{presentation.metrics.map(({ label, value }) => <div key={label} className="flex items-baseline gap-1.5"><dt className="text-muted-foreground">{label}</dt><dd className="font-medium tabular-nums">{value}</dd></div>)}</dl>}
        {job?.current && running && <p className="break-words text-xs text-muted-foreground"><strong className="font-medium text-foreground">{job.current.title}</strong> · {SUMMARY_ITEM_STAGES[job.current.stage] || job.current.stage}</p>}
      </div>
      {(controls.filters || (!knownItems && controls.refresh)) && <div className="flex flex-wrap items-center gap-2 border-b px-5 py-3">
        {controls.filters && <><Input className="min-w-40 flex-1" aria-label="Tìm trang hoặc văn bản trong kết quả" placeholder="Tìm trang hoặc văn bản…" value={search} onChange={(event) => setSearch(event.target.value)} />
          <OptionSelect aria-label="Lọc trạng thái xử lý tóm tắt" className="h-8 max-w-full rounded-md border bg-background px-2 text-sm" value={status} onValueChange={(value) => { setStatus(value); setOffset(0); }}><option value="">Tất cả trạng thái</option>{Object.entries(SUMMARY_ITEM_LABELS).map(([value, label]) => <option key={value} value={value}>{label}{data?.counts[value] ? ` (${data.counts[value]})` : ""}</option>)}</OptionSelect></>}
        {!knownItems && controls.refresh && <Button variant="outline" size="sm" onClick={() => setTick((value) => value + 1)}><span aria-hidden className="material-symbols-outlined text-[16px]!">refresh</span>Làm mới</Button>}
      </div>}
      <div className="min-h-20 flex-1 overflow-auto">
        {job && presentation?.warning && <div role="alert" className="mx-5 mt-4 space-y-1 rounded-md bg-amber-500/10 px-3 py-2 text-xs leading-5 text-amber-800 dark:text-amber-300">
          <p>{job.message || "Một số trang chưa được cập nhật. Kiểm tra chi tiết trước khi chạy lại."}</p>
          {!!job.errors?.length && <ul className="list-disc space-y-1 break-words pl-4">{job.errors.map((message, index) => <li key={index}>{message}</li>)}</ul>}
        </div>}
        {error && <p role="alert" className="px-5 py-4 text-sm text-destructive">{error}</p>}
        {!data && !error ? <div className="space-y-2 px-5 py-5" role="status" aria-label="Đang tải chi tiết"><div className="h-4 w-2/3 animate-pulse rounded bg-muted" /><div className="h-3 w-1/2 animate-pulse rounded bg-muted" /></div>
          : data && !data.details_available ? <p className="p-5 text-sm text-muted-foreground">Tác vụ này chạy trước khi lưu chi tiết từng trang. Kết quả tổng hợp vẫn được giữ ở trên.</p>
            : data?.items.length ? <SummaryJobResults items={data.items} compact={controls.compact} />
              : data ? <div className="px-5 py-8 text-center text-sm text-muted-foreground"><p>{summaryJobEmptyMessage({ filtered: !!query || !!status, running, warning: presentation?.warning })}</p>{(query || status) && <Button variant="ghost" size="sm" className="mt-2" onClick={() => { setSearch(""); setQuery(""); setStatus(""); setOffset(0); }}>Xóa bộ lọc</Button>}</div> : null}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 border-t px-5 py-3 text-xs text-muted-foreground">
        <span>{data ? controls.pagination && data.total ? `${offset + 1}–${Math.min(offset + LIMIT, data.total)} / ${data.total} trang` : `${data.total} trang` : error ? "Chưa tải được kết quả" : "Đang tải…"}</span>
        <div className="flex items-center gap-2">{controls.pagination && <><Button size="sm" variant="outline" disabled={offset === 0} onClick={() => setOffset((value) => Math.max(0, value - LIMIT))}>Trước</Button><Button size="sm" variant="outline" disabled={!data || offset + LIMIT >= data.total} onClick={() => setOffset((value) => value + LIMIT)}>Sau</Button></>}<Button size="sm" variant="outline" onClick={onClose}>Đóng</Button></div>
      </div>
    </DialogContent>
  </Dialog>;
}
