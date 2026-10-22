import type { Source } from "@/components/knowledge/types";

export type ImpactPage = {
  slug: string;
  title: string;
  scope_type?: string;
  scope_id?: string | null;
  source_ids: string[];
};

export function deletionImpact(pages: ImpactPage[], sourceIds: string[]) {
  const selected = new Set(sourceIds);
  const unique = new Map(pages.map((page) => [JSON.stringify([page.scope_type || "global", page.scope_id, page.slug]), page]));
  const affected = [...unique.values()];
  return {
    removed: affected.filter((page) => page.source_ids.every((id) => selected.has(id))),
    retained: affected.filter((page) => page.source_ids.some((id) => !selected.has(id))),
  };
}

export function needsSourcePolling(source: Pick<Source, "status">) {
  return source.status === "pending" || source.status === "processing";
}

export function nextUploadReview<T extends Pick<Source, "id" | "upload_review_status">>(sources: T[], deferred: Set<string>) {
  if (sources.length !== 1) return undefined;
  return sources.find((source) => source.upload_review_status === "awaiting" && !deferred.has(source.id));
}
