import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createRequire } from 'node:module';
import test from 'node:test';
import ts from 'typescript';

const require = createRequire(import.meta.url);
const source = fs.readFileSync(new URL('../src/components/knowledge/knowledge-table/status-dot.tsx', import.meta.url), 'utf8');
const mod = {exports: {}};
new Function('require', 'exports', 'module', ts.transpileModule(source, {compilerOptions: {
  module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX,
}}).outputText)((name) => {
  if (name === '@/lib/i18n') return {useI18n: () => ({t: (_, fallback) => fallback})};
  if (name === '@/lib/utils') return {cn: (...args) => args.join(' ')};
  if (name === './processing-quality') return {qualitySummary: () => null};
  return require(name);
}, mod.exports, mod);

for (const status of ['processing', 'pending', 'partial', 'error']) {
  test(`${status} shows actionable status without provider internals`, () => {
    const raw = 'InternalServerError: http://qwen-embedding:8000/v1 Authorization Bearer secret';
    const rendered = JSON.stringify(mod.exports.StatusDot({source: {
      status, progress: 23, progress_message: raw, chunk_status: 'error',
      chunk_error_message: raw, wiki_status: 'refining', error_message: raw,
    }}));
    assert.doesNotMatch(rendered, /qwen-embedding|Bearer|InternalServerError|secret/);
    assert.match(rendered, /[Cc]hỉ mục/);
  });
}
