import type { SummaryJobItem } from "./summary-job-details";

export type SummaryJob = {
  job_id: string;
  status: "queued" | "running" | "completed" | "failed";
  only_missing: boolean;
  engine?: "llm" | "extract";
  total: number;
  processed: number;
  updated: number;
  failed: number;
  index_failed: number;
  message: string;
  errors: string[];
  unchanged?: number;
  skipped?: number;
  current?: Pick<SummaryJobItem, "page_id" | "title" | "slug" | "scope_type" | "scope_id" | "stage" | "status" | "message"> | null;
};

export type SummaryCounts = {
  total: number;
  needs_update: number;
  active_job: SummaryJob | null;
  recent_job?: SummaryJob | null;
  source_matches_count?: number;
  source_matches?: SummaryJobItem[];
};

export const isSummaryJobActive = (job: SummaryJob | null | undefined) =>
  !!job && (job.status === "queued" || job.status === "running");

export const isSummaryJobWarning = (job: SummaryJob | null | undefined) =>
  !!job && (job.status === "failed" || job.failed > 0 || job.index_failed > 0);

export type SummaryJobState = {
  epoch: number;
  counts: SummaryCounts | null;
  trackedJob: SummaryJob | null;
  recentJob: SummaryJob | null;
  noticeJob: SummaryJob | null;
  detailsJob: SummaryJob | null;
  detailsOpen: boolean;
  starting: boolean;
  dismissedIds: readonly string[];
  completionIds: readonly string[];
  error: string | null;
};

export const initialSummaryJobState: SummaryJobState = {
  epoch: 0, counts: null, trackedJob: null, recentJob: null, noticeJob: null,
  detailsJob: null, detailsOpen: false, starting: false,
  dismissedIds: [], completionIds: [], error: null,
};

export type SummaryJobAction =
  | { type: "session"; epoch: number; starting?: boolean }
  | { type: "snapshot"; epoch: number; counts: SummaryCounts }
  | { type: "receive"; epoch: number; job: SummaryJob; source: "poll" | "start"; expectedJobId?: string }
  | { type: "expired"; epoch: number; expectedJobId: string }
  | { type: "error"; epoch: number; message: string | null }
  | { type: "finish-start"; epoch: number }
  | { type: "open-details"; job?: SummaryJob | null }
  | { type: "close-details" }
  | { type: "dismiss" };

function acceptJob(state: SummaryJobState, next: SummaryJob, started: boolean): SummaryJobState {
  const previous = state.trackedJob;
  const sameJob = previous?.job_id === next.job_id;
  if (sameJob && !isSummaryJobActive(previous) && isSummaryJobActive(next)) return state;
  const observed = started || (sameJob && isSummaryJobActive(previous));
  const completed = !isSummaryJobActive(next) && observed && !state.completionIds.includes(next.job_id);
  const visible = !state.dismissedIds.includes(next.job_id)
    && (started || isSummaryJobActive(next) || (sameJob && state.noticeJob?.job_id === next.job_id));
  return {
    ...state,
    trackedJob: next,
    recentJob: next,
    noticeJob: visible ? next : null,
    detailsJob: state.detailsJob?.job_id === next.job_id ? next : state.detailsJob,
    completionIds: completed ? [...state.completionIds, next.job_id] : state.completionIds,
    error: null,
  };
}

/** Request epochs reject responses from an older start or enabled session. */
export function summaryJobReducer(state: SummaryJobState, action: SummaryJobAction): SummaryJobState {
  if (action.type === "session") return { ...state, epoch: action.epoch, starting: action.starting ?? false };
  if (action.type === "open-details") {
    const selected = action.job ?? state.noticeJob ?? state.recentJob;
    return selected ? { ...state, detailsJob: selected, detailsOpen: true } : state;
  }
  if (action.type === "close-details") return { ...state, detailsOpen: false };
  if (action.type === "dismiss") return {
    ...state, noticeJob: null, error: null,
    dismissedIds: state.noticeJob && !state.dismissedIds.includes(state.noticeJob.job_id)
      ? [...state.dismissedIds, state.noticeJob.job_id] : state.dismissedIds,
  };
  if (action.epoch !== state.epoch) return state;
  if (action.type === "finish-start") return { ...state, starting: false };
  if (action.type === "error") return { ...state, error: action.message };
  if (action.type === "snapshot") {
    const next = action.counts.active_job || action.counts.recent_job;
    const updated = { ...state, counts: action.counts, error: null };
    if (!next) return updated;
    // A retained older result cannot displace work already being polled.
    if (!action.counts.active_job && isSummaryJobActive(state.trackedJob)
      && state.trackedJob?.job_id !== next.job_id) return updated;
    return acceptJob(updated, next, false);
  }
  if (action.type === "expired") {
    if (state.trackedJob?.job_id !== action.expectedJobId || !isSummaryJobActive(state.trackedJob)) return state;
    return acceptJob(state, {
      ...state.trackedJob, status: "failed",
      message: "Thông tin tác vụ đã hết hạn. Vui lòng kiểm tra và chạy lại.",
    }, false);
  }
  if (action.source === "poll" && (state.trackedJob?.job_id !== action.expectedJobId
    || action.job.job_id !== action.expectedJobId)) return state;
  return acceptJob(state, action.job, action.source === "start");
}
