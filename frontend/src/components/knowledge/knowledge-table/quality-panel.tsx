import type { ProcessingQuality, QualityStatus } from "../types";
import { QUALITY_LABELS, qualityStages, qualityWarningText } from "./processing-quality";

const STATUS_TONE: Record<QualityStatus, string> = {
  unknown: "text-muted-foreground",
  pending: "text-muted-foreground",
  processing: "text-amber-700 dark:text-amber-400",
  ready: "text-emerald-700 dark:text-emerald-400",
  complete: "text-emerald-700 dark:text-emerald-400",
  partial: "text-amber-700 dark:text-amber-400",
  error: "text-destructive",
  blocked: "text-destructive",
};

export function QualityPanel({ quality }: { quality?: ProcessingQuality | null }) {
  const stages = qualityStages(quality);
  return (
    <section aria-label="Kết quả xử lý" className="mt-4 border-t border-border/70 pt-3">
      <div className="grid min-w-0 gap-4 md:grid-cols-3">
        {stages.map((stage) => (
          <div key={stage.key} className="min-w-0">
            <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
              <h4 className="text-xs font-semibold">{stage.label}</h4>
              <span className={`text-[11px] font-medium ${STATUS_TONE[stage.status]}`}>{QUALITY_LABELS[stage.status]}</span>
            </div>
            <dl className="mt-2 space-y-1 text-xs leading-5">
              {stage.metrics.map((metric) => (
                <div key={metric.label} className="flex flex-wrap justify-between gap-x-3">
                  <dt className="text-muted-foreground">{metric.label}</dt>
                  <dd className="font-medium tabular-nums">{metric.value}</dd>
                </div>
              ))}
            </dl>
          </div>
        ))}
      </div>
      {stages.some((stage) => stage.status === "unknown") && (
        <p className="mt-3 text-[11px] leading-5 text-muted-foreground">Chưa có đủ số liệu để xác nhận độ bao phủ. Trạng thái sẵn sàng không đồng nghĩa toàn bộ nội dung đã được xử lý.</p>
      )}
      {(quality?.warnings?.length ?? 0) > 0 && (
        <div className="mt-3 border-l-2 border-amber-500/60 pl-3 text-xs leading-5">
          <p className="font-medium text-amber-700 dark:text-amber-400">Cần kiểm tra</p>
          <ul className="mt-1 list-disc space-y-1 pl-4 text-muted-foreground">
            {quality!.warnings.map((warning, index) => <li key={`${warning.code}-${index}`} className="break-words">{qualityWarningText(warning, quality)}</li>)}
          </ul>
        </div>
      )}
    </section>
  );
}
