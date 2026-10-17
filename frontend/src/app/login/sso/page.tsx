"use client";

import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { setToken } from "@/lib/api";
import { markSsoSession, useAuth } from "@/lib/auth";
import { clearLoginRound } from "@/lib/login-round";

/**
 * SSO landing page. The backend puts the local JWT in the URL fragment
 * (`#token=...&next=...`), which never reaches any server.
 */
export default function SsoCallbackPage() {
  const router = useRouter();
  const { refresh } = useAuth();
  const handled = useRef(false);

  useEffect(() => {
    if (handled.current) return;
    handled.current = true;

    const fragment = new URLSearchParams(window.location.hash.replace(/^#/, ""));
    const token = fragment.get("token");
    const next = fragment.get("next") || "/";

    // Drop the fragment (it holds the token) from the address bar and history entry.
    window.history.replaceState(null, "", window.location.pathname);

    if (!token) {
      router.replace("/login?error=sso_token");
      return;
    }

    setToken(token);
    markSsoSession();
    clearLoginRound();
    void refresh().then(() => {
      router.replace(next.startsWith("/") && !next.startsWith("//") ? next : "/");
    });
  }, [refresh, router]);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-background">
      <span className="material-symbols-outlined animate-spin text-primary" style={{ fontSize: 36 }}>
        progress_activity
      </span>
      <p className="text-sm text-muted-foreground">Đang đăng nhập SSO…</p>
    </div>
  );
}
