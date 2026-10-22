"use client";

import { OptionSelect } from "@/components/ui/option-select";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { wikiPageQuery } from "@/lib/wiki-navigation";
import type { SummaryJob } from "./summary-maintenance";

export type SummaryJobItem = {
  page_id: string; title: string; slug: string; scope_type: string; scope_id?: string | null;
  source_titles: string[]; status: string; stage: string; message: string; updated_at: number;
};
type DetailResult = { items: SummaryJobItem[]; total: number; counts: Record<string, number>; details_available: boolean };
const LABELS: Record<string, string> = { queued: "Chờ chạy", running: "Đang chạy", updated: "Đã cập nhật", unchanged: "Đã khớp", skipped: "Bỏ qua", failed: "Lỗi", index_failed: "Lỗi chỉ mục" };
const STAGES: Record<string, string> = { queued: "Chờ xử lý", reading: "Đọc trang Wiki", summary: "Tạo tóm tắt", llm: "AI đọc và tóm tắt", combining: "Tổng hợp các phần", validating: "Kiểm tra phiên bản", indexing: "Cập nhật chỉ mục", completed: "Hoàn tất" };
const LIMIT = 50;

export function SummaryJobDetailsDialog({ job, knownItems, onClose }: {
  job?: SummaryJob | null; knownItems?: SummaryJobItem[]; onClose: () => void;
}) {
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [tick, setTick] = useState(0);
  const [response, setResponse] = useState<{ key: string; data: DetailResult } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const jobId = job?.job_id;
  const running = job?.status === "queued" || job?.status === "running";
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
  useEffect(() => {
    if (!jobId || knownItems) return;
    let active = true;
    const params = new URLSearchParams({ offset: String(offset), limit: String(LIMIT) });
    if (status) params.set("status", status);
    if (query) params.set("q", query);
    api<DetailResult>(`/api/wiki/summaries/jobs/${encodeURIComponent(jobId)}/items?${params}`)
      .then((data) => { if (active) { setResponse({ key, data }); setError(null); } })
      .catch((err: unknown) => { if (active) setError(err instanceof Error ? err.message : "Không tải được chi tiết"); });
    return () => { active = false; };
  }, [jobId, knownItems, offset, status, query, key, tick, running]);
  const local = knownItems?.filter((item) => (!status || item.status === status) && `${item.title} ${item.slug} ${item.source_titles.join(" ")}`.toLocaleLowerCase("vi").includes(query.toLocaleLowerCase("vi")));
  const data: DetailResult | null = knownItems ? { items: local!.slice(offset, offset + LIMIT), total: local!.length, counts: {}, details_available: true } : response?.key === key ? response.data : null;
  const hrefFor = (item: SummaryJobItem) => `/wiki/${item.slug.split("/").map(encodeURIComponent).join("/")}${wikiPageQuery(item.scope_type, item.scope_id, "/wiki/law?view=wiki")}`;
  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent className="flex max-h-[90vh] flex-col gap-0 overflow-hidden p-0 sm:max-w-5xl">
        <div className="space-y-2 border-b px-5 py-4 pr-12">
          <DialogTitle>{knownItems ? "Các trang có dấu ... trong nội dung Wiki" : "Chi tiết tiến trình cập nhật tóm tắt"}</DialogTitle>
          <DialogDescription>{knownItems ? "Các trang này đã có tóm tắt khớp nội dung Wiki. Kiểm tra tệp gốc và nội dung trích xuất nếu bạn cho rằng còn thiếu đoạn văn." : "Theo dõi từng trang Wiki, văn bản nguồn, bước đang thực hiện và kết quả. Đóng popup không dừng tác vụ."}</DialogDescription>
          {job && <p className="text-xs text-muted-foreground">Đã xử lý {job.processed}/{job.total} · Cập nhật {job.updated} · Đã khớp {job.unchanged ?? 0} · Bỏ qua {job.skipped ?? 0} · Lỗi {job.failed + job.index_failed}</p>}
          {job?.current && running && <p className="text-sm"><strong>{job.current.title}</strong> · {STAGES[job.current.stage] || job.current.stage}</p>}
        </div>
        <div className="flex flex-wrap items-center gap-2 border-b px-5 py-3">
          <Input className="min-w-48 flex-1" aria-label="Tìm trang hoặc văn bản trong tiến trình" placeholder="Tìm theo tên trang hoặc văn bản…" value={search} onChange={(event) => setSearch(event.target.value)} />
          <OptionSelect aria-label="Lọc trạng thái xử lý tóm tắt" className="h-8 rounded-md border bg-background px-2 text-sm" value={status} onValueChange={(value) => { setStatus(value); setOffset(0); }}><option value="">Tất cả trạng thái</option>{Object.entries(LABELS).map(([value, label]) => <option key={value} value={value}>{label}{data?.counts[value] ? ` (${data.counts[value]})` : ""}</option>)}</OptionSelect>
          {!knownItems && <Button variant="outline" size="sm" onClick={() => setTick((value) => value + 1)}>Cập nhật</Button>}
        </div>
        <div className="min-h-24 flex-1 overflow-auto">
          {error && <p role="alert" className="px-5 py-3 text-sm text-destructive">{error}</p>}
          {!data && !error ? <p className="p-5 text-sm text-muted-foreground">Đang tải chi tiết…</p> : data && !data.details_available ? <p className="p-5 text-sm text-muted-foreground">Tác vụ này chạy trước khi có chức năng lưu chi tiết. Các tác vụ mới sẽ hiển thị đầy đủ từng trang và lý do xử lý.</p> : data?.items.length ? <table className="w-full min-w-[640px] text-left text-sm"><thead className="sticky top-0 bg-muted"><tr><th className="px-5 py-3 font-medium">Trang Wiki / văn bản nguồn</th><th className="whitespace-nowrap px-3 py-3 font-medium">Trạng thái</th><th className="px-5 py-3 font-medium">Bước xử lý & chi tiết</th></tr></thead><tbody className="divide-y">{data.items.map((item) => <tr key={item.page_id} className={item.status === "running" ? "bg-primary/5" : ""}><td className="w-[42%] px-5 py-3 align-top"><Link href={hrefFor(item)} target="_blank" rel="noopener noreferrer" className="font-medium hover:text-primary hover:underline">{item.title}</Link>{item.source_titles.map((title) => <p key={title} className="mt-1 text-xs text-muted-foreground">{title}</p>)}</td><td className="whitespace-nowrap px-3 py-3 align-top"><span className={item.status === "failed" || item.status === "index_failed" ? "text-destructive" : item.status === "running" ? "text-primary" : "text-muted-foreground"}>{LABELS[item.status] || item.status}</span></td><td className="px-5 py-3 align-top"><p className="text-xs font-medium">{STAGES[item.stage] || item.stage}</p><p className="mt-1 break-words text-xs leading-5 text-muted-foreground">{item.message}</p></td></tr>)}</tbody></table> : data ? <p className="p-6 text-center text-sm text-muted-foreground">Không có mục phù hợp.</p> : null}
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2 border-t px-5 py-3 text-xs text-muted-foreground"><span>{data?.total ? `${offset + 1}–${Math.min(offset + LIMIT, data.total)} / ${data.total} trang` : "0 trang"}</span><div className="flex items-center gap-2"><Button size="sm" variant="outline" disabled={offset === 0} onClick={() => setOffset((value) => Math.max(0, value - LIMIT))}>Trước</Button><Button size="sm" variant="outline" disabled={!data || offset + LIMIT >= data.total} onClick={() => setOffset((value) => value + LIMIT)}>Sau</Button><Button size="sm" variant="outline" onClick={onClose}>Đóng</Button></div></div>
      </DialogContent>
    </Dialog>
  );
}
