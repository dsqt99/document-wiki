import React from "react";
import { Source } from "./types";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

const STYLE: Record<string, { dot: string; text: string }> = {
  ready: { dot: "bg-emerald-500", text: "text-emerald-700 dark:text-emerald-400" },
  processing: { dot: "bg-amber-500 animate-pulse", text: "text-amber-700 dark:text-amber-400" },
  pending: { dot: "bg-slate-400 animate-pulse", text: "text-muted-foreground" },
  plan_ready: { dot: "bg-blue-500", text: "text-blue-600 dark:text-blue-400" },
  awaiting_approval: { dot: "bg-orange-500", text: "text-orange-600 dark:text-orange-400" },
  partial: { dot: "bg-amber-500", text: "text-amber-700 dark:text-amber-400" },
  error: { dot: "bg-destructive", text: "text-destructive" },
};

const FALLBACK_LABEL: Record<string, string> = {
  ready: "Sẵn sàng",
  processing: "Đang xử lý",
  pending: "Chờ xử lý",
  plan_ready: "Chờ duyệt kế hoạch",
  awaiting_approval: "Chờ duyệt dung lượng",
  partial: "Hoàn tất một phần",
  error: "Lỗi",
};

/** Sub-line under the status label: what the pipeline is doing / produced / why it failed. */
function subLine(source: Source): { text: string; tone: "muted" | "error" } | null {
  const st = source.status;
  if (st === "processing" || st === "pending") {
    const pct = st === "processing" && source.progress != null ? `${source.progress}%` : "";
    const msg = source.progress_message || (st === "pending" ? "Đang xếp hàng" : "");
    return { text: [pct, msg].filter(Boolean).join(" · "), tone: "muted" };
  }
  if (st === "error" || st === "partial") {
    const msg = source.error_message || source.wiki_error_message || source.chunk_error_message || source.progress_message;
    return msg ? { text: msg, tone: "error" } : null;
  }
  if (st === "plan_ready" || st === "awaiting_approval") return { text: "Cần xem xét để tiếp tục", tone: "muted" };
  if (st === "ready") {
    if (source.preserve_verbatim) return { text: "Nguyên văn theo Điều", tone: "muted" };
    if (source.wiki_status === "error") return { text: "Wiki lỗi — chỉ có đoạn trích", tone: "error" };
    if (source.wiki_page_count) return { text: `${source.wiki_page_count} trang wiki`, tone: "muted" };
  }
  return null;
}

export function StatusDot({ source }: { source: Source }) {
  const { t } = useI18n();
  const st = source.status;
  const style = STYLE[st] || STYLE.pending;
  const sub = subLine(source);

  return (
    <div className="flex min-w-0 flex-col">
      <span className={cn("flex items-center gap-1.5 text-xs font-medium whitespace-nowrap", style.text)}>
        <span className={cn("size-1.5 shrink-0 rounded-full", style.dot)} />
        {t(`knowledge.status.${st}`, FALLBACK_LABEL[st] || st)}
      </span>
      {sub && sub.text && (
        <span
          className={cn("truncate pl-3 text-[10px] max-w-[160px]", sub.tone === "error" ? "text-destructive/80" : "text-muted-foreground")}
          title={sub.text}
        >
          {sub.text}
        </span>
      )}
    </div>
  );
}
