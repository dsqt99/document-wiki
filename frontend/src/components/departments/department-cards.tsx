"use client";

import { useState } from "react";
import { EmptyState } from "@/components/shared/empty-state";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { DeptMembersDialog } from "./dept-members-dialog";

export type DepartmentInfo = {
  id: string;
  name: string;
  description?: string | null;
  employee_count: number;
};

type Props = {
  departments: DepartmentInfo[];
  loading: boolean;
  onEdit: (dept: DepartmentInfo) => void;
  onRefresh: () => void;
};

function Icon({ name, size = 15 }: { name: string; size?: number }) {
  return (
    <span className="material-symbols-outlined" style={{ fontSize: size }}>
      {name}
    </span>
  );
}

export function DepartmentCards({ departments, loading, onEdit, onRefresh }: Props) {
  const { t } = useI18n();
  const [membersOf, setMembersOf] = useState<DepartmentInfo | null>(null);

  const remove = async (dept: DepartmentInfo) => {
    if (!confirm(t("dept.deleteConfirm"))) return;
    // Errors are left to surface naturally (spec: no dedicated handling here).
    await api(`/api/departments/${dept.id}`, { method: "DELETE" });
    onRefresh();
  };

  if (loading) {
    return (
      <div className="flex justify-center py-16 text-muted-foreground">
        <span className="material-symbols-outlined animate-spin" style={{ fontSize: 30 }}>
          progress_activity
        </span>
      </div>
    );
  }

  if (departments.length === 0) {
    return <EmptyState icon="business" title={t("dept.noDepts")} description={t("dept.noDeptsDesc")} />;
  }

  return (
    <>
      <div className="grid grid-cols-1 gap-5 md:grid-cols-2 lg:grid-cols-3">
        {departments.map((d) => (
          <div
            key={d.id}
            className="flex flex-col rounded-xl border bg-card p-6 shadow-sm transition-colors hover:border-primary/30"
          >
            <div className="flex items-center gap-3">
              <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <Icon name="business" size={20} />
              </span>
              <div className="min-w-0">
                <p className="truncate text-base font-semibold">{d.name}</p>
                <p className="text-xs text-muted-foreground">
                  {d.employee_count} {t("dept.employees")}
                </p>
              </div>
            </div>
            {d.description && <p className="mt-3 line-clamp-2 text-sm text-muted-foreground">{d.description}</p>}
            <div className="mt-auto pt-4">
              <div className="flex flex-wrap items-center gap-1 border-t pt-3">
              <Button variant="ghost" size="sm" className="text-xs" onClick={() => setMembersOf(d)}>
                <Icon name="group" />
                {t("dept.members")}
              </Button>
              <Button variant="ghost" size="sm" className="text-xs" onClick={() => onEdit(d)}>
                <Icon name="edit" />
                {t("common.edit")}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="text-xs text-destructive hover:text-destructive"
                onClick={() => void remove(d)}
              >
                <Icon name="delete" />
                {t("common.delete")}
              </Button>
              </div>
            </div>
          </div>
        ))}
      </div>
      <DeptMembersDialog
        open={!!membersOf}
        onOpenChange={(o) => {
          if (!o) setMembersOf(null);
        }}
        deptId={membersOf?.id ?? ""}
        deptName={membersOf?.name ?? ""}
      />
    </>
  );
}
