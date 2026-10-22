import assert from "node:assert/strict";
import fs from "node:fs";
import ts from "typescript";

// Compile the actual pure TOC/anchor functions without loading the React client.
const source = ts.createSourceFile("wiki-content.tsx", fs.readFileSync(new URL("../src/components/wiki/wiki-content.tsx", import.meta.url), "utf8"), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const names = new Set(["headingId", "stripInline", "extractToc", "hastText", "headingNodeText", "TocItem", "HastLike"]);
const body = source.statements.filter((node) => node.name && names.has(node.name.text)).map((node) => node.getText(source)).join("\n");
const compiled = ts.transpileModule(body + "\nmodule.exports = { extractToc, headingId, headingNodeText };", { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;
const mod = { exports: {} };
new Function("module", compiled)(mod);
const { extractToc, headingId, headingNodeText } = mod.exports;
const text = (value) => ({ type: "text", value });
const sup = (value) => ({ type: "element", tagName: "sup", children: [text(value)] });
const technical = extractToc("## Diện tích (m<sup>2</sup>)\n## Diện tích (m<sup>3</sup>)");
assert.deepEqual(technical.map((item) => item.text), ["Diện tích (m2)", "Diện tích (m3)"]);
assert.notEqual(technical[0].id, technical[1].id);
assert.equal(technical[0].id, headingId(headingNodeText({ children: [text("Diện tích (m"), sup("2"), text(")")] })));
const legal = extractToc("### Điều 46<sup>33</sup>. (được bãi bỏ)");
assert.equal(legal[0].text, "Điều 46. (được bãi bỏ)");
assert.equal(legal[0].id, headingId(headingNodeText({ children: [text("Điều 46"), sup("33"), text(". (được bãi bỏ)")] })));
assert.deepEqual(extractToc("```md\n### Điều 46.\n```"), []);
console.log("Wiki heading footnote/anchor checks passed.");
