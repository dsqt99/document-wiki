"use client";

import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type { Source } from "../types";

type Tone = { dot: string; text: string; fallback: string };

const TONES: Record<string, Tone> = {
  ready: { dot: "bg-emerald-500", text: "text-emerald-700 dark:text-emerald-400", fallback: "Sẵn sàng" },
  processing: {
    dot: "bg-amber-500 animate-pulse",
    text: "text-amber-700 dark:text-amber-400",
    fallback: "Đang xử lý",
  },
  pending: { dot: "bg-slate-400 animate-pulse", text: "text-muted-foreground", fallback: "Chờ xử lý" },
  plan_ready: { dot: "bg-blue-500", text: "text-blue-600 dark:text-blue-400", fallback: "Chờ duyệt kế hoạch" },
  awaiting_approval: {
    dot: "bg-orange-500",
    text: "text-orange-600 dark:text-orange-400",
    fallback: "Chờ duyệt dung lượng",
  },
  partial: { dot: "bg-amber-500", text: "text-amber-700 dark:text-amber-400", fallback: "Hoàn tất một phần" },
  error: { dot: "bg-destructive", text: "text-destructive", fallback: "Lỗi" },
};

type SubLine = { text: string; error: boolean } | null;

function subLineFor(source: Source): SubLine {
  switch (source.status) {
    case "processing": {
      const parts: string[] = [];
      if (typeof source.progress === "number") parts.push(`${source.progress}%`);
      if (source.progress_message) parts.push(source.progress_message);
      return parts.length ? { text: parts.join(" · "), error: false } : null;
    }
    case "pending":
      return { text: source.progress_message || "Đang xếp hàng", error: false };
    case "error":
    case "partial": {
      const msg =
        source.error_message ||
        source.wiki_error_message ||
        source.chunk_error_message ||
        source.progress_message;
      return msg ? { text: msg, error: true } : null;
    }
    case "plan_ready":
    case "awaiting_approval":
      return { text: "Cần xem xét để tiếp tục", error: false };
    case "ready":
      if (source.preserve_verbatim) return { text: "Nguyên văn theo Điều", error: false };
      if (source.wiki_status === "error") return { text: "Wiki lỗi — chỉ có đoạn trích", error: true };
      if ((source.wiki_page_count ?? 0) > 0) return { text: `${source.wiki_page_count} trang wiki`, error: false };
      return null;
    default:
      return null;
  }
}

export function StatusDot({ source }: { source: Source }) {
  const { t } = useI18n();
  const known = TONES[source.status];
  const tone = known ?? TONES.pending;
  const label = known ? t(`knowledge.status.${source.status}`, known.fallback) : source.status;
  const sub = subLineFor(source);

  return (
    <div className="flex flex-col">
      <span className={cn("inline-flex items-center gap-1.5 text-xs font-medium whitespace-nowrap", tone.text)}>
        <span className={cn("size-1.5 shrink-0 rounded-full", tone.dot)} />
        {label}
      </span>
      {sub && (
        <span
          title={sub.text}
          className={cn(
            "mt-0.5 max-w-40 truncate pl-3 text-[10px]",
            sub.error ? "text-destructive/80" : "text-muted-foreground"
          )}
        >
          {sub.text}
        </span>
      )}
    </div>
  );
}
