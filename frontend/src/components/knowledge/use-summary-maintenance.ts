"use client";

import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import {
  initialSummaryJobState, isSummaryJobActive, summaryJobReducer,
  type SummaryCounts, type SummaryJob,
} from "./summary-job-state";

export function useSummaryMaintenance(enabled: boolean, onComplete: () => void) {
  const [state, dispatch] = useReducer(summaryJobReducer, initialSummaryJobState);
  const [sourceNotesOpen, setSourceNotesOpen] = useState(false);
  const [confirmAllOpen, setConfirmAllOpen] = useState(false);
  const epoch = useRef(0);
  const mounted = useRef(false);
  const submitting = useRef(false);
  const statusRequest = useRef(0);
  const completed = useRef(new Set<string>());
  const onCompleteRef = useRef(onComplete);
  const detailsTrigger = useRef<HTMLElement | null>(null);

  useEffect(() => { onCompleteRef.current = onComplete; }, [onComplete]);
  const invalidateRequests = useCallback(() => ++epoch.current, []);

  const refresh = useCallback(async () => {
    if (!enabled || !mounted.current) return;
    const requestEpoch = epoch.current;
    const requestId = ++statusRequest.current;
    try {
      const counts = await api<SummaryCounts>("/api/wiki/summaries/status");
      if (!mounted.current || requestEpoch !== epoch.current || requestId !== statusRequest.current) return;
      dispatch({ type: "snapshot", epoch: requestEpoch, counts });
    } catch (err) {
      if (!mounted.current || requestEpoch !== epoch.current || requestId !== statusRequest.current) return;
      dispatch({ type: "error", epoch: requestEpoch,
        message: err instanceof Error ? err.message : "Không tải được trạng thái tóm tắt." });
    }
  }, [enabled]);

  useEffect(() => {
    mounted.current = enabled;
    submitting.current = false;
    const nextEpoch = invalidateRequests();
    dispatch({ type: "session", epoch: nextEpoch });
    if (enabled) void refresh();
    return () => {
      mounted.current = false;
      invalidateRequests();
      submitting.current = false;
    };
  }, [enabled, refresh, invalidateRequests]);

  // Callback delivery is outside the reducer, including under Strict Mode replay.
  useEffect(() => {
    if (!enabled) return;
    for (const id of state.completionIds) {
      if (completed.current.has(id)) continue;
      completed.current.add(id);
      onCompleteRef.current();
    }
  }, [enabled, state.completionIds]);

  const activeId = isSummaryJobActive(state.trackedJob) ? state.trackedJob?.job_id : null;
  useEffect(() => {
    if (!enabled || !activeId) return;
    const requestEpoch = epoch.current;
    let cancelled = false;
    let fetching = false;
    const timer = setInterval(async () => {
      if (fetching) return;
      fetching = true;
      try {
        const job = await api<SummaryJob>(`/api/wiki/summaries/jobs/${encodeURIComponent(activeId)}`);
        if (cancelled || !mounted.current || requestEpoch !== epoch.current) return;
        dispatch({ type: "receive", epoch: requestEpoch, job, source: "poll", expectedJobId: activeId });
        if (!isSummaryJobActive(job)) void refresh();
      } catch (err) {
        if (cancelled || !mounted.current || requestEpoch !== epoch.current) return;
        if (err instanceof ApiError && err.status === 404) {
          dispatch({ type: "expired", epoch: requestEpoch, expectedJobId: activeId });
        } else {
          dispatch({ type: "error", epoch: requestEpoch,
            message: err instanceof Error ? err.message : "Không đọc được tiến độ. Đang thử lại..." });
        }
      } finally {
        fetching = false;
      }
    }, 2000);
    return () => { cancelled = true; clearInterval(timer); };
  }, [enabled, activeId, state.epoch, refresh]);

  const start = async (onlyMissing: boolean, pageIds?: string[], confirmed = false) => {
    if (!enabled || !mounted.current || submitting.current || isSummaryJobActive(state.trackedJob)) return;
    if (!onlyMissing && !pageIds && !confirmed) { setConfirmAllOpen(true); return; }
    setConfirmAllOpen(false);
    submitting.current = true;
    const requestEpoch = invalidateRequests();
    dispatch({ type: "session", epoch: requestEpoch, starting: true });
    dispatch({ type: "error", epoch: requestEpoch, message: null });
    try {
      const job = await api<SummaryJob>("/api/wiki/summaries/rebuild", {
        method: "POST", body: { only_missing: onlyMissing, engine: "llm", ...(pageIds ? { page_ids: pageIds } : {}) },
      });
      if (!mounted.current || requestEpoch !== epoch.current) return;
      dispatch({ type: "receive", epoch: requestEpoch, job, source: "start" });
      if (!isSummaryJobActive(job)) void refresh();
    } catch (err) {
      if (!mounted.current || requestEpoch !== epoch.current) return;
      dispatch({ type: "error", epoch: requestEpoch,
        message: err instanceof Error ? err.message : "Không chạy được tác vụ tóm tắt." });
    } finally {
      if (mounted.current && requestEpoch === epoch.current) {
        submitting.current = false;
        dispatch({ type: "finish-start", epoch: requestEpoch });
      }
    }
  };

  const openDetails = (job?: SummaryJob | null, trigger?: HTMLElement | null) => {
    const activeElement = typeof document !== "undefined" && document.activeElement instanceof HTMLElement
      ? document.activeElement : null;
    detailsTrigger.current = trigger ?? activeElement;
    dispatch({ type: "open-details", job });
  };
  const detailsReturnFocus = useCallback(() => {
    if (detailsTrigger.current?.isConnected) return detailsTrigger.current;
    return typeof document === "undefined" ? false
      : document.querySelector<HTMLElement>("[data-summary-result-trigger]") ?? false;
  }, []);
  const dismiss = useCallback(() => dispatch({ type: "dismiss" }), []);

  return {
    counts: state.counts,
    job: enabled ? state.noticeJob : null,
    recentJob: enabled ? state.recentJob : null,
    error: enabled ? state.error : null,
    busy: enabled && (state.starting || isSummaryJobActive(state.trackedJob)),
    detailsJob: enabled ? state.detailsJob : null,
    detailsOpen: enabled && state.detailsOpen,
    openDetails, closeDetails: () => dispatch({ type: "close-details" }), detailsReturnFocus,
    confirmAllOpen: enabled && confirmAllOpen,
    closeConfirmation: () => setConfirmAllOpen(false),
    confirmAll: () => start(false, undefined, true),
    refresh, start,
    sourceNotesOpen: enabled && sourceNotesOpen,
    openSourceNotes: () => setSourceNotesOpen(true),
    closeSourceNotes: () => setSourceNotesOpen(false),
    dismiss,
  };
}
