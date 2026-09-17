"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";
import { useTheme } from "@/lib/theme";
import { useI18n, TranslationKey } from "@/lib/i18n";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { NotificationBell } from "@/components/notifications/notification-bell";

/* ─── Types ─── */

type NavItemDef = {
  labelKey: TranslationKey;
  href: string;
  icon: string;
  requiredPermissions?: string[];
};

type NavSectionDef = {
  id: string;
  labelKey: TranslationKey;
  requiredPermissions?: string[];
  items: NavItemDef[];
};

/* ─── Navigation Config ─── */

const navSectionDefs: NavSectionDef[] = [
  {
    id: "org-knowledge",
    labelKey: "nav.orgKnowledge",
    items: [
      { labelKey: "nav.documents", href: "/knowledge", icon: "description", requiredPermissions: ["doc:read:own_dept", "doc:read:all"] },
      { labelKey: "nav.wiki", href: "/wiki", icon: "auto_stories", requiredPermissions: ["wiki:read:own_dept", "wiki:read:all"] },
      { labelKey: "nav.reviews", href: "/wiki/review", icon: "fact_check", requiredPermissions: ["wiki:read:own_dept", "wiki:read:all"] },
      { labelKey: "nav.skills", href: "/skills", icon: "bolt", requiredPermissions: ["skill:read:own_dept", "skill:read:all"] },
    ],
  },
  {
    id: "organization",
    labelKey: "nav.organization",
    requiredPermissions: ["org:departments:read", "org:employees:read"],
    items: [
      { labelKey: "nav.departments", href: "/departments", icon: "domain", requiredPermissions: ["org:departments:read"] },
      { labelKey: "nav.employees", href: "/employees", icon: "group", requiredPermissions: ["org:employees:read"] },
    ],
  },
  {
    id: "system",
    labelKey: "nav.system",
    requiredPermissions: ["org:audit:read", "org:settings:read", "org:settings:manage"],
    items: [
      { labelKey: "nav.audit", href: "/audit", icon: "policy", requiredPermissions: ["org:audit:read"] },
      { labelKey: "nav.settings", href: "/settings", icon: "settings", requiredPermissions: ["org:settings:read"] },
    ],
  },
];

/* ─── Helpers ─── */

const ALL_NAV_HREFS = navSectionDefs.flatMap((s) => s.items.map((i) => i.href));

function isActive(href: string, pathname: string) {
  if (href === "/") return pathname === "/";
  if (!(pathname === href || pathname.startsWith(href + "/"))) return false;
  return !ALL_NAV_HREFS.some(
    (other) =>
      other !== href &&
      other.startsWith(href + "/") &&
      (pathname === other || pathname.startsWith(other + "/")),
  );
}

/* ─── Sub-components ─── */

type SidebarNavItemProps = {
  label: string;
  href: string;
  icon: string;
  pathname: string;
  indented?: boolean;
  collapsed?: boolean;
};

function SidebarNavItem({
  label,
  href,
  icon,
  pathname,
  indented = false,
  collapsed = false,
}: SidebarNavItemProps) {
  const { user } = useAuth();
  const active = isActive(href, pathname) || (href === "/wiki" && pathname === "/" && user?.role !== "admin");

  if (collapsed) {
    return (
      <Tooltip>
        <TooltipTrigger
          render={
            <Link
              href={href}
              className={cn(
                "group flex items-center justify-center w-10 h-10 mx-auto rounded-lg transition-all duration-150",
                active
                  ? "bg-primary/10 text-primary font-semibold border border-primary/20 shadow-xs"
                  : "text-slate-500 hover:bg-slate-200/60 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800/60 dark:hover:text-slate-100"
              )}
              title={label}
            >
              <span
                className={cn(
                  "material-symbols-outlined text-[20px] shrink-0 transition-transform group-hover:scale-110",
                  active ? "filled text-primary" : "text-slate-500 group-hover:text-slate-900 dark:text-slate-400 dark:group-hover:text-slate-100"
                )}
                style={{ fontVariationSettings: active ? "'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 20" : "'FILL' 0, 'wght' 300, 'GRAD' 0, 'opsz' 20" }}
              >
                {icon}
              </span>
            </Link>
          }
        />
        <TooltipContent side="right" className="font-medium text-xs">
          {label}
        </TooltipContent>
      </Tooltip>
    );
  }

  return (
    <Link
      href={href}
      className={cn(
        "group relative flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-[13px] font-medium transition-all duration-150",
        indented && "ml-2",
        active
          ? "bg-primary/10 text-primary font-semibold shadow-2xs"
          : "text-slate-600 hover:bg-slate-200/60 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800/60 dark:hover:text-slate-100"
      )}
    >
      <span
        className={cn(
          "material-symbols-outlined text-[19px] shrink-0",
          active ? "filled text-primary" : "text-slate-400 group-hover:text-slate-700 dark:text-slate-500 dark:group-hover:text-slate-300"
        )}
        style={{ fontVariationSettings: active ? "'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 20" : "'FILL' 0, 'wght' 300, 'GRAD' 0, 'opsz' 20" }}
      >
        {icon}
      </span>
      <span className="truncate">{label}</span>
      {active && (
        <span className="ml-auto w-1.5 h-1.5 rounded-full bg-primary shrink-0" />
      )}
    </Link>
  );
}

