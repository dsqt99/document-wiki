// Run from frontend: node scripts/check-session-lifecycle.mjs
// Uses synthetic credentials and a fake browser only; never contacts an auth server.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import ts from "typescript";

const require = createRequire(import.meta.url);
const modules = new Map();
let hooks;
function loadModule(name) {
  let file = path.resolve("src/lib", `${name}.ts`);
  if (!fs.existsSync(file)) file += "x";
  if (modules.has(file)) return modules.get(file).exports;
  const compiled = ts.transpileModule(fs.readFileSync(file, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.React },
  }).outputText;
  const mod = { exports: {} };
  modules.set(file, mod);
  new Function("require", "exports", "module", compiled)(
    (specifier) => {
      if (specifier === "react") return {
        default: { createElement: (_type, props) => ({ props }) },
        createContext: () => ({ Provider: "provider-fixture" }),
        useState: (...args) => hooks.useState(...args),
        useRef: (...args) => hooks.useRef(...args),
        useEffect: (...args) => hooks.useEffect(...args),
        useCallback: (fn) => fn,
        useMemo: (fn) => fn(),
      };
      if (specifier.startsWith("@/lib/")) return loadModule(specifier.slice(6));
      return specifier.startsWith(".") ? loadModule(specifier.slice(2)) : require(specifier);
    },
    mod.exports, mod,
  );
  return mod.exports;
}

const store = new Map();
const browser = new EventTarget();
browser.localStorage = {
  getItem: (key) => store.get(key) ?? null,
  setItem: (key, value) => store.set(key, value),
  removeItem: (key) => store.delete(key),
};
globalThis.window = browser;
const tokenKey = "arkon_token";
const fixture = (exp, marker = "first") => `e30.${Buffer.from(JSON.stringify({ exp, marker })).toString("base64url")}.fixture`;
const first = fixture(2_000_000_000);
const second = fixture(2_000_000_001, "second");
const apiModule = loadModule("api");
const { api, apiUpload, clearToken, setToken } = apiModule;
const session = loadModule("session");
const tests = [];
const test = (name, run) => tests.push({ name, run });

test("authenticated API 401 clears the current token", async () => {
  setToken(first);
  globalThis.fetch = async () => new Response('{"detail":"expired"}', { status: 401 });
  await assert.rejects(api("/fixture"), (error) => error.status === 401);
  assert.ok(!store.has(tokenKey), "Expired credentials must be removed");
});

test("upload 401 clears the current token", async () => {
  setToken(first);
  globalThis.fetch = async () => new Response("{}", { status: 401 });
  await assert.rejects(apiUpload("/fixture", new FormData()), (error) => error.status === 401);
  assert.ok(!store.has(tokenKey), "Upload invalidation must match ordinary requests");
});

test("a slow old 401 cannot clear a newer login", async () => {
  setToken(first);
  let respond;
  globalThis.fetch = () => new Promise((resolve) => { respond = resolve; });
  const pending = api("/fixture");
  setToken(second);
  respond(new Response("{}", { status: 401 }));
  await assert.rejects(pending, (error) => error.status === 401);
  assert.ok(store.get(tokenKey) === second, "The newer login must survive");
});

test("403, 503 and network errors retain the session", async () => {
  for (const status of [403, 503]) {
    setToken(first);
    globalThis.fetch = async () => new Response("{}", { status });
    await assert.rejects(api("/fixture"), (error) => error.status === status);
    assert.ok(store.get(tokenKey) === first, "Non-authentication errors must retain credentials");
  }
  globalThis.fetch = async () => { throw new TypeError("offline fixture"); };
  await assert.rejects(api("/fixture"), TypeError);
  assert.ok(store.get(tokenKey) === first, "Network errors must retain credentials");
});

test("401 for an explicitly different authorization header retains the current session", async () => {
  setToken(second);
  globalThis.fetch = async () => new Response("{}", { status: 401 });
  await assert.rejects(api("/fixture", { headers: { Authorization: `Bearer ${first}` } }));
  assert.ok(store.get(tokenKey) === second, "Only the request credential may be invalidated");
});

function storageEvent(key = tokenKey) {
  const event = new Event("storage");
  Object.defineProperty(event, "key", { value: key });
  browser.dispatchEvent(event);
}

