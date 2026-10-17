"use client";

import { useCallback, useEffect, useState } from "react";
import { DepartmentCards, type DepartmentInfo } from "@/components/departments/department-cards";
import { DepartmentDialog } from "@/components/departments/department-dialog";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

function fetchDepartments(): Promise<DepartmentInfo[]> {
  return api<DepartmentInfo[]>("/api/departments")
    .then((res) => (Array.isArray(res) ? res : []))
    .catch(() => []);
}

export default function DepartmentsPage() {
  const [departments, setDepartments] = useState<DepartmentInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<DepartmentInfo | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchDepartments().then((list) => {
      if (cancelled) return;
      setDepartments(list);
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const reload = useCallback(() => {
    void fetchDepartments().then(setDepartments);
  }, []);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Departments"
        description="Organize employees into departments and manage knowledge access."
        action={
          <Button
            onClick={() => {
              setEditing(null);
              setDialogOpen(true);
            }}
          >
            <span className="material-symbols-outlined" style={{ fontSize: 18 }}>
              add
            </span>
            Add Department
          </Button>
        }
      />
      <DepartmentCards
        departments={departments}
        loading={loading}
        onEdit={(d) => {
          setEditing(d);
          setDialogOpen(true);
        }}
        onRefresh={reload}
      />
      <DepartmentDialog open={dialogOpen} onOpenChange={setDialogOpen} department={editing} onSaved={reload} />
    </div>
  );
}
