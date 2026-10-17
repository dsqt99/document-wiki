"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { errorText, type Source } from "../types";

type Props = {
  source: Source;
  onClose: () => void;
  onDone: () => void;
};

/** Context windows used as a size reference; budget keeps 15% headroom. */
const WINDOWS = [
  { name: "Claude 4 / Gemini 3 / GPT-5 (1M)", size: 1_000_000 },
  { name: "GPT-4o / GPT-4-turbo (128K)", size: 128_000 },
];
const MULTI_PASS_THRESHOLD = 850_000;

/** Compact token count: 1.23M, 45K, 812. */
export function formatTokens(n: number | null | undefined): string {
  const v = n ?? 0;
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(2)}M`;
  if (v >= 1_000) return `${Math.round(v / 1_000)}K`;
  return String(Math.round(v));
}

export function ExtractionReviewDialog({ source, onClose, onDone }: Props) {
  const { t } = useI18n();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [busy, setBusy] = useState<"delete" | "approve" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const tokens = source.extracted_token_count ?? 0;

  const run = async (kind: "delete" | "approve") => {
    setError(null);
    setBusy(kind);
    try {
      if (kind === "delete") {
        await api(`/api/sources/${source.id}`, { method: "DELETE" });
      } else {
        await api(`/api/sources/${source.id}/approve-extraction`, { method: "POST" });
      }
      onDone();
    } catch (err) {
      setError(errorText(err, t("common.error")));
      setBusy(null);
    }
  };

  const stats = [
    { value: formatTokens(tokens), label: t("extraction.tokens") },
    { value: String(source.page_count ?? 0), label: t("extraction.pages") },
    { value: String(source.image_count ?? 0), label: t("extraction.images") },
  ];

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !busy) onClose();
      }}
    >
      <DialogContent className="gap-4 sm:max-w-[560px]">
        <div className="pr-8">
          <DialogTitle className="flex items-center gap-2 text-base font-semibold">
            <span className="material-symbols-outlined text-orange-600 dark:text-orange-400" style={{ fontSize: 20 }}>
              scale
            </span>
            {t("extraction.title")}
          </DialogTitle>
          <DialogDescription className="mt-1 text-xs">{t("extraction.desc")}</DialogDescription>
        </div>

        <div className="rounded-lg border p-3">
          <p className="truncate text-sm font-medium" title={source.title || source.file_name || ""}>
            {source.title || source.file_name}
          </p>
          <div className="mt-3 grid grid-cols-3 gap-2 text-center">
            {stats.map((s) => (
              <div key={s.label}>
                <div className="font-mono text-xl font-bold tabular-nums">{s.value}</div>
                <div className="text-xs text-muted-foreground">{s.label}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="space-y-1.5 rounded-lg bg-muted/40 p-3 text-xs">
          <p className="font-semibold">{t("extraction.fitsInContext")}</p>
          {WINDOWS.map((w) => {
            const budget = Math.round(w.size * 0.85);
            const fits = tokens <= budget;
            return (
              <div key={w.name} className="flex items-center gap-1.5">
                <span
                  className={cn(
                    "material-symbols-outlined shrink-0",
                    fits ? "text-emerald-600 dark:text-emerald-400" : "text-orange-600 dark:text-orange-400"
                  )}
                  style={{ fontSize: 16 }}
                >
                  {fits ? "check_circle" : "warning"}
                </span>
                <span>
                  {w.name} — {t("extraction.budget").replace("{budget}", formatTokens(budget))}
                </span>
              </div>
            );
          })}
          {tokens > MULTI_PASS_THRESHOLD && (
            <p className="pt-1 text-muted-foreground italic">{t("extraction.multiPassNote")}</p>
          )}
        </div>

        {error && (
          <div className="flex items-start gap-2 rounded-lg bg-destructive/10 px-3 py-2 text-xs text-destructive">
            <span className="material-symbols-outlined shrink-0" style={{ fontSize: 16 }}>
              error
            </span>
            <span>{error}</span>
          </div>
        )}

        <div className="flex flex-wrap justify-end gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={!!busy}
            className={cn(confirmDelete && "border-destructive/50 text-destructive hover:text-destructive")}
            onClick={() => (confirmDelete ? void run("delete") : setConfirmDelete(true))}
          >
            {busy === "delete"
              ? t("common.loading")
              : confirmDelete
                ? t("extraction.confirmCancelDelete")
                : t("extraction.cancelDelete")}
          </Button>
          <Button size="sm" disabled={!!busy} onClick={() => void run("approve")}>
            {busy === "approve" ? t("common.loading") : t("extraction.approveProcess")}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
