// Run from frontend: node scripts/check-wiki-navigation.mjs
import assert from "node:assert/strict";
import fs from "node:fs";
import ts from "typescript";

const source = fs.readFileSync(new URL("../src/lib/wiki-navigation.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
const navigation = { exports: {} };
new Function("exports", "module", compiled)(navigation.exports, navigation);
const { sanitizeWikiLibraryReturnTo, wikiPageQuery } = navigation.exports;

const fallback = "/wiki/law?view=wiki";
for (const unsafe of [
  null, "", "https://example.com/knowledge", "//example.com/knowledge",
  "javascript:alert(1)", "/other?tab=wiki", "/knowledge/", "/knowledge/../knowledge",
  "/%6bnowledge", "/knowledge\\evil", "/knowledge\n?tab=wiki",
]) {
  assert.equal(sanitizeWikiLibraryReturnTo(unsafe), fallback, `Reject unsafe destination: ${unsafe}`);
}

const context = "/knowledge?tab=documents&wiki_q=t%C3%B3m+t%E1%BA%AFt&wiki_source=source-1&wiki_type=concept&wiki_status=mature&wiki_page=3&unrelated=keep#results";
const safe = sanitizeWikiLibraryReturnTo(context);
const returned = new URL(safe, "https://wiki.test");
assert.equal(returned.pathname, "/wiki/law");
assert.equal(returned.searchParams.get("view"), "wiki");
assert.equal(returned.searchParams.get("wiki_q"), "tóm tắt");
assert.equal(returned.searchParams.get("wiki_source"), "source-1");
assert.equal(returned.searchParams.get("wiki_type"), "concept");
assert.equal(returned.searchParams.has("wiki_status"), false);
assert.equal(returned.searchParams.get("wiki_page"), "3");
assert.equal(returned.searchParams.get("unrelated"), "keep");
assert.equal(returned.hash, "#results");

assert.equal(sanitizeWikiLibraryReturnTo("/wiki/law?view=wiki&wiki_page=2"), "/wiki/law?view=wiki&wiki_page=2");
assert.equal(returned.searchParams.has("tab"), false);

// The same query builder serves library read/edit links, in-place navigation and scope changes.
const scoped = new URLSearchParams(wikiPageQuery("department", "dept-1", context, true));
assert.equal(scoped.get("scopeType"), "department");
assert.equal(scoped.get("scopeId"), "dept-1");
assert.equal(scoped.get("edit"), "1");
assert.equal(scoped.get("returnTo"), safe);
const nextPage = new URLSearchParams(wikiPageQuery("department", "dept-1", scoped.get("returnTo")));
assert.equal(nextPage.get("returnTo"), safe);
assert.equal(nextPage.has("edit"), false);
const globalPage = new URLSearchParams(wikiPageQuery("global", null, nextPage.get("returnTo")));
assert.equal(globalPage.has("scopeType"), false);
assert.equal(globalPage.has("scopeId"), false);
assert.equal(globalPage.get("returnTo"), safe);
assert.equal(new URLSearchParams(wikiPageQuery(null, null, "//example.com")).get("returnTo"), fallback);
console.log("Wiki navigation regression checks passed.");
