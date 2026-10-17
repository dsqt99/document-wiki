"use client";

import { useCallback, useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { errorText, type Source } from "../types";

type PlanPage = {
  action: "CREATE" | "UPDATE";
  slug: string;
  title: string;
  page_type: string;
  entity_names?: string[];
  priority?: number;
  related_kb_pages?: string[];
};

type Plan = {
  pages: PlanPage[];
  strategy?: string | null;
  compilation_notes?: string | null;
  estimated_page_count?: number | null;
  source_page_slug?: string | null;
};

type PlanResponse = {
  id: string;
  status: string;
  plan: Plan | null;
  review_note?: string | null;
};

type Props = {
  source: Source;
  onClose: () => void;
  onDone: () => void;
};

const POLL_MS = 3000;

function Spinner({ size = 16 }: { size?: number }) {
  return (
    <span className="material-symbols-outlined animate-spin" style={{ fontSize: size }}>
      progress_activity
    </span>
  );
}

function pageTypeLabel(pt: string): string {
  const v = pt === "concept" ? "page" : pt || "";
  return v ? v.charAt(0).toUpperCase() + v.slice(1) : "";
}

export function PlanReviewDialog({ source, onClose, onDone }: Props) {
  const { t } = useI18n();
  const [plan, setPlan] = useState<Plan | null>(null);
  const [status, setStatus] = useState("pending_review");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [requestingRegen, setRequestingRegen] = useState(false);
  const [confirmReject, setConfirmReject] = useState(false);

  const load = useCallback(() => {
    return api<PlanResponse>(`/api/sources/${source.id}/plan`)
      .then((res) => {
        setPlan(res.plan ?? null);
        setStatus(res.status || "pending_review");
      })
      .catch((err: unknown) => setError(errorText(err, t("common.error"))))
      .finally(() => setLoading(false));
  }, [source.id, t]);

  useEffect(() => {
    let cancelled = false;
    api<PlanResponse>(`/api/sources/${source.id}/plan`)
      .then((res) => {
        if (cancelled) return;
        setPlan(res.plan ?? null);
        setStatus(res.status || "pending_review");
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(errorText(err, t("common.error")));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [source.id, t]);

  useEffect(() => {
    if (status !== "regenerating") return;
    const timer = setInterval(() => {
      void load();
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [status, load]);

  const regenerating = status === "regenerating" || requestingRegen;

  const regenerate = async () => {
    if (!note.trim()) {
      setError(t("plan.feedbackRequired"));
      return;
    }
    setError(null);
    setRequestingRegen(true);
    try {
      await api(`/api/sources/${source.id}/plan/regenerate`, { method: "POST", body: { note: note.trim() } });
      setStatus("regenerating");
      setNote("");
      setConfirmReject(false);
    } catch (err) {
      setError(errorText(err, t("common.error")));
    } finally {
      setRequestingRegen(false);
    }
  };

  const decide = async (kind: "approve" | "reject") => {
    setError(null);
    setSubmitting(true);
    try {
      const fallback = kind === "approve" ? "Approved via UI" : "Rejected via UI";
      await api(`/api/sources/${source.id}/plan/${kind}`, {
        method: "POST",
        body: { note: note.trim() || fallback },
      });
      onDone();
    } catch (err) {
      setError(errorText(err, t("common.error")));
      setSubmitting(false);
    }
  };

  const pages = [...(plan?.pages ?? [])].sort((a, b) => {
    if (a.action !== b.action) return a.action === "CREATE" ? -1 : 1;
    return (a.priority ?? 99) - (b.priority ?? 99);
  });
  const createCount = pages.filter((p) => p.action === "CREATE").length;
  const updateCount = pages.filter((p) => p.action === "UPDATE").length;
  const busy = loading || submitting || regenerating;

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !submitting) onClose();
      }}
    >
      <DialogContent className="flex max-h-[85vh] flex-col gap-0 overflow-hidden p-0 sm:max-w-2xl">
        <div className="border-b px-5 py-4 pr-12">
          <DialogTitle className="flex items-center gap-2 text-base font-semibold">
            <span className="material-symbols-outlined text-blue-600 dark:text-blue-400" style={{ fontSize: 20 }}>
              fact_check
            </span>
            {t("plan.title")}
          </DialogTitle>
          <DialogDescription className="mt-1 text-xs">
            {t("plan.subtitle").replace("{title}", source.title)}
          </DialogDescription>
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
          {loading ? (
            <div className="flex justify-center py-16 text-muted-foreground">
              <Spinner size={30} />
            </div>
          ) : (
            <>
              {regenerating && (
                <div className="flex items-center gap-2 rounded-lg border border-blue-500/30 bg-blue-50 px-3 py-2 text-xs text-blue-700 dark:bg-blue-500/10 dark:text-blue-300">
                  <Spinner />
                  {t("plan.regenerating")}
                </div>
              )}

              <div className={cn("space-y-4", regenerating && "pointer-events-none opacity-50")}>
                <div className="flex flex-wrap items-center gap-4 text-sm text-muted-foreground">
                  <span className="flex items-center gap-1.5">
                    <span className="size-2 rounded-full bg-emerald-500" />
                    {createCount} {t("plan.toCreate")}
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span className="size-2 rounded-full bg-yellow-500" />
                    {updateCount} {t("plan.toUpdate")}
                  </span>
                  {plan?.strategy && (
                    <span className="flex items-center gap-1">
                      <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
                        analytics
                      </span>
                      {plan.strategy}
                    </span>
                  )}
                </div>

                {plan?.compilation_notes && (
                  <div className="rounded-lg border bg-secondary/40 px-3 py-2 text-xs">
                    <span className="font-semibold">{t("plan.plannerNote")} </span>
                    {plan.compilation_notes}
                  </div>
                )}

                <div className="space-y-2">
                  {pages.map((p) => {
                    const names = p.entity_names ?? [];
                    return (
                      <div key={`${p.action}-${p.slug}`} className="rounded-lg border bg-card px-3 py-2.5">
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge
                            variant="outline"
                            className={cn(
                              "h-4 px-1.5 text-[10px]",
                              p.action === "CREATE"
                                ? "border-emerald-500/40 text-emerald-700 dark:text-emerald-400"
                                : "border-yellow-500/40 text-yellow-700 dark:text-yellow-400"
                            )}
                          >
                            {p.action}
                          </Badge>
                          <span className="text-sm font-medium">{p.title}</span>
                          <span className="font-mono text-[10px] text-muted-foreground">{p.slug}</span>
                          {p.page_type && (
                            <Badge variant="secondary" className="h-4 px-1.5 text-[10px]">
                              {pageTypeLabel(p.page_type)}
                            </Badge>
                          )}
                        </div>
                        {names.length > 0 && (
                          <p className="mt-1 text-[11px] text-muted-foreground">
                            {names.slice(0, 5).join(", ")}
                            {names.length > 5 ? ` +${names.length - 5} more` : ""}
                          </p>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>

              <div className="space-y-1.5">
                <Textarea
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder={t("plan.feedbackPlaceholder")}
                  disabled={regenerating}
                  className="h-16 min-h-16 resize-none text-sm [field-sizing:fixed]"
                />
                <p className="text-[11px] text-muted-foreground">{t("plan.feedbackHelp")}</p>
              </div>
            </>
          )}

          {error && (
            <div className="flex items-start gap-2 rounded-lg bg-destructive/10 px-3 py-2 text-xs text-destructive">
              <span className="material-symbols-outlined shrink-0" style={{ fontSize: 16 }}>
                error
              </span>
              <span>{error}</span>
            </div>
          )}
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2 border-t px-5 py-3">
          <Button variant="outline" size="sm" onClick={() => void regenerate()} disabled={busy}>
            {regenerating ? (
              <Spinner size={15} />
            ) : (
              <span className="material-symbols-outlined" style={{ fontSize: 15 }}>
                refresh
              </span>
            )}
            {regenerating ? t("common.retrying") : t("plan.regenerateBtn")}
          </Button>
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="ghost" size="sm" onClick={onClose} disabled={submitting}>
              {t("common.cancel")}
            </Button>
            {confirmReject ? (
              <Button variant="destructive" size="sm" onClick={() => void decide("reject")} disabled={busy}>
                {submitting ? (
                  <Spinner size={15} />
                ) : (
                  <span className="material-symbols-outlined" style={{ fontSize: 15 }}>
                    close
                  </span>
                )}
                {t("plan.confirmRejectBtn")}
              </Button>
            ) : (
              <Button
                variant="outline"
                size="sm"
                className="text-destructive hover:text-destructive"
                onClick={() => setConfirmReject(true)}
                disabled={busy}
              >
                <span className="material-symbols-outlined" style={{ fontSize: 15 }}>
                  close
                </span>
                {t("plan.rejectBtn")}
              </Button>
            )}
            <Button size="sm" onClick={() => void decide("approve")} disabled={busy}>
              {submitting ? (
                <Spinner size={15} />
              ) : (
                <span className="material-symbols-outlined" style={{ fontSize: 15 }}>
                  check
                </span>
              )}
              {t("plan.approveBtn")}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
