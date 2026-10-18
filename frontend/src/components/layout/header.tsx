"use client";

import { NotificationBell } from "@/components/layout/notification-bell";
import { UserMenu } from "@/components/layout/user-menu";
import { useAuth } from "@/lib/auth";

/**
 * Legacy top bar (title + notifications + account menu). The portal layout does not
 * mount it — every user function lives in the sidebar — but it is kept for pages
 * that may want a compact header outside the sidebar layout.
 */
export function Header({ title }: { title?: string }) {
  const { user } = useAuth();
  if (!user) return null;
  return (
    <header className="flex h-14 items-center gap-3 border-b bg-background px-4">
      <h1 className="flex-1 truncate text-sm font-semibold">{title ?? "Document Wiki"}</h1>
      <NotificationBell />
      <UserMenu triggerClassName="flex items-center gap-2 rounded-lg px-2 py-1 text-sm hover:bg-muted">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/logo.png?v=3" alt="" className="size-6 rounded-md" />
        <span className="max-w-40 truncate">{user.name}</span>
      </UserMenu>
    </header>
  );
}
