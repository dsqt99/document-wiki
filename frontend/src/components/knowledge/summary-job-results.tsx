import Link from "next/link";
import { wikiPageQuery } from "@/lib/wiki-navigation";
import type { SummaryJobItem } from "./summary-job-details";

export const SUMMARY_ITEM_LABELS: Record<string, string> = {
  queued: "Chờ chạy", running: "Đang chạy", updated: "Đã cập nhật", unchanged: "Đã khớp",
  skipped: "Bỏ qua", failed: "Lỗi", index_failed: "Lỗi chỉ mục",
};
export const SUMMARY_ITEM_STAGES: Record<string, string> = {
  queued: "Chờ xử lý", reading: "Đọc trang Wiki", summary: "Tạo tóm tắt", llm: "AI đọc và tóm tắt",
  combining: "Tổng hợp các phần", validating: "Kiểm tra phiên bản", indexing: "Cập nhật chỉ mục", completed: "Hoàn tất",
};

function statusClass(status: string) {
  return status === "failed" || status === "index_failed" ? "text-destructive"
    : status === "running" ? "text-primary" : "text-muted-foreground";
}

function PageIdentity({ item }: { item: SummaryJobItem }) {
  const href = `/wiki/${item.slug.split("/").map(encodeURIComponent).join("/")}${wikiPageQuery(item.scope_type, item.scope_id, "/wiki/law?view=wiki")}`;
  return <div className="min-w-0">
    <Link href={href} target="_blank" rel="noopener noreferrer" className="break-words font-medium hover:text-primary hover:underline focus-visible:outline-2 focus-visible:outline-ring">{item.title}</Link>
    {item.source_titles.map((title) => <p key={title} className="mt-1 break-words text-xs leading-5 text-muted-foreground">{title}</p>)}
  </div>;
}

function ItemStatus({ item }: { item: SummaryJobItem }) {
  return <span className={`inline-flex shrink-0 items-center gap-1.5 text-xs ${statusClass(item.status)}`}>
    <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-current" />
    {SUMMARY_ITEM_LABELS[item.status] || item.status}
  </span>;
}

export function SummaryJobResults({ items, compact }: { items: SummaryJobItem[]; compact: boolean }) {
  return <>
    <ul className={`divide-y ${compact ? "" : "sm:hidden"}`} aria-label="Các trang đã xử lý">
      {items.map((item) => <li key={item.page_id} className={`space-y-2 px-5 py-4 ${item.status === "running" ? "bg-primary/5" : ""}`}>
        <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2"><div className="min-w-0 flex-1 basis-40"><PageIdentity item={item} /></div><ItemStatus item={item} /></div>
        <p className="break-words text-xs leading-5 text-muted-foreground">{item.message || SUMMARY_ITEM_STAGES[item.stage] || item.stage}</p>
      </li>)}
    </ul>
    {!compact && <table className="hidden w-full text-left text-sm sm:table">
      <thead className="sticky top-0 bg-muted"><tr><th className="px-5 py-3 font-medium">Trang Wiki / văn bản nguồn</th><th className="px-3 py-3 font-medium">Trạng thái</th><th className="px-5 py-3 font-medium">Bước xử lý & chi tiết</th></tr></thead>
      <tbody className="divide-y">{items.map((item) => <tr key={item.page_id} className={item.status === "running" ? "bg-primary/5" : ""}>
        <td className="w-[42%] px-5 py-3 align-top"><PageIdentity item={item} /></td>
        <td className="px-3 py-3 align-top"><ItemStatus item={item} /></td>
        <td className="px-5 py-3 align-top"><p className="text-xs font-medium">{SUMMARY_ITEM_STAGES[item.stage] || item.stage}</p><p className="mt-1 break-words text-xs leading-5 text-muted-foreground">{item.message}</p></td>
      </tr>)}</tbody>
    </table>}
  </>;
}
