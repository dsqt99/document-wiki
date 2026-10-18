"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { NotificationBell } from "@/components/layout/notification-bell";
import { UserMenu } from "@/components/layout/user-menu";

const COLLAPSE_KEY = "sidebar-collapsed";

type NavItem = {
  href: string;
  labelKey: string;
  icon: string;
  /** Visible when the user holds at least one of these (empty = always). */
  perms: string[];
  adminOnly?: boolean;
};

type NavGroup = {
  labelKey?: string;
  /** Group shown only when the user holds one of these (empty = no condition). */
  perms: string[];
  items: NavItem[];
};

const NAV: NavGroup[] = [
  { perms: [], items: [{ href: "/", labelKey: "nav.dashboard", icon: "dashboard", perms: [], adminOnly: true }] },
  {
    labelKey: "nav.orgKnowledge",
    perms: [],
    items: [
      { href: "/knowledge", labelKey: "nav.documents", icon: "description", perms: ["doc:read:own_dept", "doc:read:all"] },
      {
        href: "/wiki/law",
        labelKey: "nav.wiki",
        icon: "auto_stories",
        perms: ["wiki:read:own_dept", "wiki:read:all", "doc:read:own_dept", "doc:read:all"],
      },
      { href: "/skills", labelKey: "nav.skills", icon: "bolt", perms: ["skill:read:own_dept", "skill:read:all"] },
      { href: "/prompts", labelKey: "nav.prompts", icon: "chat_paste_go", perms: [] },
    ],
  },
  {
    labelKey: "nav.organization",
    perms: ["org:departments:read", "org:employees:read"],
    items: [
      { href: "/departments", labelKey: "nav.departments", icon: "domain", perms: ["org:departments:read"] },
      { href: "/employees", labelKey: "nav.employees", icon: "group", perms: ["org:employees:read"] },
    ],
  },
  {
    labelKey: "nav.system",
    perms: ["org:audit:read", "org:settings:read", "org:settings:manage"],
    items: [
      { href: "/audit", labelKey: "nav.audit", icon: "policy", perms: ["org:audit:read"] },
      { href: "/settings", labelKey: "nav.settings", icon: "settings", perms: ["org:settings:read"] },
    ],
  },
];

const ALL_HREFS = NAV.flatMap((g) => g.items.map((i) => i.href));

function matches(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(href + "/");
}

function isActive(pathname: string, href: string, isAdmin: boolean): boolean {
  if (href === "/wiki/law") {
    if (pathname === "/" && !isAdmin) return true;
    if (pathname === "/wiki") return true;
    if (pathname.startsWith("/wiki/") && !pathname.startsWith("/wiki/review")) return true;
  }
  if (!matches(pathname, href)) return false;
  // A longer, more specific item that also matches wins.
  return !ALL_HREFS.some((other) => other !== href && other.length > href.length && matches(pathname, other));
}

