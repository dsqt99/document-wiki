import assert from "node:assert/strict";
import test from "node:test";
import { summaryJobPresentation, summaryDetailControls, summaryJobEmptyMessage } from "../src/components/knowledge/summary-job-view.ts";

const job = (changes = {}) => ({ job_id: "one", status: "completed", total: 1, processed: 1,
  updated: 1, failed: 0, index_failed: 0, unchanged: 0, skipped: 0, ...changes });

test("completed results use past tense and omit empty statistics", () => {
  const result = summaryJobPresentation(job());
  assert.equal(result.title, "Kết quả cập nhật tóm tắt");
  assert.equal(result.label, "Hoàn tất");
  assert.equal(result.running, false);
  assert.deepEqual(result.metrics.map((item) => item.label), ["Đã xử lý", "Cập nhật"]);
  assert.ok(!result.description.includes("không dừng"));
});

test("queued and active jobs distinguish waiting from processing", () => {
  assert.equal(summaryJobPresentation(job({ status: "queued" })).label, "Đang chờ");
  const result = summaryJobPresentation(job({ status: "running" }));
  assert.equal(result.title, "Tiến trình cập nhật tóm tắt");
  assert.equal(result.running, true);
  assert.ok(result.description.includes("không dừng"));
});

test("index failures and failed jobs stay visibly actionable", () => {
  assert.equal(summaryJobPresentation(job({ index_failed: 1 })).label, "Cần kiểm tra");
  assert.equal(summaryJobPresentation(job({ status: "failed" })).warning, true);
  assert.ok(summaryJobPresentation(job({ index_failed: 1 })).metrics.some((item) => item.label === "Lỗi chỉ mục"));
});

test("small completed results omit search, pagination and refresh", () => {
  assert.deepEqual(summaryDetailControls({ total: 1, fullTotal: 1 }),
    { filters: false, pagination: false, refresh: false, compact: true });
});

test("filters remain usable after narrowing a large result to zero", () => {
  const controls = summaryDetailControls({ total: 0, fullTotal: 100, query: "unmatched" });
  assert.equal(controls.filters, true);
  assert.equal(controls.compact, false);
  assert.equal(controls.pagination, false);
  assert.equal(summaryDetailControls({ total: 1, fullTotal: 1, status: "failed" }).filters, true);
});

test("active work, fetch errors and later pages retain needed controls", () => {
  assert.equal(summaryDetailControls({ total: 1, fullTotal: 1, running: true }).refresh, true);
  assert.equal(summaryDetailControls({ total: 1, fullTotal: 1, error: true }).refresh, true);
  assert.equal(summaryDetailControls({ total: 1, fullTotal: 100, offset: 50 }).pagination, true);
});

test("a failed job without page rows never looks like successful no-work", () => {
  const message = summaryJobEmptyMessage({ warning: true });
  assert.ok(message.includes("chưa hoàn tất"));
  assert.ok(message.includes("chạy lại"));
  assert.ok(!message.includes("Không có trang cần cập nhật"));
});