const flush = async () => { for (let i = 0; i < 20; i++) await Promise.resolve(); };
async function withClock(run) {
  assert.equal(typeof session.startSessionMonitor, "function", "Session monitoring must be implemented");
  const originals = { setTimeout, clearTimeout, setInterval, clearInterval, now: Date.now };
  let now = 1_000_000;
  let nextId = 0;
  const timers = new Map();
  const schedule = (fn, delay = 0, interval = 0) => {
    const id = ++nextId;
    timers.set(id, { fn, at: now + delay, interval });
    return id;
  };
  globalThis.setTimeout = (fn, delay) => schedule(fn, delay);
  globalThis.clearTimeout = (id) => timers.delete(id);
  globalThis.setInterval = (fn, delay) => schedule(fn, delay, delay);
  globalThis.clearInterval = (id) => timers.delete(id);
  Date.now = () => now;
  const doc = new EventTarget();
  doc.visibilityState = "visible";
  globalThis.document = doc;
  const monitors = [];
  const start = (fetchUser) => {
    let user = null;
    let loading = true;
    let error = null;
    const monitor = session.startSessionMonitor({
      fetchUser, onUser: (value) => { user = value; }, onLoading: (value) => { loading = value; },
      onError: (value) => { error = value; },
    });
    monitors.push(monitor);
    return { monitor, get user() { return user; }, get loading() { return loading; }, get error() { return error; } };
  };
  const tick = async (duration) => {
    const target = now + duration;
    for (;;) {
      const next = [...timers.entries()].filter(([, timer]) => timer.at <= target).sort((a, b) => a[1].at - b[1].at)[0];
      if (!next) break;
      const [id, timer] = next;
      now = timer.at;
      if (timer.interval) timer.at += timer.interval;
      else timers.delete(id);
      timer.fn();
      await flush();
    }
    now = target;
    await flush();
  };
  try { await run({ start, tick, doc, timers }); }
  finally {
    for (const monitor of monitors) monitor.stop();
    Object.assign(globalThis, { setTimeout: originals.setTimeout, clearTimeout: originals.clearTimeout, setInterval: originals.setInterval, clearInterval: originals.clearInterval });
    Date.now = originals.now;
    delete globalThis.document;
  }
}

test("clearToken immediately clears same-tab UI", () => withClock(async ({ start, tick }) => {
  setToken(fixture(1100));
  const state = start(async () => ({ id: "first-user" }));
  await tick(0);
  assert.ok(state.user);
  clearToken();
  assert.equal(state.user, null);
  assert.equal(state.loading, false);
}));

test("cross-tab token removal and storage clear clear open-tab UI", () => withClock(async ({ start, tick }) => {
  for (const eventKey of [tokenKey, null]) {
    setToken(fixture(1100));
    const state = start(async () => ({ id: "first-user" }));
    await tick(0);
    store.clear();
    storageEvent(eventKey);
    assert.equal(state.user, null);
    assert.equal(state.loading, false);
    state.monitor.stop();
  }
}));

test("JWT deadline clears UI without another backend request", () => withClock(async ({ start, tick }) => {
  setToken(fixture(1002));
  let calls = 0;
  const state = start(async () => { calls++; return { id: "first-user" }; });
  await tick(1999);
  assert.ok(state.user);
  await tick(1);
  assert.equal(state.user, null);
  assert.ok(!store.has(tokenKey));
  assert.equal(calls, 1);
}));

test("already-expired tokens never restore a profile", () => withClock(async ({ start, tick }) => {
  setToken(fixture(999));
  let calls = 0;
  const state = start(async () => { calls++; return { id: "expired" }; });
  await tick(0);
  assert.equal(state.user, null);
  assert.equal(state.loading, false);
  assert.equal(calls, 0);
  assert.ok(!store.has(tokenKey));
}));

test("idle revocation is checked every 30 seconds", () => withClock(async ({ start, tick }) => {
  setToken(fixture(1100));
  let calls = 0;
  const state = start(async () => {
    if (++calls > 1) throw { status: 401 };
    return { id: "first-user" };
  });
  await tick(29_999);
  assert.ok(state.user);
  await tick(1);
  assert.equal(calls, 2);
  assert.equal(state.user, null);
  assert.ok(!store.has(tokenKey));
}));

