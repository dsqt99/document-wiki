"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { Sidebar } from "@/components/layout/sidebar";

export default function PortalLayout({ children }: { children: React.ReactNode }) {
  const { user, loading, error, refresh } = useAuth();
  const router = useRouter();

  // Unauthenticated: send to /login, remembering where we were.
  useEffect(() => {
    if (loading || error || user) return;
    const here = window.location.pathname + window.location.search;
    const target = here === "/" || here === "" ? "/login" : `/login?next=${encodeURIComponent(here)}`;
    router.push(target);
  }, [loading, error, user, router]);

  if (error && !user) {
    return (
      <div role="alert" className="flex h-screen flex-col items-center justify-center gap-3 bg-background px-6 text-center">
        <p className="text-sm text-muted-foreground">{error}</p>
        <button type="button" className="rounded-md border px-4 py-2 text-sm font-medium hover:bg-muted" onClick={() => void refresh()}>
          Thử lại
        </button>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-3 bg-background">
        <span className="material-symbols-outlined animate-spin text-primary" style={{ fontSize: 40 }}>
          progress_activity
        </span>
        <p className="text-xs text-muted-foreground">Loading...</p>
      </div>
    );
  }

  if (!user) return null;

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <Sidebar />
      <main className="min-w-0 flex-1 overflow-hidden">
        <div className="flex h-full w-full flex-col gap-8 overflow-y-auto *:shrink-0 px-6 pt-4 pb-6 md:px-8 md:pb-8 lg:px-10 lg:pb-10">{children}</div>
      </main>
    </div>
  );
}