export function Sidebar() {
  const { user, hasPermission } = useAuth();
  const { t } = useI18n();
  const pathname = usePathname() || "/";
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    let saved = false;
    try {
      saved = localStorage.getItem(COLLAPSE_KEY) === "true";
    } catch {
      saved = false;
    }
    const id = setTimeout(() => setCollapsed(saved), 0);
    return () => clearTimeout(id);
  }, []);

  const toggle = () =>
    setCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(COLLAPSE_KEY, String(next));
      } catch {
        /* ignore */
      }
      return next;
    });

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && (e.key === "b" || e.key === "B")) {
        e.preventDefault();
        setCollapsed((prev) => {
          const next = !prev;
          try {
            localStorage.setItem(COLLAPSE_KEY, String(next));
          } catch {
            /* ignore */
          }
          return next;
        });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (!user) return null;
  const isAdmin = user.role === "admin";
  const can = (perms: string[]) => perms.length === 0 || perms.some((p) => hasPermission(p));

  const groups = NAV.map((g) => ({
    ...g,
    items: g.items.filter((i) => (i.adminOnly ? isAdmin : can(i.perms))),
  })).filter((g) => can(g.perms) && g.items.length > 0);

  return (
    <aside
      className={cn(
        "hidden h-screen shrink-0 flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground transition-[width] duration-200 select-none md:flex",
        collapsed ? "w-[60px]" : "w-60",
      )}
    >
      {/* Brand / user block */}
      {collapsed ? (
        <div className="mt-2 border-b border-sidebar-border px-2.5 pt-1.5 pb-2.5">
          <div className="flex flex-col items-center gap-1.5">
            <UserMenu triggerClassName="rounded-lg p-1 outline-none hover:bg-sidebar-accent">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src="/logo.png?v=3" alt="Document Wiki" className="size-[26px] rounded-md" />
            </UserMenu>
            <Tooltip>
              <TooltipTrigger
                render={
                  <button
                    type="button"
                    aria-label={t("sidebar.expand")}
                    onClick={toggle}
                    className="flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-sidebar-accent hover:text-foreground"
                  />
                }
              >
                <span className="material-symbols-outlined" style={{ fontSize: 20 }}>
                  left_panel_open
                </span>
              </TooltipTrigger>
              <TooltipContent side="right">{t("sidebar.expand")}</TooltipContent>
            </Tooltip>
            <NotificationBell className="scale-90" />
          </div>
        </div>
      ) : (
        <div className="mt-2 flex items-center gap-1 border-b border-sidebar-border px-2.5 pt-1.5 pb-2.5">
          <UserMenu triggerClassName="flex h-[42px] min-w-0 flex-1 items-center gap-2.5 rounded-[10px] pl-2 text-left outline-none hover:bg-sidebar-accent">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/logo.png?v=3" alt="Document Wiki" className="size-[26px] shrink-0 rounded-md" />
            <span className="min-w-0">
              <span className="block text-sm font-bold whitespace-nowrap text-foreground">Document Wiki</span>
              <span className="block truncate text-[11px] text-muted-foreground">
                {user.name} · {user.role}
              </span>
            </span>
          </UserMenu>
          <NotificationBell className="mr-0.5" />
          <Tooltip>
            <TooltipTrigger
              render={
                <button
                  type="button"
                  aria-label={t("sidebar.collapse")}
                  onClick={toggle}
                  className="flex size-8 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-sidebar-accent hover:text-foreground"
                />
              }
            >
              <span className="material-symbols-outlined" style={{ fontSize: 20 }}>
                left_panel_close
              </span>
            </TooltipTrigger>
            <TooltipContent side="bottom">{t("sidebar.collapse")}</TooltipContent>
          </Tooltip>
        </div>
      )}

      {/* Navigation */}
      <nav className="scrollbar-hover flex-1 overflow-y-auto px-2 pt-2 pb-3">
        <div className={cn("flex flex-col", collapsed ? "items-center gap-2" : "gap-4")}>
          {groups.map((group, gi) => (
            <div key={group.labelKey ?? `g${gi}`} className={cn("flex flex-col", collapsed ? "items-center gap-1" : "gap-0.5")}>
              {group.labelKey &&
                (collapsed ? (
                  <div className="my-1 h-px w-6 bg-sidebar-border" />
                ) : (
                  <p className="px-2.5 py-1 text-[10px] font-bold tracking-wider text-slate-400/90 uppercase">
                    {t(group.labelKey)}
                  </p>
                ))}
              {group.items.map((item) => {
                const active = isActive(pathname, item.href, isAdmin);
                const label = t(item.labelKey);
                if (collapsed) {
                  return (
                    <Tooltip key={item.href}>
                      <TooltipTrigger
                        render={
                          <Link
                            href={item.href}
                            aria-label={label}
                            className={cn(
                              "group flex size-10 items-center justify-center rounded-lg border border-transparent transition-colors",
                              active
                                ? "border-primary/20 bg-primary/10 text-primary"
                                : "text-slate-500 hover:bg-sidebar-accent hover:text-foreground dark:text-slate-400",
                            )}
                          />
                        }
                      >
                        <span
                          className={cn("material-symbols-outlined transition-transform group-hover:scale-110", active && "filled")}
                          style={{ fontSize: 20 }}
                        >
                          {item.icon}
                        </span>
                      </TooltipTrigger>
                      <TooltipContent side="right">{label}</TooltipContent>
                    </Tooltip>
                  );
                }
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={cn(
                      "flex h-9 items-center gap-2.5 rounded-[10px] px-2.5 py-1.5 text-[13px] font-medium transition-colors",
                      group.labelKey && "ml-2",
                      active
                        ? "bg-primary/10 font-semibold text-primary shadow-xs"
                        : "text-slate-600 hover:bg-sidebar-accent hover:text-foreground dark:text-slate-400",
                    )}
                  >
                    <span
                      className={cn("material-symbols-outlined", active && "filled")}
                      style={{ fontSize: 24, fontVariationSettings: `"FILL" ${active ? 1 : 0}, "wght" 300` }}
                    >
                      {item.icon}
                    </span>
                    <span className="flex-1 truncate">{label}</span>
                    {active && <span className="size-1.5 rounded-full bg-primary" />}
                  </Link>
                );
              })}
            </div>
          ))}
        </div>
      </nav>

      {/* Footer */}
      <div className="border-t border-sidebar-border px-3 py-2.5">
        {collapsed ? (
          <Tooltip>
            <TooltipTrigger render={<div className="flex justify-center text-muted-foreground/50" />}>
              <span className="material-symbols-outlined" style={{ fontSize: 14 }}>
                dns
              </span>
            </TooltipTrigger>
            <TooltipContent side="right">{t("brand.internal")}</TooltipContent>
          </Tooltip>
        ) : (
          <p className="truncate text-[10px] text-muted-foreground">{t("brand.internal")}</p>
        )}
      </div>
    </aside>
  );
}
