import assert from "node:assert/strict";
import test from "node:test";
import { initialSummaryJobState, summaryJobReducer, isSummaryJobActive, isSummaryJobWarning } from "../src/components/knowledge/summary-job-state.ts";

const job = (status = "completed", id = "job-a", overrides = {}) => ({ job_id: id, status, only_missing: true, total: 1, processed: status === "completed" ? 1 : 0, updated: 0, failed: 0, index_failed: 0, message: "", errors: [], ...overrides });
const snapshot = (state, recent, active = null, epoch = state.epoch) => summaryJobReducer(state, { type: "snapshot", epoch, counts: { total: 4, needs_update: 1, active_job: active, recent_job: recent } });
const receive = (state, next, source = "poll", expectedJobId = state.trackedJob?.job_id, epoch = state.epoch) => summaryJobReducer(state, { type: "receive", epoch, job: next, source, expectedJobId });

test("historical completed and failed results stay available without notices or completion events", () => {
  for (const status of ["completed", "failed"]) {
    const state = snapshot(initialSummaryJobState, job(status));
    assert.equal(state.noticeJob, null);
    assert.equal(state.recentJob.status, status);
    assert.deepEqual(state.completionIds, []);
  }
});

test("observed active work announces its terminal transition exactly once", () => {
  let state = snapshot(initialSummaryJobState, null, job("running"));
  assert.equal(state.noticeJob.status, "running");
  state = receive(state, job());
  assert.deepEqual(state.completionIds, ["job-a"]);
  assert.equal(state.noticeJob.status, "completed");
  state = snapshot(state, job());
  state = receive(state, job());
  assert.deepEqual(state.completionIds, ["job-a"]);
});

test("dismissal survives refresh and retains the latest result", () => {
  let state = receive(initialSummaryJobState, job(), "start");
  state = summaryJobReducer(state, { type: "dismiss" });
  state = snapshot(state, job());
  assert.equal(state.noticeJob, null);
  assert.equal(state.recentJob.job_id, "job-a");
  assert.deepEqual(state.completionIds, ["job-a"]);
});

test("a different active job appears after the previous result was dismissed", () => {
  let state = receive(initialSummaryJobState, job(), "start");
  state = summaryJobReducer(state, { type: "dismiss" });
  state = snapshot(state, job(), job("queued", "job-b"));
  assert.equal(state.noticeJob.job_id, "job-b");
  assert.equal(state.trackedJob.job_id, "job-b");
  assert.equal(isSummaryJobActive(state.trackedJob), true);
});

test("an immediately completed rebuild emits one completion including zero work", () => {
  const state = receive(initialSummaryJobState, job("completed", "empty", { total: 0 }), "start");
  assert.equal(state.noticeJob.job_id, "empty");
  assert.deepEqual(state.completionIds, ["empty"]);
});

test("a stale poll for a previous job cannot replace a newly started job", () => {
  let state = receive(initialSummaryJobState, job("running"), "start");
  state = receive(state, job("running", "job-b"), "start");
  const previous = state;
  state = receive(state, job(), "poll", "job-a");
  assert.equal(state, previous);
  assert.deepEqual(state.completionIds, []);
});

test("a terminal job cannot regress when an overlapping request returns active data", () => {
  let state = receive(initialSummaryJobState, job(), "start");
  state = receive(state, job("running"));
  state = snapshot(state, null, job("queued"));
  assert.equal(state.trackedJob.status, "completed");
  assert.equal(state.noticeJob.status, "completed");
  assert.deepEqual(state.completionIds, ["job-a"]);
});

test("request epochs ignore delayed status, errors and job responses after start or disable", () => {
  let state = snapshot(initialSummaryJobState, job());
  const oldEpoch = state.epoch;
  state = summaryJobReducer(state, { type: "session", epoch: oldEpoch + 1 });
  state = receive(state, job("running", "job-b"), "start");
  const current = state;
  assert.equal(snapshot(state, job(), null, oldEpoch), current);
  assert.equal(receive(state, job(), "start", undefined, oldEpoch), current);
  assert.equal(summaryJobReducer(state, { type: "error", epoch: oldEpoch, message: "stale" }), current);
});

test("a refresh failure is clearable without reviving historical notices", () => {
  let state = snapshot(initialSummaryJobState, job());
  state = summaryJobReducer(state, { type: "error", epoch: state.epoch, message: "Retry" });
  assert.equal(state.error, "Retry");
  state = snapshot(state, job());
  assert.equal(state.error, null);
  assert.equal(state.noticeJob, null);
});

test("missing active jobs become actionable terminal failures and stop polling", () => {
  let state = receive(initialSummaryJobState, job("running"), "start");
  state = summaryJobReducer(state, { type: "expired", epoch: state.epoch, expectedJobId: "job-a" });
  assert.equal(state.trackedJob.status, "failed");
  assert.equal(isSummaryJobActive(state.trackedJob), false);
  assert.match(state.noticeJob.message, /hết hạn.*chạy lại/);
  assert.deepEqual(state.completionIds, ["job-a"]);
});

test("warning classification includes failed jobs and partial page or index failures", () => {
  assert.equal(isSummaryJobWarning(job()), false);
  assert.equal(isSummaryJobWarning(null), false);
  assert.equal(isSummaryJobWarning(job("failed")), true);
  assert.equal(isSummaryJobWarning(job("completed", "a", { failed: 1 })), true);
  assert.equal(isSummaryJobWarning(job("completed", "a", { index_failed: 1 })), true);
});

test("details remain open when a notice is dismissed and track only their selected job", () => {
  let state = receive(initialSummaryJobState, job("running"), "start");
  state = summaryJobReducer(state, { type: "open-details" });
  state = summaryJobReducer(state, { type: "dismiss" });
  assert.equal(state.detailsOpen, true);
  assert.equal(state.detailsJob.status, "running");
  state = receive(state, job());
  assert.equal(state.detailsJob.status, "completed");
  state = receive(state, job("running", "job-b"), "start");
  assert.equal(state.detailsJob.job_id, "job-a");
  state = summaryJobReducer(state, { type: "close-details" });
  assert.equal(state.detailsOpen, false);
});

test("a retained historical result can be opened without displaying a notice", () => {
  let state = snapshot(initialSummaryJobState, job());
  state = summaryJobReducer(state, { type: "open-details" });
  assert.equal(state.detailsJob.job_id, "job-a");
  assert.equal(state.detailsOpen, true);
  assert.equal(state.noticeJob, null);
  assert.deepEqual(state.completionIds, []);
});
