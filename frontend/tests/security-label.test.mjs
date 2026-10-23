import assert from "node:assert/strict";
import fs from "node:fs";
import { createRequire } from "node:module";
import test from "node:test";
import ts from "typescript";

const require = createRequire(import.meta.url);
const source = fs.readFileSync(new URL("../src/components/knowledge/security-label-select.tsx", import.meta.url), "utf8");
function loadSelect(user) {
  const compiled = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX,
  } }).outputText;
  const mod = { exports: {} };
  const deps = (name) => {
    if (name === "@/lib/auth") return { useAuth: () => ({ user }) };
    if (name === "@/components/ui/select") return Object.fromEntries(
      ["Select", "SelectContent", "SelectItem", "SelectTrigger", "SelectValue"].map((key) => [key, key]));
    if (name === "@/lib/security-label") return requirePolicy();
    return require(name);
  };
  new Function("require", "exports", "module", compiled)(deps, mod.exports, mod);
  return mod.exports.SecurityLabelSelect;
}
function requirePolicy() {
  const text = fs.readFileSync(new URL("../src/lib/security-label.ts", import.meta.url), "utf8");
  const mod = { exports: {} };
  new Function("exports", "module", ts.transpileModule(text, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020,
  } }).outputText)(mod.exports, mod);
  return mod.exports;
}
function values(node) {
  if (!node || typeof node !== "object") return [];
  if (Array.isArray(node)) return node.flatMap(values);
  return [...(node.type === "SelectItem" ? [node.props.value] : []), ...values(node.props?.children)];
}
test("PUBLIC uploader cannot select INTERNAL even with a stale initial value", () => {
  const Select = loadSelect({ role: "employee", clearance_level: "PUBLIC" });
  assert.deepEqual(values(Select({ value: "INTERNAL", onChange() {} })), ["PUBLIC"]);
});
test("INTERNAL uploader cannot select a higher stale label", () => {
  const Select = loadSelect({ role: "employee", clearance_level: "INTERNAL" });
  assert.deepEqual(values(Select({ value: "RESTRICTED", onChange() {} })), ["PUBLIC", "INTERNAL"]);
});
test("new uploads default within the uploader's clearance", () => {
  const { defaultSecurityLabel } = requirePolicy();
  assert.equal(defaultSecurityLabel({ clearance_level: "PUBLIC" }), "PUBLIC");
  assert.equal(defaultSecurityLabel({ clearance_level: "INTERNAL" }), "INTERNAL");
  assert.equal(defaultSecurityLabel({ clearance_level: "CONFIDENTIAL" }), "INTERNAL");
});
test("only backend-authorized editors can change existing labels", () => {
  const { canEditSecurityLabel } = requirePolicy();
  assert.equal(canEditSecurityLabel({ role: "employee", permissions: ["doc:edit:own_dept"] }), false);
  assert.equal(canEditSecurityLabel({ role: "employee", permissions: ["doc:edit:all"] }), true);
  assert.equal(canEditSecurityLabel({ role: "admin" }), true);
});
