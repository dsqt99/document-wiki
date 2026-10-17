"use client";

import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, ApiError, apiUrl, clearToken, setToken } from "@/lib/api";

/** localStorage keys; the token key must match the one used by lib/api. */
const STORAGE_PREFIX = "arkon";
const storageKeys = { ssoFlag: `${STORAGE_PREFIX}_sso`, token: `${STORAGE_PREFIX}_token` } as const;

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
  workspace_memberships: WorkspaceMembership[];
}

interface AuthState {
  loading: boolean;
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

const hasStoredToken = (): boolean => withStorage((store) => Boolean(store.getItem(storageKeys.token)), false);

/** Permission scopes that satisfy a resource/action check. */
const ACCESS_SCOPES = ["all", "own_dept"] as const;

const isAdmin = (u: User): boolean => u.role === "admin";

const grants = (u: User): Set<string> => new Set(u.permissions ?? []);

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const loadMe = useCallback(async () => {
    if (!hasStoredToken()) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const me = await api<User>("/api/auth/me");
      setUser(me);
    } catch (err) {
      if (err instanceof ApiError && (err.status === 401 || err.status === 403)) clearToken();
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // Deferred so the first (loading) render commits before storage is consulted.
    const id = setTimeout(() => void loadMe(), 0);
    return () => clearTimeout(id);
  }, [loadMe]);

  const login = useCallback(async (email: string, password: string) => {
    const res = await api<{ access_token: string; user: User }>("/api/auth/login", {
      method: "POST",
      body: { email, password },
    });
    setToken(res.access_token);
    clearSsoFlag();
    setUser(res.user);
  }, []);

  const logout = useCallback(() => {
    const sso = isSsoSession();
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
    () => ({ loading, user, refresh: loadMe, login, logout, getWorkspaceRole, canAccess, hasPermission }),
    [loading, user, loadMe, login, logout, getWorkspaceRole, canAccess, hasPermission],
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
