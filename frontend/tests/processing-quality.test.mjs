import assert from "node:assert/strict";
import test from "node:test";
import { qualityStages, qualitySummary } from "../src/components/knowledge/knowledge-table/processing-quality.ts";

const complete = () => ({
  extraction: { status: "complete", total_pages: 10, text_pages: 10, empty_pages: 0, ocr_pages: 2 },
  source_index: { status: "ready", expected: 20, indexed: 20 },
  wiki: { status: "complete", expected: 4, published: 4, failed: 0 },
  warnings: [],
});

test("legacy sources never imply measured coverage from ready status or Wiki page count", () => {
  assert.deepEqual(qualityStages().map((stage) => stage.status), ["unknown", "unknown", "unknown"]);
  assert.equal(qualitySummary({ status: "ready", wiki_page_count: 7 }), "Chưa đo độ bao phủ");
});

test("known zero counters stay zero and unknown counters stay explicit", () => {
  const report = complete();
  report.extraction.empty_pages = 0;
  report.source_index.indexed = null;
  const stages = qualityStages(report);
  assert.equal(stages[0].metrics.find((metric) => metric.label === "Trang trống / bỏ qua").value, "0");
  assert.equal(stages[1].status, "unknown");
  assert.equal(stages[1].metrics[0].value, "Chưa rõ / 20");
});

test("incomplete extraction and publication cannot be presented as complete", () => {
  const report = complete();
  report.extraction.text_pages = 8;
  report.extraction.empty_pages = 2;
  report.wiki.published = 3;
  report.wiki.failed = 1;
  assert.deepEqual(qualityStages(report).map((stage) => stage.status), ["partial", "ready", "partial"]);
  assert.equal(qualitySummary({ status: "ready", processing_quality: report }), "Độ bao phủ chưa đầy đủ");
});

test("active and blocked statuses remain distinct without inventing completion", () => {
  const report = complete();
  report.source_index.status = "processing";
  report.source_index.indexed = 5;
  report.wiki.status = "blocked";
  assert.deepEqual(qualityStages(report).map((stage) => stage.status), ["complete", "processing", "blocked"]);
  assert.equal(qualitySummary({ status: "ready", processing_quality: report }), "Có bước lỗi hoặc bị chặn");
});

test("complete requires measured counts; style warnings alone do not imply failed coverage", () => {
  const report = complete();
  report.warnings.push({ code: "style", message: "Cần rà soát cách trình bày" });
  assert.equal(qualitySummary({ status: "ready", processing_quality: report }), null);
  report.extraction.total_pages = null;
  assert.equal(qualityStages(report)[0].status, "unknown");
});

test("known warning codes become actionable Vietnamese with measured counters", async () => {
  const { qualityWarningText } = await import("../src/components/knowledge/knowledge-table/processing-quality.ts");
  const report = complete();
  report.extraction.empty_pages = 2;
  assert.equal(qualityWarningText({ code: "empty_pages", message: "2 extracted pages have no text." }, report), "2 trang không có văn bản. Đối chiếu tệp gốc và chạy lại trích xuất nếu cần.");
  for (const code of ["unprocessed_pages", "review_expired", "embedding_unavailable", "no_source_chunks", "source_index_incomplete", "wiki_pages_skipped", "wiki_index_failed"]) {
    const message = qualityWarningText({ code, message: "English diagnostic" }, report);
    assert.notEqual(message, "English diagnostic");
    assert.ok(message.length > 20);
  }
  assert.equal(qualityWarningText({ code: "future_warning", message: "Chi tiết cảnh báo mới" }, report), "Chi tiết cảnh báo mới");
});
