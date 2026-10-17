"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/shared/page-header";
import {
  ContributionReviewDialog,
  REVIEW_LABELS_EN,
  type ReviewOutcome,
} from "@/components/skills/contribution-dialogs";
import { TONE } from "@/components/skills/skill-utils";
import type { PendingContribution } from "@/components/skills/types";
import { cn } from "@/lib/utils";

const ADMIN_REVIEW_LABELS = { ...REVIEW_LABELS_EN, closeTip: undefined };

export default function SkillContributionsAdminPage() {
  const router = useRouter();
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const [items, setItems] = useState<PendingContribution[] | null>(null);
  const [reviewing, setReviewing] = useState<PendingContribution | null>(null);

  // Admins only; everyone else goes back to the portal home.
  useEffect(() => {
    if (user && !isAdmin) router.replace("/");
  }, [user, isAdmin, router]);

  const load = useCallback(() => {
    return api<PendingContribution[]>("/api/admin/skill-contributions")
      .then((rows) => setItems(Array.isArray(rows) ? rows : []))
      .catch((err) => {
        console.error("Load contributions failed", err);
        setItems([]);
      });
  }, []);

  useEffect(() => {
    if (!isAdmin) return;
    const timer = setTimeout(() => void load(), 0);
    return () => clearTimeout(timer);
  }, [isAdmin, load]);

  const onSettled = ({ ok }: ReviewOutcome) => {
    if (!ok) return;
    setReviewing(null);
    void load();
  };

  if (!isAdmin) return null;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Contribution Management" description="Review and approve AI skill proposals from the team." />

      <div className="overflow-hidden rounded-2xl border border-border/60 bg-card">
        {items === null ? (
          <div className="flex justify-center py-24">
            <span className="material-symbols-outlined animate-spin text-primary" style={{ fontSize: 40 }}>
              progress_activity
            </span>
          </div>
        ) : items.length === 0 ? (
          <div className="flex flex-col items-center gap-3 py-24 text-center">
            <span className="material-symbols-outlined opacity-20" style={{ fontSize: 80 }}>rate_review</span>
            <p className="text-sm text-muted-foreground">No pending contributions at the moment.</p>
          </div>
        ) : (
          <ul className="divide-y divide-border/60">
            {items.map((c) => (
              <li key={c.id} className="group flex items-center gap-4 p-6 transition-colors hover:bg-muted/30">
                <div className="flex size-12 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
                  <span className="material-symbols-outlined" style={{ fontSize: 24 }}>edit_note</span>
                </div>
                <div className="min-w-0 flex-1">
                  <h3 className="truncate font-serif text-lg font-bold group-hover:text-primary">{c.title}</h3>
                  <p className="truncate text-sm text-muted-foreground">{c.description || "No description provided."}</p>
                  <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
                    <span className="inline-flex items-center gap-1">
                      <span className="material-symbols-outlined" style={{ fontSize: 14 }}>person</span>
                      {c.contributor_name}
                    </span>
                    <span className="inline-flex items-center gap-1">
                      <span className="material-symbols-outlined" style={{ fontSize: 14 }}>calendar_today</span>
                      {new Date(c.created_at).toLocaleDateString()}
                    </span>
                    <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-bold tracking-wider uppercase", TONE.amber)}>
                      Pending Review
                    </span>
                  </div>
                </div>
                <Button variant="outline" size="sm" className="shrink-0 text-primary" onClick={() => setReviewing(c)}>
                  <span className="material-symbols-outlined" style={{ fontSize: 16 }}>visibility</span>
                  Review
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <ContributionReviewDialog
        contribution={reviewing ? { id: reviewing.id, contributorName: reviewing.contributor_name } : null}
        labels={ADMIN_REVIEW_LABELS}
        onClose={() => setReviewing(null)}
        onSettled={onSettled}
      />
    </div>
  );
}