type SidebarStaticSectionProps = {
  section: NavSectionDef;
  hasPermission: (perm: string) => boolean;
  pathname: string;
  collapsed?: boolean;
};

function SidebarStaticSection({
  section,
  hasPermission,
  pathname,
  collapsed = false,
}: SidebarStaticSectionProps) {
  const { t } = useI18n();

  const visibleItems = section.items.filter((i) => {
    if (!i.requiredPermissions) return true;
    return i.requiredPermissions.some((p) => hasPermission(p));
  });
  if (visibleItems.length === 0) return null;

  if (collapsed) {
    return (
      <div className="mt-2.5 first:mt-0">
        <div className="w-6 mx-auto border-t border-slate-200/80 dark:border-slate-800/80 my-2" />
        <div className="space-y-1">
          {visibleItems.map((item) => (
            <SidebarNavItem
              key={item.href}
              label={t(item.labelKey)}
              href={item.href}
              icon={item.icon}
              pathname={pathname}
              collapsed
            />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="mt-4 first:mt-0">
      <div className="px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-slate-400/90 dark:text-slate-500">
        {t(section.labelKey)}
      </div>
      <div className="mt-0.5 space-y-0.5">
        {visibleItems.map((item) => (
          <SidebarNavItem
            key={item.href}
            label={t(item.labelKey)}
            href={item.href}
            icon={item.icon}
            pathname={pathname}
            indented
          />
        ))}
      </div>
    </div>
  );
}

/* ─── User / Organization Dropdown Menu Content ─── */

function UserMenuDropdownContent({
  user,
  onLogout,
}: {
  user: { name: string; role: string } | null;
  onLogout: () => void;
}) {
  const router = useRouter();
  const { theme, setTheme } = useTheme();
  const { lang, setLang, t } = useI18n();

  const themeOptions = [
    { value: "light" as const, icon: "light_mode", label: t("theme.light") },
    { value: "dark" as const, icon: "dark_mode", label: t("theme.dark") },
    { value: "system" as const, icon: "desktop_windows", label: t("theme.system") },
  ];

  const langOptions = [
    { value: "vi" as const, flag: "🇻🇳", label: "VI" },
    { value: "en" as const, flag: "🇬🇧", label: "EN" },
  ];

  return (
    <DropdownMenuContent
      align="start"
      className="w-56 p-1.5 shadow-xl border-border bg-popover text-popover-foreground rounded-xl select-none"
    >
      {user && (
        <>
          <div className="px-2.5 py-1.5">
            <p className="text-xs font-semibold text-foreground leading-snug">{user.name}</p>
            <p className="text-[11px] text-muted-foreground capitalize">{user.role}</p>
          </div>
          <DropdownMenuSeparator className="my-1" />
        </>
      )}

      <DropdownMenuItem
        onClick={() => router.push("/profile")}
        className="cursor-pointer px-2 py-1.5 rounded-lg font-medium text-xs"
      >
        <span className="material-symbols-outlined mr-2 text-[17px] text-muted-foreground">person</span>
        {t("user.profile")}
      </DropdownMenuItem>

      <DropdownMenuSeparator className="my-1" />

      {/* Theme Row */}
      <div className="flex items-center justify-between px-2 py-1.5">
        <span className="text-xs font-medium text-muted-foreground">{t("theme.title")}</span>
        <div className="flex items-center gap-0.5 p-0.5 rounded-lg bg-secondary border border-border">
          {themeOptions.map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={(e) => { e.preventDefault(); e.stopPropagation(); setTheme(opt.value); }}
              className={cn(
                "flex items-center justify-center w-7 h-6 rounded-md text-xs transition-all cursor-pointer",
                theme === opt.value
                  ? "bg-popover text-primary shadow-xs ring-1 ring-primary/30"
                  : "text-muted-foreground hover:text-foreground"
              )}
              title={opt.label}
              aria-label={opt.label}
            >
              <span className="material-symbols-outlined text-[14px]">{opt.icon}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Language Row */}
      <div className="flex items-center justify-between px-2 py-1.5">
        <span className="text-xs font-medium text-muted-foreground">{t("language.title")}</span>
        <div className="flex items-center gap-0.5 p-0.5 rounded-lg bg-secondary border border-border">
          {langOptions.map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={(e) => { e.preventDefault(); e.stopPropagation(); setLang(opt.value); }}
              className={cn(
                "flex items-center gap-1 px-2 h-6 rounded-md text-[11px] font-semibold transition-all cursor-pointer",
                lang === opt.value
                  ? "bg-popover text-primary shadow-xs ring-1 ring-primary/30"
                  : "text-muted-foreground hover:text-foreground"
              )}
              title={opt.value === "vi" ? "Tiếng Việt" : "English"}
              aria-label={opt.value === "vi" ? "Tiếng Việt" : "English"}
            >
              <span className="text-[12px] leading-none">{opt.flag}</span>
              <span>{opt.label}</span>
            </button>
          ))}
        </div>
      </div>

      <DropdownMenuSeparator className="my-1" />

      <DropdownMenuItem
        onClick={onLogout}
        className="cursor-pointer text-destructive focus:text-destructive focus:bg-destructive/10 px-2 py-1.5 rounded-lg font-medium text-xs transition-colors"
      >
        <span className="material-symbols-outlined mr-2 text-[17px]">logout</span>
        {t("user.signOut")}
      </DropdownMenuItem>
    </DropdownMenuContent>
  );
}

/* ─── Org / User Header ─── */

function OrgHeader({
  user,
  collapsed,
  onToggleCollapse,
}: {
  user: { name: string; role: string } | null;
  collapsed: boolean;
  onToggleCollapse: () => void;
}) {
  const router = useRouter();
  const { logout } = useAuth();
  const { t } = useI18n();

  const handleLogout = () => {
    logout();
    router.push("/login");
  };

  if (collapsed) {
    return (
      <div className="px-1.5 py-1.5 flex flex-col items-center gap-2 border-b border-slate-200/70 dark:border-slate-800/70 pb-2">
        <DropdownMenu>
          <DropdownMenuTrigger className="flex items-center justify-center w-10 h-10 rounded-lg hover:bg-slate-200/60 dark:hover:bg-slate-800/60 transition-colors cursor-pointer outline-none">
            <img
              src="/logo.png?v=3"
              alt="Document Wiki"
              width={26}
              height={26}
              className="shrink-0 rounded-md shadow-xs object-cover"
            />
          </DropdownMenuTrigger>
          <UserMenuDropdownContent user={user} onLogout={handleLogout} />
        </DropdownMenu>

        {/* Expand button */}
        <button
          type="button"
          onClick={onToggleCollapse}
          className="flex items-center justify-center w-8 h-8 rounded-md text-slate-400 hover:text-slate-800 hover:bg-slate-200/60 dark:hover:bg-slate-800/60 transition-colors cursor-pointer"
          title={t("sidebar.expand")}
          aria-label={t("sidebar.expand")}
        >
          <span className="material-symbols-outlined text-[18px]">left_panel_open</span>
        </button>

        {/* Bell */}
        <div className="scale-90">
          <NotificationBell />
        </div>
      </div>
    );
  }

  return (
    <div className="px-2.5 py-1.5 mb-1 flex items-center justify-between gap-1 border-b border-slate-200/70 dark:border-slate-800/70 pb-2.5">
      <DropdownMenu>
        {/* Dropdown trigger without overlapping arrow icon */}
        <DropdownMenuTrigger className="flex items-center gap-2.5 rounded-lg px-2 py-1.5 hover:bg-slate-200/60 dark:hover:bg-slate-800/60 transition-colors cursor-pointer min-w-0 flex-1 text-left outline-none group">
          <img
            src="/logo.png?v=3"
            alt="Document Wiki"
            width={26}
            height={26}
            className="shrink-0 rounded-md shadow-xs object-cover group-hover:scale-105 transition-transform"
          />
          <div className="flex flex-col items-start min-w-0 flex-1">
            <span className="text-[14px] font-bold text-slate-900 dark:text-slate-100 truncate leading-tight font-heading">
              Document Wiki
            </span>
            {user && (
              <span className="text-[10px] text-slate-500 dark:text-slate-400 truncate leading-tight font-medium">
                {user.name} · {user.role}
              </span>
            )}
          </div>
        </DropdownMenuTrigger>
        <UserMenuDropdownContent user={user} onLogout={handleLogout} />
      </DropdownMenu>

      <div className="flex items-center gap-0.5 shrink-0">
        <NotificationBell />
        <button
          type="button"
          onClick={onToggleCollapse}
          className="p-1.5 rounded-md text-slate-400 hover:text-slate-700 hover:bg-slate-200/60 dark:hover:bg-slate-800/60 transition-colors cursor-pointer"
          title={t("sidebar.collapse")}
          aria-label={t("sidebar.collapse")}
        >
          <span className="material-symbols-outlined text-[18px]">left_panel_close</span>
        </button>
      </div>
    </div>
  );
}

/* ─── Main Sidebar ─── */

export function Sidebar() {
  const pathname = usePathname();
  const { user, hasPermission } = useAuth();
  const { t } = useI18n();

  const [collapsed, setCollapsed] = useState(false);

  // Read stored preference on mount
  useEffect(() => {
    const stored = localStorage.getItem("sidebar-collapsed");
    if (stored !== null) {
      setCollapsed(stored === "true");
    }
  }, []);

  const toggleCollapse = () => {
    setCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem("sidebar-collapsed", String(next));
      return next;
    });
  };

  // Shortcut Ctrl+B / Cmd+B to toggle sidebar
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "b") {
        e.preventDefault();
        toggleCollapse();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const visibleSections = navSectionDefs.filter((s) => {
    if (!s.requiredPermissions) return true;
    return s.requiredPermissions.some((p) => hasPermission(p));
  });

  return (
    <nav
      className={cn(
        "hidden md:flex flex-col h-full shrink-0 bg-slate-50 dark:bg-slate-950/80 border-r border-slate-200/80 dark:border-slate-800/80 transition-all duration-200 ease-in-out select-none z-20",
        collapsed ? "w-[60px]" : "w-[240px]"
      )}
    >
      {/* Org Header + User + Collapse Button */}
      <div className="pt-2">
        <OrgHeader
          user={user}
          collapsed={collapsed}
          onToggleCollapse={toggleCollapse}
        />
      </div>

      {/* Navigation */}
      <div
        className={cn(
          "flex-1 overflow-y-auto overflow-x-hidden py-1 sidebar-scrollbar",
          collapsed ? "px-1.5" : "px-2"
        )}
      >
        {/* Dashboard */}
        {user?.role === "admin" && (
          <SidebarNavItem
            label={t("nav.dashboard")}
            href="/"
            icon="dashboard"
            pathname={pathname}
            collapsed={collapsed}
          />
        )}

        {/* Static sections */}
        {visibleSections.map((section) => (
          <SidebarStaticSection
            key={section.id}
            section={section}
            hasPermission={hasPermission}
            pathname={pathname}
            collapsed={collapsed}
          />
        ))}
      </div>

      {/* Bottom meta */}
      <div
        className={cn(
          "py-2 border-t border-slate-200/70 dark:border-slate-800/70 transition-all",
          collapsed ? "px-1 text-center" : "px-3"
        )}
      >
        {collapsed ? (
          <span
            className="material-symbols-outlined text-[14px] text-slate-400/60 block"
            title={t("brand.internal")}
          >
            dns
          </span>
        ) : (
          <span className="text-[10px] text-slate-400 dark:text-slate-500 font-medium">
            {t("brand.internal")}
          </span>
        )}
      </div>
    </nav>
  );
}
