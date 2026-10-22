"use client";

import { useCallback } from "react";
import { DropdownMenu, DropdownMenuContent, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { SummaryJobProgress, SummaryMaintenanceMenuGroup, SummarySourceNotes, useSummaryMaintenance } from "./summary-maintenance";
import { useAuth } from "@/lib/auth";
import { notifyWikiStore, wikiStore } from "@/lib/wiki-store";

export function WikiSummaryActions({ onComplete }: { onComplete: () => void }) {
  const { hasPermission } = useAuth();
  const enabled = hasPermission("org:settings:manage");
  const completed = useCallback(() => {
    wikiStore.pagesCache.clear();
    wikiStore.pageDetailCache.clear();
    notifyWikiStore();
    onComplete();
  }, [onComplete]);
  const maintenance = useSummaryMaintenance(enabled, completed);
  if (!enabled) return null;
  return <div className="space-y-3">
    <div className="flex justify-end">
      <DropdownMenu onOpenChange={(open) => { if (open) void maintenance.refresh(); }}>
        <DropdownMenuTrigger data-summary-result-trigger className="inline-flex h-9 items-center gap-2 rounded-lg border px-3 text-sm hover:bg-muted focus-visible:outline-2 focus-visible:outline-ring">
          <span aria-hidden="true" className="material-symbols-outlined text-[18px]!">short_text</span>
          Tóm tắt Wiki
          <span aria-hidden="true" className="material-symbols-outlined text-[18px]!">expand_more</span>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="min-w-72">
          <SummaryMaintenanceMenuGroup maintenance={maintenance} />
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
    <SummaryJobProgress job={maintenance.job} error={maintenance.error} onDismiss={maintenance.dismiss} onRetry={() => void maintenance.refresh()} onDetails={(trigger) => maintenance.openDetails(maintenance.job, trigger)} detailsOpen={maintenance.detailsOpen} />
    <SummarySourceNotes maintenance={maintenance} />
  </div>;
}
