"use client";

import { useEffect, useRef } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { currentPathForHost, postToHost, useIsEmbedded } from "@/lib/embed";
import { Sidebar } from "@/components/layout/sidebar";

export default function PortalLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const embedded = useIsEmbedded();
  const announced = useRef(false);

  // Unauthenticated: send to /login, remembering where we were.
  useEffect(() => {
    if (loading || user) return;
    const here = window.location.pathname + window.location.search;
    const target = here === "/" || here === "" ? "/login" : `/login?next=${encodeURIComponent(here)}`;
    if (embedded) router.replace(target);
    else router.push(target);
  }, [loading, user, embedded, router]);

  // Embedded: tell the host page we are ready, then report every navigation.
  useEffect(() => {
    if (!embedded || loading || !user) return;
    const path = currentPathForHost();
    if (!announced.current) {
      announced.current = true;
      postToHost({ type: "ready", path });
    } else {
      postToHost({ type: "navigate", path });
    }
  }, [embedded, loading, user, pathname]);

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

  if (embedded) {
    return (
      <main className="h-screen overflow-y-auto bg-background">
        <div className="flex flex-col gap-5 p-4 md:p-5">{children}</div>
      </main>
    );
  }

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <Sidebar />
      <main className="min-w-0 flex-1 overflow-y-auto">
        <div className="flex w-full flex-col gap-8 px-6 pt-4 pb-6 md:px-8 md:pb-8 lg:px-10 lg:pb-10">{children}</div>
      </main>
    </div>
  );
}