test("focus and visible-tab activation recheck the backend", () => withClock(async ({ start, tick, doc }) => {
  setToken(fixture(1100));
  let calls = 0;
  start(async () => { calls++; return { id: "first-user" }; });
  await tick(0);
  browser.dispatchEvent(new Event("focus"));
  await flush();
  assert.equal(calls, 2);
  doc.visibilityState = "hidden";
  doc.dispatchEvent(new Event("visibilitychange"));
  await flush();
  assert.equal(calls, 2);
  doc.visibilityState = "visible";
  doc.dispatchEvent(new Event("visibilitychange"));
  await flush();
  assert.equal(calls, 3);
}));

test("a delayed profile response cannot undo logout", () => withClock(async ({ start, tick }) => {
  setToken(fixture(1100));
  let resolveProfile;
  const state = start(() => new Promise((resolve) => { resolveProfile = resolve; }));
  await tick(0);
  clearToken();
  resolveProfile({ id: "old-user" });
  await flush();
  assert.equal(state.user, null);
  assert.equal(state.loading, false);
}));

test("token swaps refresh UI and ignore the old profile response", () => withClock(async ({ start, tick }) => {
  setToken(fixture(1100));
  let calls = 0;
  let resolveOld;
  const state = start(() => ++calls === 1 ? new Promise((resolve) => { resolveOld = resolve; }) : Promise.resolve({ id: "new-user" }));
  await tick(0);
  store.set(tokenKey, fixture(1101, "new"));
  storageEvent();
  await flush();
  assert.equal(state.user?.id, "new-user");
  resolveOld({ id: "old-user" });
  await flush();
  assert.equal(state.user?.id, "new-user");
}));

test("transient and permission errors preserve a verified user", () => withClock(async ({ start, tick }) => {
  setToken(fixture(1100));
  let failure;
  const state = start(async () => {
    if (failure) throw failure;
    return { id: "first-user" };
  });
  await tick(0);
  for (failure of [{ status: 403 }, { status: 503 }, new TypeError("offline fixture")]) {
    await state.monitor.refresh();
    assert.equal(state.user?.id, "first-user");
    assert.equal(state.loading, false);
    assert.ok(store.has(tokenKey));
  }
}));

test("a verifier outage during initial load waits for retry without logout", () => withClock(async ({ start, tick }) => {
  setToken(fixture(1100));
  let fail = true;
  const state = start(async () => {
    if (fail) throw new TypeError("offline fixture");
    return { id: "first-user" };
  });
  await tick(0);
  assert.equal(state.loading, true);
  assert.ok(state.error, "An initial outage must expose an error so the UI can offer retry");
  assert.ok(store.has(tokenKey));
  fail = false;
  await tick(30_000);
  assert.equal(state.user?.id, "first-user");
  assert.equal(state.loading, false);
  assert.equal(state.error, null);
}));

test("stop removes timers/listeners and ignores outstanding responses", () => withClock(async ({ start, tick, timers }) => {
  setToken(fixture(1100));
  let calls = 0;
  let resolveProfile;
  const state = start(() => { calls++; return new Promise((resolve) => { resolveProfile = resolve; }); });
  await tick(0);
  state.monitor.stop();
  assert.equal(timers.size, 0);
  browser.dispatchEvent(new Event("focus"));
  storageEvent();
  resolveProfile({ id: "stopped-user" });
  await flush();
  assert.equal(calls, 1);
  assert.equal(state.user, null);
}));

// A minimal hook adapter exercises the real provider without a DOM or extra package.
function mountProvider() {
  const slots = [];
  let cursor = 0;
  const pendingEffects = [];
  const cleanups = [];
  hooks = {
    useState(initial) {
      const id = cursor++;
      if (!(id in slots)) slots[id] = initial;
      return [slots[id], (value) => { slots[id] = value; }];
    },
    useRef(initial) {
      const id = cursor++;
      if (!(id in slots)) slots[id] = { current: initial };
      return slots[id];
    },
    useEffect(effect) {
      const id = cursor++;
      if (!(id in slots)) {
        slots[id] = true;
        pendingEffects.push(effect);
      }
    },
  };
  const auth = loadModule("auth");
  const render = () => {
    cursor = 0;
    return auth.AuthProvider({ children: null }).props.value;
  };
  render();
  for (const effect of pendingEffects) cleanups.push(effect());
  return { get value() { return render(); }, stop: () => cleanups.forEach((cleanup) => cleanup?.()) };
}

