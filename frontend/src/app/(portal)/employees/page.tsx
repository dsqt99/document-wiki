"use client";

import { useEffect, useState } from "react";
import { EmployeeDialog, type DepartmentOption, type RoleOption } from "@/components/employees/employee-dialog";
import { EmployeeTable, type Employee } from "@/components/employees/employee-table";
import { RolesPermissionsCard } from "@/components/settings/roles-permissions-card";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

type EmployeePage = {
  items?: Employee[];
  total?: number;
  page?: number;
  page_size?: number;
  total_pages?: number;
};

type Tab = "employees" | "rbac";

const PAGE_SIZE = 20;

const ROLES: RoleOption[] = [
  { id: "viewer", name: "Viewer" },
  { id: "contributor", name: "Contributor" },
  { id: "knowledge_manager", name: "Knowledge Manager" },
  { id: "admin", name: "System Admin" },
];

const EMPTY_RESULT = { items: [] as Employee[], total: 0, page: 1, totalPages: 0 };

export default function EmployeesPage() {
  const [tab, setTab] = useState<Tab>("employees");
  const [requestedPage, setRequestedPage] = useState(1);
  const [search, setSearch] = useState("");
  const [reloadTick, setReloadTick] = useState(0);
  const [result, setResult] = useState(EMPTY_RESULT);
  const [answeredKey, setAnsweredKey] = useState<string | null>(null);
  const [departments, setDepartments] = useState<DepartmentOption[]>([]);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<Employee | null>(null);

  const requestKey = `${requestedPage}|${search}|${reloadTick}`;
  const loading = answeredKey !== requestKey;

  useEffect(() => {
    let cancelled = false;
    const params = new URLSearchParams({ page: String(requestedPage), page_size: String(PAGE_SIZE) });
    if (search) params.set("search", search);
    const key = `${requestedPage}|${search}|${reloadTick}`;
    api<EmployeePage>(`/api/employees?${params.toString()}`)
      .then((res) => {
        if (cancelled) return;
        setResult({
          items: Array.isArray(res?.items) ? res.items : [],
          total: res?.total ?? 0,
          page: res?.page ?? requestedPage,
          totalPages: res?.total_pages ?? 0,
        });
        setAnsweredKey(key);
      })
      .catch(() => {
        if (cancelled) return;
        setResult({ ...EMPTY_RESULT, page: requestedPage });
        setAnsweredKey(key);
      });
    return () => {
      cancelled = true;
    };
  }, [requestedPage, search, reloadTick]);

  useEffect(() => {
    let cancelled = false;
    api<DepartmentOption[]>("/api/departments")
      .then((res) => {
        if (!cancelled && Array.isArray(res)) setDepartments(res);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  const refresh = () => {
    // Re-fetch the page currently on screen with the current keyword.
    setRequestedPage(result.page);
    setReloadTick((n) => n + 1);
  };

  const header =
    tab === "employees"
      ? {
          title: "Nhân viên & Tài khoản",
          description: "Quản lý danh sách nhân sự, phân nhóm phòng ban và tài khoản truy cập MCP.",
          action: (
            <Button
              onClick={() => {
                setEditing(null);
                setDialogOpen(true);
              }}
            >
              <span className="material-symbols-outlined" style={{ fontSize: 24, width: 30 }}>
                person_add
              </span>
              Thêm nhân viên
            </Button>
          ),
        }
      : {
          title: "Quản lý Phân quyền & Vai trò",
          description: "Thiết lập quyền truy cập chi tiết (RBAC) cho từng vai trò trong toàn bộ hệ thống.",
          action: undefined,
        };

  const tabClass = (active: boolean) =>
    cn(
      "-mb-px inline-flex items-center gap-2 border-b-2 px-4 py-2.5 text-sm font-medium transition-colors",
      active
        ? "border-primary font-semibold text-primary"
        : "border-transparent text-muted-foreground hover:border-border hover:text-foreground",
    );

  return (
    <div className="flex flex-col">
      <PageHeader actionClassName="sm:mb-0.5" title={header.title} description={header.description} action={header.action} />

      <div className="mt-8 mb-14 flex gap-2 border-b">
        <button type="button" className={tabClass(tab === "employees")} onClick={() => setTab("employees")}>
          <span className="material-symbols-outlined" style={{ fontSize: 24 }}>
            group
          </span>
          Danh sách Nhân viên
          {result.total > 0 && (
            <span className="rounded-full bg-muted px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground">
              {result.total}
            </span>
          )}
        </button>
        <button type="button" className={tabClass(tab === "rbac")} onClick={() => setTab("rbac")}>
          <span className="material-symbols-outlined" style={{ fontSize: 24 }}>
            admin_panel_settings
          </span>
          Ma trận Phân quyền (RBAC)
        </button>
      </div>

      {tab === "employees" ? (
        <EmployeeTable
          employees={result.items}
          loading={loading}
          onEdit={(emp) => {
            setEditing(emp);
            setDialogOpen(true);
          }}
          onRefresh={refresh}
          page={result.page}
          totalPages={result.totalPages}
          total={result.total}
          onPageChange={setRequestedPage}
          search={search}
          onSearch={(q) => {
            setSearch(q);
            setRequestedPage(1);
            setReloadTick((n) => n + 1);
          }}
        />
      ) : (
        <RolesPermissionsCard />
      )}

      <EmployeeDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        employee={editing}
        departments={departments}
        roles={ROLES}
        onSaved={refresh}
      />
    </div>
  );
}
