"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { needsSourcePolling } from "@/lib/source-workflow";
import { StatusDot } from "./knowledge-table/status-dot";
import { formatViDate } from "@/lib/legal-doc";
import { errorText, type Source, type SourceListResponse } from "./types";

const FILTERS = ["Tất cả", "Đang xử lý", "Sẵn sàng", "Lỗi"] as const;
function matches(source: Source, filter: string) {
  if (filter === "Sẵn sàng") return source.status === "ready";
  if (filter === "Đang xử lý") return needsSourcePolling(source);
  if (filter === "Lỗi") return ["error", "partial"].includes(source.status);
  return true;
}

export function UploadedDocuments({ initial, onRefresh, onDismiss }: {
  initial: Source[];
  onRefresh: () => void;
  onDismiss: () => void;
}) {
  const [sources, setSources] = useState(initial);
  const [seen, setSeen] = useState(initial);
  if (seen !== initial) {
    setSeen(initial);
    setSources((current) => [...initial, ...current.filter((s) => !initial.some((next) => next.id === s.id))]);
  }
  const refreshRef = useRef(onRefresh);
  useEffect(() => { refreshRef.current = onRefresh; }, [onRefresh]);
  const [filter, setFilter] = useState<string>("Tất cả");
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const pollingIds = sources.filter(needsSourcePolling).map((source) => source.id).join(",");
  useEffect(() => {
    if (!pollingIds) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const ids = pollingIds.split(",");
        const updates: Source[] = [];
        for (let i = 0; i < ids.length && active; i += 100) {
          const result = await api<SourceListResponse>(`/api/sources?source_ids=${ids.slice(i, i + 100).join(",")}&page_size=100`);
          updates.push(...result.items);
        }
        if (!active) return;
        setSources((current) => current.map((source) => updates.find((updated) => updated.id === source.id) ?? source));
        setError(null);
        if (updates.some((updated) => !needsSourcePolling(updated))) refreshRef.current();
      } catch (err) { if (active) setError(errorText(err, "Chưa cập nhật được tiến độ")); }
      if (active) timer = setTimeout(() => { void poll(); }, 4000);
    };
    void poll();
    return () => { active = false; clearTimeout(timer); };
  }, [pollingIds, tick]);

  const visible = sources.filter((source) => matches(source, filter));
  const retry = async (source: Source) => {
    try {
      const updated = await api<Source>(`/api/sources/${source.id}/retry`, { method: "POST" });
      setSources((current) => current.map((item) => item.id === source.id ? updated : item));
      onRefresh();
    } catch (err) { setError(errorText(err, "Không chạy lại được tài liệu")); }
  };
  return (
    <section className="mb-5 rounded-xl border bg-background" aria-label="Tài liệu vừa tải lên">
      <div className="flex items-start justify-between gap-3 border-b px-4 py-3">
        <div><h2 className="text-sm font-semibold">Kết quả đợt tải lên · {sources.length} tài liệu</h2><p className="mt-1 text-xs text-muted-foreground">Tài liệu tự động trích xuất, biên soạn Wiki và tạo chỉ mục tìm kiếm. Mở tài liệu để xem hoặc sửa thông tin.</p></div>
        <Button variant="outline" size="sm" onClick={onDismiss}>Về danh sách tài liệu</Button>
      </div>
      <div className="flex flex-wrap items-center gap-1 border-b bg-muted/20 px-3 py-2">{FILTERS.map((value) => <Button key={value} size="sm" variant={filter === value ? "secondary" : "ghost"} aria-pressed={filter === value} onClick={() => setFilter(value)}>{value} ({sources.filter((source) => matches(source, value)).length})</Button>)}</div>
      <div className="max-h-[28rem] overflow-auto"><table className="w-full min-w-[760px] text-left text-xs"><thead className="sticky top-0 z-10 border-b bg-background text-muted-foreground"><tr>{["Tài liệu / trạng thái", "Số hiệu", "Cơ quan ban hành", "Ngày ban hành", "Thao tác"].map((label) => <th key={label} className="px-3 py-3 font-medium">{label}</th>)}</tr></thead><tbody className="divide-y">{visible.map((source) => <tr key={source.id}>
        <td className="max-w-72 px-3 py-3"><Link className="mb-1 block truncate text-sm font-medium hover:text-primary" title={source.file_name || source.title} href={`/wiki/source/${source.id}`}>{source.file_name || source.title}</Link><StatusDot source={source} /></td>
        <td className="px-3 py-3">{source.doc_meta?.doc_number || "Chưa xác định"}</td><td className="max-w-48 px-3 py-3">{source.doc_meta?.issuing_authority || "Chưa xác định"}</td><td className="whitespace-nowrap px-3 py-3">{formatViDate(source.doc_meta?.issued_date) || "Chưa xác định"}</td>
        <td className="px-3 py-3">{source.status === "error" ? <Button variant="outline" size="sm" onClick={() => void retry(source)}>Thử lại</Button> : <Button size="sm" variant="ghost" nativeButton={false} render={<Link href={`/wiki/source/${source.id}`} />}>Mở tài liệu</Button>}</td>
      </tr>)}</tbody></table>{!visible.length && <p className="p-6 text-center text-sm text-muted-foreground">Không có tài liệu ở trạng thái này.</p>}</div>
      {error && <div className="flex items-center gap-2 px-4 pb-3 text-xs text-destructive" role="alert">{error}<Button variant="ghost" size="sm" onClick={() => setTick((n) => n + 1)}>Thử lại</Button></div>}
    </section>
  );
}
