import assert from "node:assert/strict";
import fs from "node:fs";
import ts from "typescript";

const source = fs.readFileSync(new URL("../src/lib/source-workflow.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;
const mod = { exports: {} };
new Function("exports", "module", compiled)(mod.exports, mod);
const { deletionImpact, needsSourcePolling, nextUploadReview } = mod.exports;

const pages = [
  { slug: "same", scope_type: "global", source_ids: ["a"], title: "A" },
  { slug: "same", scope_type: "department", scope_id: "dept", source_ids: ["a", "b"], title: "AB" },
  { slug: "shared", scope_type: "global", source_ids: ["b", "c"], title: "BC" },
];
assert.equal(deletionImpact([...pages, pages[0]], ["a"]).removed.length, 1);
const together = deletionImpact([...pages, pages[0]], ["a", "b"]);
assert.equal(together.removed.length, 2);
assert.equal(together.retained.length, 1);
assert.equal(needsSourcePolling({ status: "awaiting_approval" }), false);
assert.equal(needsSourcePolling({ status: "processing" }), true);
assert.equal(needsSourcePolling({ status: "ready" }), false);
const queue = [{ id: "a", upload_review_status: "pending" }, { id: "b", upload_review_status: "awaiting" }];
assert.equal(nextUploadReview(queue, new Set()), undefined, "Bulk uploads must not open modal review automatically");
assert.equal(nextUploadReview([queue[1]], new Set())?.id, "b");
assert.equal(nextUploadReview(queue, new Set(["b"])), undefined);
console.log("Source workflow checks passed.");
