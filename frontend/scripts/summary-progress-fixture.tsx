"use client";

// Local browser fixture. Temporarily import from a non-production app route.
// All summary requests are intercepted in this document; no AI tasks are started.
import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { SummaryJobProgress, SummaryMaintenanceMenuGroup, SummarySourceNotes, useSummaryMaintenance, type SummaryJob } from "@/components/knowledge/summary-maintenance";
import type { SummaryJobItem } from "@/components/knowledge/summary-job-details";
import { useTheme } from "@/lib/theme";

const finished = (total = 1): SummaryJob => ({ job_id: "qa-history", status: "completed", only_missing: true, engine: "llm",
  total, processed: total, updated: total, failed: 0, index_failed: 0, unchanged: 0, skipped: 0, message: "Đã cập nhật tóm tắt.", errors: [] });
const rowsFor = (total: number): SummaryJobItem[] => Array.from({ length: total }, (_, i) => ({ page_id: `page-${i}`, title: i ? `Trang Wiki ${i + 1}` : "Đường link chuyên mục",
  slug: i ? `trang-${i + 1}` : "duong-link-chuyen-muc", scope_type: "global", source_titles: ["07. Danh sách đường link.docx"],
  status: "updated", stage: "completed", message: "Đã lưu tóm tắt AI (662 ký tự) và cập nhật chỉ mục", updated_at: 0 }));
let simulation = { job: finished(), rows: rowsFor(1), fail: false, expired: false, empty: false, sequence: 0 };

function Workspace({ onComplete, enabled }: { onComplete: () => void; enabled: boolean }) {
  const maintenance = useSummaryMaintenance(enabled, onComplete);
  return <section className="mx-auto max-w-6xl space-y-5 px-4 py-8">
    <div className="flex flex-wrap items-center justify-between gap-4"><div><h1 className="text-xl font-semibold">Tài liệu Wiki</h1><p className="mt-1 text-sm text-muted-foreground">Quản lý tài liệu và nội dung đã biên soạn</p></div>
      <DropdownMenu onOpenChange={(open) => { if (open) void maintenance.refresh(); }}><DropdownMenuTrigger data-summary-result-trigger className="rounded-lg border px-3 py-2 text-sm">Xử lý nội dung</DropdownMenuTrigger><DropdownMenuContent align="end" className="min-w-72"><SummaryMaintenanceMenuGroup maintenance={maintenance} /></DropdownMenuContent></DropdownMenu>
    </div>
    <SummaryJobProgress job={maintenance.job} error={maintenance.error} onDismiss={maintenance.dismiss} onRetry={() => void maintenance.refresh()} onDetails={(trigger) => maintenance.openDetails(maintenance.job, trigger)} detailsOpen={maintenance.detailsOpen} />
    <div className="rounded-xl border"><div className="flex justify-between border-b bg-muted/30 px-4 py-3 text-xs text-muted-foreground"><span>TÀI LIỆU</span><span>TRẠNG THÁI</span></div>
      <div className="flex items-center justify-between gap-4 px-4 py-5"><div><p className="text-sm font-medium">07. Danh sách đường link.docx</p><p className="mt-1 text-xs text-muted-foreground">Phòng ban · PC08</p></div><span className="text-xs text-emerald-600">Sẵn sàng</span></div>
    </div>
    <SummarySourceNotes maintenance={maintenance} />
  </section>;
}

