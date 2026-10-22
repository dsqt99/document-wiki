import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { createRequire, Module } from "node:module";
import { fileURLToPath } from "node:url";
import ts from "typescript";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

const require = createRequire(import.meta.url);
const resolveFilename = Module._resolveFilename;
const handlers = new Map([".ts", ".tsx"].map((ext) => [ext, require.extensions[ext]]));
Module._resolveFilename = function(request, ...args) {
  return resolveFilename.call(this, request.startsWith("@/") ? fileURLToPath(new URL(`../src/${request.slice(2)}`, import.meta.url)) : request, ...args);
};
for (const ext of handlers.keys()) require.extensions[ext] = (module, filename) => {
  const result = ts.transpileModule(readFileSync(filename, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX }, fileName: filename,
  });
  module._compile(result.outputText, filename);
};
let SummaryJobResults;
try { ({ SummaryJobResults } = require("../src/components/knowledge/summary-job-results.tsx")); }
finally {
  Module._resolveFilename = resolveFilename;
  for (const [ext, handler] of handlers) {
    if (handler) require.extensions[ext] = handler;
    else delete require.extensions[ext];
  }
}
const item = { page_id: "one", title: "Đường link <chuyên mục>", slug: "duong-link", scope_type: "department", scope_id: "pc08",
  source_titles: ["07. Danh sách đường link.docx"], status: "updated", stage: "completed", message: "Đã lưu tóm tắt AI và cập nhật chỉ mục", updated_at: 0 };

test("one completed result renders document rows without a wide table", () => {
  const html = renderToStaticMarkup(createElement(SummaryJobResults, { items: [item], compact: true }));
  assert.ok(html.includes("<ul"));
  assert.ok(!html.includes("<table"));
  assert.ok(!html.includes("min-w-[640px]"));
  assert.ok(html.includes("Đường link &lt;chuyên mục&gt;"));
  assert.ok(html.includes(item.source_titles[0]));
  assert.ok(html.includes("scopeType=department&amp;scopeId=pc08"));
});

test("larger results retain desktop columns and a wrapping mobile list", () => {
  const html = renderToStaticMarkup(createElement(SummaryJobResults, { items: [item], compact: false }));
  assert.ok(html.includes("sm:hidden"));
  assert.ok(html.includes("sm:table"));
  assert.ok(html.includes("Bước xử lý &amp; chi tiết"));
});
