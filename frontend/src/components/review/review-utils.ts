// Shared types and small helpers for the branch review desk (/wiki/review).
import type { DraftResponse } from "@/types/wiki";

/** Queue filter value kept in the `status` URL parameter. */
export type QueueStatus = "pending" | "needs_revision" | "approved" | "rejected";

export const QUEUE_STATUSES: { value: QueueStatus; key: string; fallback: string; branchStatus: string }[] = [
  { value: "pending", key: "review.statusPending", fallback: "Chờ duyệt", branchStatus: "pending_merge" },
  { value: "needs_revision", key: "review.statusNeedsRevision", fallback: "Cần chỉnh sửa", branchStatus: "draft" },
  { value: "approved", key: "review.statusApproved", fallback: "Đã duyệt", branchStatus: "merged" },
  { value: "rejected", key: "review.statusRejected", fallback: "Đã từ chối", branchStatus: "closed" },
];

/** Branch status sent to the API for a queue filter; unknown values fall back to pending_merge. */
export function branchStatusFor(status: string | null | undefined): string {
  return QUEUE_STATUSES.find((s) => s.value === status)?.branchStatus ?? "pending_merge";
}

/**
 * One row of GET /api/wiki/branches. The optional draft-like fields are not sent by the
 * backend today; they are only read by the "Compare with" picker.
 */
export interface BranchListItem {
  id: string;
  name: string;
  description: string | null;
  scope_type: string | null;
  scope_id: string | null;
  author_name: string | null;
  created_at: string;
  has_conflict: boolean;
  draft_count: number;
  page_id?: string | null;
  draft_kind?: string | null;
  content_md?: string | null;
  revision_round?: number | null;
}

export interface BranchDetail {
  id: string;
  name: string;
  description: string | null;
  has_conflict: boolean;
  drafts: DraftResponse[];
}

/** Scope filter key of a branch: "global" or "<scope_type>:<scope_id>". */
export function scopeKeyOf(b: Pick<BranchListItem, "scope_type" | "scope_id">): string {
  if (!b.scope_type || b.scope_type === "global") return "global";
  return `${b.scope_type}:${b.scope_id ?? ""}`;
}

export function scopeOptionsOf(items: BranchListItem[]): { value: string; label: string }[] {
  const seen = new Map<string, string>();
  for (const b of items) {
    const key = scopeKeyOf(b);
    if (!seen.has(key)) seen.set(key, key === "global" ? "Global" : `Scope: ${b.scope_type}`);
  }
  const rest = [...seen.entries()]
    .filter(([k]) => k !== "global")
    .map(([value, label]) => ({ value, label }))
    .sort((a, b) => a.label.localeCompare(b.label));
  return seen.has("global") ? [{ value: "global", label: seen.get("global")! }, ...rest] : rest;
}

/** "just now", "5m ago", "3h ago", "2d ago", or a short day + month date. */
export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const then = new Date(iso);
  const ms = then.getTime();
  if (Number.isNaN(ms)) return "";
  const sec = Math.floor((Date.now() - ms) / 1000);
  if (sec < 60) return "just now";
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hours = Math.floor(min / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return then.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

export const AI_ACTIVE_STATES = new Set(["pending", "running", "queued"]);

/** Encode a wiki slug for a URL path while keeping its "/" separators. */
export function slugPath(slug: string): string {
  return slug.split("/").map(encodeURIComponent).join("/");
}

export function errorMessage(err: unknown, fallback: string): string {
  if (err instanceof Error && err.message) return err.message;
  return fallback;
}

export type NoteMode = "reject" | "changes";

export type MiddleTab = "diff" | "proposed" | "current";
