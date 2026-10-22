import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import ts from "typescript";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

const require = createRequire(import.meta.url);
// Compile these isolated presentation modules without a browser or new test dependency.
const previous = new Map([".ts", ".tsx"].map((extension) => [extension, require.extensions[extension]]));
for (const extension of previous.keys()) {
  require.extensions[extension] = (module, filename) => {
    const result = ts.transpileModule(readFileSync(filename, "utf8"), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
      fileName: filename,
    });
    module._compile(result.outputText, filename);
  };
}
let QualityPanel;
try {
  ({ QualityPanel } = require("../src/components/knowledge/knowledge-table/quality-panel.tsx"));
} finally {
  for (const [extension, handler] of previous) {
    if (handler) require.extensions[extension] = handler;
    else delete require.extensions[extension];
  }
}

test("quality panel renders three named stages and unknown counters for legacy sources", () => {
  const html = renderToStaticMarkup(createElement(QualityPanel, {}));
  for (const label of ["Trích xuất nội dung", "Chỉ mục nguồn gốc", "Biên soạn Wiki"]) assert.ok(html.includes(label));
  assert.equal((html.match(/Chưa xác định/g) ?? []).length, 3);
  assert.ok(html.includes("Chưa rõ / Chưa rõ"));
  assert.ok(html.includes("<dl"));
});

test("quality panel surfaces full warning messages as escaped text", () => {
  const html = renderToStaticMarkup(createElement(QualityPanel, {
    quality: { warnings: [{ code: "index_failure", message: "Không lập chỉ mục <đoạn 3>; chạy lại chỉ mục nguồn." }] },
  }));
  assert.ok(html.includes("Không lập chỉ mục &lt;đoạn 3&gt;; chạy lại chỉ mục nguồn."));
  assert.ok(html.includes("Cần kiểm tra"));
});
