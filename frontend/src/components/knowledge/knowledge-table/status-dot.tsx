import React from "react";
import { Source } from "./types";
import { useI18n } from "@/lib/i18n";

export function StatusDot({ source }: { source: Source }) {
  const { t } = useI18n();

  const colors: Record<string, string> = {
    ready: "bg-green-500",
    processing: "bg-yellow-500",
    error: "bg-destructive",
    pending: "bg-muted-foreground",
    plan_ready: "bg-blue-500",
    awaiting_approval: "bg-orange-500",
  };

  const status = source.status;
  const highlight = status === "plan_ready" || status === "awaiting_approval";

  const getStatusLabel = (st: string) => {
    switch (st) {
      case "ready":
        return t("knowledge.status.ready", "Ready");
      case "processing":
        return t("knowledge.status.processing", "Processing");
      case "error":
        return t("knowledge.status.error", "Error");
      case "pending":
        return t("knowledge.status.pending", "Pending");
      case "plan_ready":
        return t("knowledge.status.plan_ready", "Review Plan");
      case "awaiting_approval":
        return t("knowledge.status.awaiting_approval", "Review Size");
      default:
        return st;
    }
  };

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-1.5">
        <span className={`w-2 h-2 rounded-full ${colors[status] || colors.pending}`} />
        <span className={`text-xs capitalize ${highlight ? (status === "plan_ready" ? "text-blue-500 font-medium" : "text-orange-500 font-medium") : "text-muted-foreground"}`}>
          {getStatusLabel(status)}
        </span>
        {status === "processing" && source.progress !== undefined && (
          <span className="text-xs text-muted-foreground">({source.progress}%)</span>
        )}
      </div>
      {(status === "processing" || status === "pending") && source.progress_message && (
        <span className="text-[10px] text-muted-foreground truncate max-w-[150px]" title={source.progress_message}>
          {source.progress_message}
        </span>
      )}
      {status === "error" && source.progress_message && (
        <span className="text-[10px] text-destructive truncate max-w-[150px]" title={source.progress_message}>
          {source.progress_message}
        </span>
      )}
    </div>
  );
}
