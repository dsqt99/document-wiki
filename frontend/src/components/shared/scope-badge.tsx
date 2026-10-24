"use client";

import { Badge } from "@/components/ui/badge";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

export type ScopeType = "global" | "project" | "department" | "team" | "personal";

const KNOWN: Record<ScopeType, { icon: string; labelKey: string; tone: string }> = {
  personal: {
    icon: "person",
    labelKey: "scope.personal",
    tone: "border-slate-500/30 bg-slate-50 text-slate-700 dark:bg-slate-500/10 dark:text-slate-300",
  },
  global: {
    icon: "public",
    labelKey: "scope.global",
    tone: "border-blue-500/30 bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300",
  },
  department: {
    icon: "corporate_fare",
    labelKey: "scope.department",
    tone: "border-indigo-500/30 bg-indigo-50 text-indigo-700 dark:bg-indigo-500/10 dark:text-indigo-300",
  },
  project: {
    icon: "folder_special",
    labelKey: "scope.project",
    tone: "border-amber-500/30 bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300",
  },
  team: {
    icon: "group",
    labelKey: "scope.team",
    tone: "border-emerald-500/30 bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300",
  },
};

type ScopeBadgeProps = {
  scopeType?: ScopeType | string;
  /** Accepted for call-site symmetry; not displayed. */
  scopeId?: string | null;
  className?: string;
};

export function ScopeBadge({ scopeType, className }: ScopeBadgeProps) {
  const { t } = useI18n();

  if (!scopeType) {
    return (
      <Badge variant="outline" className={cn("gap-1 text-xs whitespace-nowrap text-muted-foreground", className)}>
        <span className="material-symbols-outlined" style={{ fontSize: 13 }}>
          public
        </span>
        {t("scope.global")}
      </Badge>
    );
  }

  const known = KNOWN[scopeType as ScopeType];
  if (!known) {
    return (
      <Badge
        variant="outline"
        className={cn("rounded-full text-[11px] font-medium whitespace-nowrap text-muted-foreground", className)}
      >
        {scopeType}
      </Badge>
    );
  }

  return (
    <Badge
      variant="outline"
      className={cn("gap-1 rounded-full text-[11px] font-medium whitespace-nowrap", known.tone, className)}
    >
      <span className="material-symbols-outlined" style={{ fontSize: 14 }}>
        {known.icon}
      </span>
      {t(known.labelKey)}
    </Badge>
  );
}
