/** Browser session state. JWT decoding here schedules UI cleanup, never authorization. */
export const TOKEN_KEY = "arkon_token";
const SESSION_EVENT = "arkon:session-change";

export function readToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(TOKEN_KEY, token);
  } catch {
    /* storage unavailable */
  }
  window.dispatchEvent(new Event(SESSION_EVENT));
}

/** A response for an old token must never remove a newer login. */
export function clearToken(expectedToken?: string): void {
  if (typeof window === "undefined") return;
  if (expectedToken !== undefined && readToken() !== expectedToken) return;
  try {
    window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable */
  }
  window.dispatchEvent(new Event(SESSION_EVENT));
}

function subscribeSessionChanges(onChange: () => void): () => void {
  const onStorage = (event: StorageEvent) => {
    if (event.key === TOKEN_KEY || event.key === null) onChange();
  };
  window.addEventListener(SESSION_EVENT, onChange);
  window.addEventListener("storage", onStorage);
  return () => {
    window.removeEventListener(SESSION_EVENT, onChange);
    window.removeEventListener("storage", onStorage);
  };
}

function tokenExpiresAt(token: string): number | null {
  try {
    const payload = token.split(".")[1];
    const claims = JSON.parse(atob(payload.replace(/-/g, "+").replace(/_/g, "/")));
    const deadline = typeof claims.exp === "number" ? claims.exp * 1000 : NaN;
    return Number.isFinite(deadline) ? deadline : null;
  } catch {
    // The backend rejects invalid tokens; decoding is only an extra UI timer.
    return null;
  }
}

export interface SessionMonitor {
  refresh(): Promise<void>;
  stop(): void;
}

/** Keep idle tabs coherent; every protected backend request still authorizes independently. */
export function startSessionMonitor<T>(options: {
  fetchUser(): Promise<T>;
  onUser(user: T | null): void;
  onLoading(loading: boolean): void;
  onError?(error: unknown | null): void;
}): SessionMonitor {
  let stopped = false;
  let currentToken: string | null | undefined;
  let generation = 0;
  let verified = false;
  let expiryTimer: ReturnType<typeof setTimeout> | undefined;
  let inFlight: { token: string; generation: number; promise: Promise<void> } | null = null;

  const synchronizeToken = (): string | null => {
    const token = readToken();
    if (token !== currentToken) {
      currentToken = token;
      generation++;
      verified = false;
      options.onUser(null);
      options.onError?.(null);
      options.onLoading(Boolean(token));
    }
    clearTimeout(expiryTimer);
    if (!token) {
      options.onLoading(false);
      return null;
    }
    const expiresAt = tokenExpiresAt(token);
    if (expiresAt !== null) {
      const remaining = expiresAt - Date.now();
      if (remaining <= 0) {
        clearToken(token);
        return null;
      }
      // Browsers overflow longer delays, so recheck long-lived sessions in chunks.
      expiryTimer = setTimeout(() => void refresh(), Math.min(remaining, 2_147_483_647));
    }
    return token;
  };

  function refresh(): Promise<void> {
    if (stopped) return Promise.resolve();
    const token = synchronizeToken();
    if (!token) return Promise.resolve();
    if (inFlight?.token === token && inFlight.generation === generation) return inFlight.promise;
    options.onError?.(null);
    const requestGeneration = generation;
    const isCurrent = () => !stopped && generation === requestGeneration && readToken() === token;
    const promise = Promise.resolve().then(async () => {
      if (!isCurrent()) return;
      try {
        const user = await options.fetchUser();
        if (!isCurrent()) return;
        // A sleeping tab may receive the response after the JWT's deadline.
        const expiresAt = tokenExpiresAt(token);
        if (expiresAt !== null && expiresAt <= Date.now()) {
          clearToken(token);
          return;
        }
        verified = true;
        options.onError?.(null);
        options.onUser(user);
        options.onLoading(false);
      } catch (error) {
        if (!isCurrent()) return;
        if (error && typeof error === "object" && "status" in error && error.status === 401) {
          clearToken(token);
        } else {
          // Do not redirect a previously verified user on 403, 503 or network failures.
          // Initial failures need a retry screen, while preserving the unverified session.
          options.onError?.(verified ? null : error);
          options.onLoading(!verified);
        }
      }
    }).finally(() => {
      if (inFlight?.promise === promise) inFlight = null;
    });
    inFlight = { token, generation: requestGeneration, promise };
    return promise;
  }

  const onChange = () => void refresh();
  const onVisibility = () => {
    if (document.visibilityState === "visible") void refresh();
  };
  const unsubscribe = subscribeSessionChanges(onChange);
  window.addEventListener("focus", onChange);
  document.addEventListener("visibilitychange", onVisibility);
  const initialTimer = setTimeout(onChange, 0);
  const interval = setInterval(onChange, 30_000);

  return {
    refresh,
    stop() {
      stopped = true;
      generation++;
      clearTimeout(initialTimer);
      clearTimeout(expiryTimer);
      clearInterval(interval);
      unsubscribe();
      window.removeEventListener("focus", onChange);
      document.removeEventListener("visibilitychange", onVisibility);
    },
  };
}
