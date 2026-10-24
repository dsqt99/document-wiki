import assert from 'node:assert/strict';
import fs from 'node:fs';
import {createRequire} from 'node:module';
import test from 'node:test';
import ts from 'typescript';

const require = createRequire(import.meta.url);
test('expired iframe session asks host for top-level login without redirecting inside frame', async () => {
  const source = fs.readFileSync(process.env.LOGIN_TEST_SOURCE || new URL('../src/app/login/page.tsx', import.meta.url), 'utf8');
  const effects = [], posted = [], redirects = [];
  const mod = {exports: {}};
  const deps = (name) => {
    if (name === 'react') return {Suspense: 'Suspense', useEffect: (fn) => effects.push(fn),
      useRef: (v) => ({current: v}), useState: (v) => [v, () => {}]};
    if (name === 'next/navigation') return {useRouter: () => ({replace: (v) => redirects.push(v)}),
      useSearchParams: () => new URLSearchParams('next=%2Fknowledge')};
    if (name === '@/lib/auth') return {useAuth: () => ({user: null, loading: false})};
    if (name === '@/lib/api') return {api: async () => ({enabled: true, chatbot_login: true}), apiUrl: (v) => v};
    if (name === '@/lib/embed') return {isEmbedded: () => true, useIsEmbedded: () => true,
      postToHost: (v) => posted.push(v)};
    if (name === '@/lib/login-round') return {MAX_LOGIN_HOPS: 2, clearLoginRound() {}, readLoginRound: () => ({at: 0, hops: 0}), saveLoginRound() {}};
    if (name.startsWith('@/components/')) return new Proxy({}, {get: (_, key) => key});
    return require(name);
  };
  const js = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX}}).outputText;
  new Function('require', 'exports', 'module', 'window', js + '\nexports.testLogin = LoginOrchestrator;')(
    deps, mod.exports, mod, {location: {replace: (v) => redirects.push(v)}});
  mod.exports.testLogin();
  for (const effect of effects) effect();
  await new Promise(setImmediate);
  assert.deepEqual(posted, [{type: 'auth-required', path: '/knowledge'}]);
  assert.deepEqual(redirects, []);
});
