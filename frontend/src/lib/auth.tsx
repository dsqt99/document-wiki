"use client";

import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { api, apiUrl, clearToken, setToken } from "@/lib/api";
import { readToken, SessionMonitor, startSessionMonitor } from "@/lib/session";

/** SSO marker is separate from the token managed by lib/session. */
const STORAGE_PREFIX = "arkon";
const storageKeys = { ssoFlag: `${STORAGE_PREFIX}_sso` } as const;

/** Membership of the signed-in user in one workspace. */
export interface WorkspaceMembership {
  role: string;
  workspace_id: string;
  workspace_name: string;
}

/** Profile returned by /api/auth/me and /api/auth/login. */
export interface User {
  id: string;
  email: string;
  name: string;
  role: "admin" | "employee";
  permissions: string[];
  department_names: string[];
  department_ids: string[];
  scope_department_ids?: string[];
  clearance_level?: string;
  workspace_memberships: WorkspaceMembership[];
}

interface AuthState {
  loading: boolean;
  error: string | null;
  user: User | null;
  refresh(): Promise<void>;
  login(email: string, password: string): Promise<void>;
  /** Returns true when it navigated away by itself (SSO logout). */
  logout(): boolean;
  getWorkspaceRole(workspaceId: string): string | null;
  canAccess(resource: string, action: string): boolean;
  hasPermission(perm: string): boolean;
}

/** Run a storage operation, swallowing errors (private mode, disabled storage). */
function withStorage<T>(op: (store: Storage) => T, fallback: T): T {
  try {
    return op(window.localStorage);
  } catch {
    return fallback;
  }
}

/** Flag the current session as coming from Keycloak SSO. */
export function markSsoSession(): void {
  withStorage((store) => store.setItem(storageKeys.ssoFlag, "1"), undefined);
}

const clearSsoFlag = (): void => withStorage((store) => store.removeItem(storageKeys.ssoFlag), undefined);

const isSsoSession = (): boolean => withStorage((store) => store.getItem(storageKeys.ssoFlag) === "1", false);

/** Permission scopes that satisfy a resource/action check. */
const ACCESS_SCOPES = ["all", "own_dept"] as const;

const isAdmin = (u: User): boolean => u.role === "admin";

const grants = (u: User): Set<string> => new Set(u.permissions ?? []);

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const monitor = useRef<SessionMonitor | null>(null);
  const departingForSsoLogout = useRef(false);
  const loginAttempt = useRef(0);

  const loadMe = useCallback(() => monitor.current?.refresh() ?? Promise.resolve(), []);

  useEffect(() => {
    const active = startSessionMonitor<User>({
      fetchUser: () => api<User>("/api/auth/me", { timeoutMs: 12_000 }),
      onUser: (nextUser) => {
        // Let the explicit SSO navigation finish before the portal's login guard runs.
        if (!departingForSsoLogout.current) setUser(nextUser);
      },
      onLoading: setLoading,
      onError: (failure) => setError(failure ? "Không thể kiểm tra phiên đăng nhập. Kiểm tra kết nối và thử lại." : null),
    });
    monitor.current = active;
    return () => {
      active.stop();
      if (monitor.current === active) monitor.current = null;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const attempt = ++loginAttempt.current;
    const previousToken = readToken();
    const res = await api<{ access_token: string; user: User }>("/api/auth/login", {
      method: "POST",
      body: { email, password },
    });
    if (!monitor.current || attempt !== loginAttempt.current || readToken() !== previousToken) return;
    departingForSsoLogout.current = false;
    clearSsoFlag();
    setToken(res.access_token);
    if (readToken() === res.access_token) setUser(res.user);
  }, []);

  const logout = useCallback(() => {
    loginAttempt.current++;
    const sso = isSsoSession();
    departingForSsoLogout.current = sso;
    clearToken();
    clearSsoFlag();
    if (sso) {
      // Keep `user` in memory so the portal guard does not race us to /login.
      window.location.href = apiUrl("/api/auth/sso/logout");
      return true;
    }
    setUser(null);
    return false;
  }, []);

  // Admins short-circuit every check; anonymous users fail every check.
  const hasPermission = useCallback(
    (perm: string): boolean => (user ? isAdmin(user) || grants(user).has(perm) : false),
    [user],
  );

  const canAccess = useCallback(
    (resource: string, action: string): boolean => {
      if (!user) return false;
      if (isAdmin(user)) return true;
      const granted = grants(user);
      return ACCESS_SCOPES.some((scope) => granted.has([resource, action, scope].join(":")));
    },
    [user],
  );

  const getWorkspaceRole = useCallback(
    (workspaceId: string): string | null => {
      if (user === null) return null;
      if (isAdmin(user)) return "admin";
      const membership = (user.workspace_memberships ?? []).find((entry) => entry.workspace_id === workspaceId);
      return membership ? membership.role : null;
    },
    [user],
  );

  const value = useMemo<AuthState>(
    () => ({ loading, error, user, refresh: loadMe, login, logout, getWorkspaceRole, canAccess, hasPermission }),
    [loading, error, user, loadMe, login, logout, getWorkspaceRole, canAccess, hasPermission],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

/** Access the auth state; only valid below <AuthProvider>. */
export function useAuth(): AuthState {
  const state = useContext(AuthContext);
  if (state === null) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return state;
}