export default function SummaryProgressFixture() {
  const [ready, setReady] = useState(false);
  const [version, setVersion] = useState(0);
  const [completions, setCompletions] = useState(0);
  const [enabled, setEnabled] = useState(true);
  const { setTheme } = useTheme();
  const completed = useCallback(() => setCompletions((value) => value + 1), []);
  useEffect(() => {
    const original = window.fetch;
    window.fetch = async (input, init) => {
      const url = new URL(typeof input === "string" ? input : input instanceof Request ? input.url : input.toString(), location.origin);
      if (!url.pathname.startsWith("/api/wiki/summaries/")) return original(input, init);
      const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
      if (simulation.fail) return json({ detail: "Không kết nối được dịch vụ kiểm tra." }, 503);
      if (url.pathname.endsWith("/status")) return json({ total: simulation.job.total, needs_update: simulation.empty ? 0 : simulation.job.total,
        active_job: ["queued", "running"].includes(simulation.job.status) ? simulation.job : null, recent_job: simulation.job });
      if (url.pathname.endsWith("/rebuild")) {
        simulation.job = { ...finished(simulation.empty ? 0 : simulation.job.total), job_id: `qa-start-${++simulation.sequence}`, status: simulation.empty ? "completed" : "running", processed: 0, updated: 0,
          current: simulation.empty ? null : { ...simulation.rows[0], status: "running", stage: "llm", message: "AI đọc và tóm tắt" } };
        return json(simulation.job);
      }
      if (simulation.expired) return json({ detail: "Tác vụ đã hết hạn" }, 404);
      if (url.pathname.endsWith("/items")) {
        const counts: Record<string, number> = {};
        for (const row of simulation.rows) counts[row.status] = (counts[row.status] ?? 0) + 1;
        const q = (url.searchParams.get("q") ?? "").toLowerCase();
        const status = url.searchParams.get("status");
        const matching = simulation.rows.filter((row) => (!status || row.status === status) && `${row.title} ${row.source_titles.join(" ")}`.toLowerCase().includes(q));
        const offset = Number(url.searchParams.get("offset") ?? 0);
        return json({ items: matching.slice(offset, offset + 50), total: matching.length, counts, details_available: true });
      }
      return json(simulation.job);
    };
    // Mount the real hook only after the isolated transport is installed.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setReady(true);
    return () => { window.fetch = original; };
  }, []);
  const reset = (count: number) => {
    simulation = { job: finished(count), rows: rowsFor(count), fail: false, expired: false, empty: count === 0, sequence: simulation.sequence };
    setVersion((value) => value + 1);
    setCompletions(0);
  };
  return <main className="min-h-screen bg-background text-foreground">
    <div className="border-b bg-muted/30 px-4 py-3 text-xs"><p className="mb-2 text-muted-foreground">Kiểm tra UI local · dữ liệu giả lập · callbacks: {completions}</p>
      <div className="flex flex-wrap gap-2"><Button size="sm" variant="outline" onClick={() => reset(1)}>1 trang</Button><Button size="sm" variant="outline" onClick={() => reset(8)}>8 trang</Button><Button size="sm" variant="outline" onClick={() => reset(52)}>52 trang</Button><Button size="sm" variant="outline" onClick={() => reset(0)}>Không cần cập nhật</Button>
        <Button size="sm" variant="outline" onClick={() => { simulation.job = { ...simulation.job, status: "completed", processed: simulation.job.total, updated: simulation.job.total, current: null }; }}>Hoàn tất tác vụ</Button>
        <Button size="sm" variant="outline" onClick={() => { simulation.job = { ...simulation.job, status: "failed", failed: 1, message: "Không tạo được tóm tắt do AI không phản hồi.", errors: Array.from({ length: 5 }, (_, i) => `Trang ${i + 1}: Kết nối AI hết thời gian chờ khi đọc văn bản nguồn và tạo tóm tắt; vui lòng kiểm tra dịch vụ AI trước khi chạy lại. Mã trang: 12345678-1234-1234-1234-123456789012.`) }; simulation.rows = []; }}>Tác vụ lỗi</Button>
        <Button size="sm" variant="outline" onClick={() => { simulation.fail = !simulation.fail; }}>Đổi lỗi kết nối</Button><Button size="sm" variant="outline" onClick={() => { simulation.expired = !simulation.expired; }}>Đổi hết hạn</Button>
        <Button size="sm" variant="outline" onClick={() => setEnabled((value) => !value)}>Đổi quyền</Button><Button size="sm" variant="outline" onClick={() => setTheme("dark")}>Tối</Button><Button size="sm" variant="outline" onClick={() => setTheme("light")}>Sáng</Button>
      </div>
    </div>
    {ready && <Workspace key={version} onComplete={completed} enabled={enabled} />}
  </main>;
}
