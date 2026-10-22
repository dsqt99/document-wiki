import assert from "node:assert/strict";
import fs from "node:fs";
import ts from "typescript";

const file = new URL("../src/lib/extracted-headings.ts", import.meta.url);
const compiled = ts.transpileModule(fs.readFileSync(file, "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
const mod = { exports: {} };
new Function("exports", "module", compiled)(mod.exports, mod);
const { normalizeExtractedHeadings } = mod.exports;

const citations = [
  "### Điều 41 của Nghị định này thì bị xử phạt vi phạm hành chính theo quy định tại",
  "### Điều 85 của Luật Xử lý vi phạm hành chính.",
  "## Chương II của Nghị định này là mức phạt tiền đối với cá nhân; trường hợp có",
  "### **Điều 2 và Điều 3 của Luật số 107/2025/QH15**",
  "### <mark>Điều 5; Điều 6; khoản 1 Điều 7;</mark>",
  "### Mục 2 của Chương III quy định như sau:",
  "## Chương IIIa của Nghị định này quy định như sau:",
  "### Điều 10 Nghị định này;",
  "### Điều 42 Luật số 15/2012/QH13;",
];
for (const citation of citations) {
  assert.equal(normalizeExtractedHeadings(citation), citation.replace(/^#+\s+/, ""), citation);
}

const headings = ["## Chương II", "### Mục 1", "### Điều 4a. Thi hành các hình thức xử phạt<sup>4</sup>",
  "### Điều 2: nguyên tắc thực hiện", "### Điều 5 Vi phạm quy định", "## Hướng dẫn sử dụng", "## Chương IIIa"];
for (const heading of headings) assert.equal(normalizeExtractedHeadings(heading), heading);

const fenced = "```md\n### Điều 85 của Luật Xử lý vi phạm hành chính.\n```";
assert.equal(normalizeExtractedHeadings(fenced), fenced);
const indented = "    ### Điều 85 của Luật Xử lý vi phạm hành chính.";
assert.equal(normalizeExtractedHeadings(indented), indented);
const body = "Nội dung dẫn chiếu tại\n### Điều 85 của Luật Xử lý vi phạm hành chính.\nNgười có thẩm quyền tiếp tục thực hiện.";
assert.equal(normalizeExtractedHeadings(body), body.replace("### ", ""));
assert.equal(normalizeExtractedHeadings(normalizeExtractedHeadings(body)), normalizeExtractedHeadings(body));
const bareReference = "Theo các điều sau: Điều 5; Điều 40;\n\n### Điều 41.\nNội dung tiếp tục.";
assert.equal(normalizeExtractedHeadings(bareReference), bareReference.replace("### ", ""));
assert.equal(normalizeExtractedHeadings("Nội dung trước.\n### Điều 41.\nTiêu đề điều mới"), "Nội dung trước.\n### Điều 41.\nTiêu đề điều mới");
console.log("Extracted document heading checks passed.");