test("AuthProvider does not restore a login response that already expired in transit", () => withClock(async ({ tick }) => {
  const provider = mountProvider();
  try {
    await tick(0);
    globalThis.fetch = async () => new Response(JSON.stringify({ access_token: fixture(999), user: { id: "expired-login" } }));
    await provider.value.login("fixture@example.invalid", "fixture");
    await flush();
    assert.ok(!store.has(tokenKey));
    assert.equal(provider.value.user, null);
  } finally { provider.stop(); }
}));

test("AuthProvider ignores a pending login after explicit logout", () => withClock(async ({ tick }) => {
  const provider = mountProvider();
  try {
    await tick(0);
    let respond;
    globalThis.fetch = () => new Promise((resolve) => { respond = resolve; });
    const pending = provider.value.login("fixture@example.invalid", "fixture");
    provider.value.logout();
    respond(new Response(JSON.stringify({ access_token: fixture(1100), user: { id: "old-login" } })));
    await pending;
    await flush();
    assert.ok(!store.has(tokenKey));
    assert.equal(provider.value.user, null);
  } finally { provider.stop(); }
}));

test("password login remains usable and authenticated 401 clears provider state", () => withClock(async ({ tick }) => {
  const provider = mountProvider();
  const user = { id: "local-user", role: "employee", permissions: ["wiki:read:all"] };
  try {
    await tick(0);
    globalThis.fetch = async (url) => new Response(JSON.stringify(url.endsWith("/login") ? { access_token: fixture(1100), user } : user));
    await provider.value.login("fixture@example.invalid", "fixture");
    await flush();
    assert.equal(provider.value.user?.id, "local-user");
    assert.equal(provider.value.loading, false);
    assert.equal(provider.value.canAccess("wiki", "read"), true);
    globalThis.fetch = async () => new Response("{}", { status: 401 });
    await assert.rejects(api("/fixture"));
    assert.equal(provider.value.user, null);
    assert.equal(provider.value.canAccess("wiki", "read"), false);
  } finally { provider.stop(); }
}));

test("AuthProvider exposes an initial verifier error and clears it on manual retry", () => withClock(async ({ tick }) => {
  setToken(fixture(1100));
  globalThis.fetch = async () => new Response("{}", { status: 503 });
  const provider = mountProvider();
  try {
    await tick(0);
    assert.ok(provider.value.error);
    assert.equal(provider.value.user, null);
    assert.ok(store.has(tokenKey));
    globalThis.fetch = async () => new Response(JSON.stringify({ id: "recovered-user" }));
    await provider.value.refresh();
    assert.equal(provider.value.error, null);
    assert.equal(provider.value.loading, false);
    assert.equal(provider.value.user.id, "recovered-user");
  } finally { provider.stop(); }
}));

test("SSO logout clears storage and preserves its explicit navigation flow", () => withClock(async ({ tick }) => {
  setToken(fixture(1100));
  store.set("arkon_sso", "1");
  browser.location = { href: "https://wiki.invalid/" };
  globalThis.fetch = async () => new Response(JSON.stringify({ id: "sso-user" }));
  const provider = mountProvider();
  try {
    await tick(0);
    assert.equal(provider.value.logout(), true);
    assert.ok(browser.location.href.endsWith("/api/auth/sso/logout"));
    assert.ok(!store.has(tokenKey));
    assert.ok(!store.has("arkon_sso"));
    assert.equal(provider.value.user?.id, "sso-user", "The portal guard must allow the explicit SSO navigation to finish");
  } finally { provider.stop(); delete browser.location; }
}));

let failures = 0;
for (const { name, run } of tests) {
  try {
    store.clear();
    await run();
    console.log(`PASS ${name}`);
  } catch (error) {
    failures++;
    console.error(`FAIL ${name} (${error.code ?? error.name})`);
  }
}
clearToken();
if (failures) process.exitCode = 1;
else console.log(`Session lifecycle regression checks passed (${tests.length}).`);
