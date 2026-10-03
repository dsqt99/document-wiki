"use client";

import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { EmployeeTable } from "@/components/employees/employee-table";
import { EmployeeDialog } from "@/components/employees/employee-dialog";
import { RolesPermissionsCard } from "@/components/settings/roles-permissions-card";

export type Department = {
  id: string;
  name: string;
};

export type Employee = {
  id: string;
  name: string;
  email: string;
  role: string;
  global_role: string;
  department_ids: string[];
  department_names: string[];
  is_active: boolean;
  has_token: boolean;
  last_connected?: string;
};

type PaginatedResponse = {
  items: Employee[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};

export default function EmployeesPage() {
  const [activeTab, setActiveTab] = useState<"employees" | "rbac">("employees");
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const roles = [
    { id: "viewer", name: "Viewer" },
    { id: "contributor", name: "Contributor" },
    { id: "knowledge_manager", name: "Knowledge Manager" },
    { id: "admin", name: "System Admin" }
  ];
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editEmployee, setEditEmployee] = useState<Employee | null>(null);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState("");
  const pageSize = 20;

  const loadEmployees = useCallback(async (p = 1, s = "") => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page: String(p), page_size: String(pageSize) });
      if (s) params.set("search", s);
      const data = await api<PaginatedResponse>(`/api/employees?${params}`);
      setEmployees(data.items);
      setTotal(data.total);
      setTotalPages(data.total_pages);
      setPage(data.page);
    } catch {
      setEmployees([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadEmployees();
    api<Department[]>("/api/departments").then(setDepartments).catch(() => {});
  }, [loadEmployees]);

  const handleCreate = () => {
    setEditEmployee(null);
    setDialogOpen(true);
  };

  const handleEdit = (emp: Employee) => {
    setEditEmployee(emp);
    setDialogOpen(true);
  };

  const handleSearch = (q: string) => {
    setSearch(q);
    setPage(1);
    loadEmployees(1, q);
  };

  return (
    <>
      <PageHeader
        title={activeTab === "employees" ? "Nhân viên & Tài khoản" : "Quản lý Phân quyền & Vai trò"}
        description={
          activeTab === "employees"
            ? "Quản lý danh sách nhân sự, phân nhóm phòng ban và tài khoản truy cập MCP."
            : "Thiết lập quyền truy cập chi tiết (RBAC) cho từng vai trò trong toàn bộ hệ thống."
        }
        action={
          activeTab === "employees" ? (
            <Button
              onClick={handleCreate}
              className="bg-primary text-primary-foreground hover:bg-primary/90 shadow-sm"
            >
              <span className="material-symbols-outlined text-base mr-1.5">
                person_add
              </span>
              Thêm nhân viên
            </Button>
          ) : undefined
        }
      />

      {/* Modern Navigation Tabs */}
      <div className="flex items-center gap-2 border-b border-border/70 mb-6">
        <button
          type="button"
          onClick={() => setActiveTab("employees")}
          className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-all duration-150 ${
            activeTab === "employees"
              ? "border-primary text-primary font-semibold"
              : "border-transparent text-muted-foreground hover:text-foreground hover:border-border"
          }`}
        >
          <span className="material-symbols-outlined text-[18px]">group</span>
          <span>Danh sách Nhân viên</span>
          {total > 0 && (
            <span className="ml-1 px-2 py-0.5 text-[11px] rounded-full bg-muted text-muted-foreground font-mono font-medium">
              {total}
            </span>
          )}
        </button>

        <button
          type="button"
          onClick={() => setActiveTab("rbac")}
          className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-all duration-150 ${
            activeTab === "rbac"
              ? "border-primary text-primary font-semibold"
              : "border-transparent text-muted-foreground hover:text-foreground hover:border-border"
          }`}
        >
          <span className="material-symbols-outlined text-[18px]">admin_panel_settings</span>
          <span>Ma trận Phân quyền (RBAC)</span>
        </button>
      </div>

      {activeTab === "employees" ? (
        <EmployeeTable
          employees={employees}
          loading={loading}
          onEdit={handleEdit}
          onRefresh={() => loadEmployees(page, search)}
          page={page}
          totalPages={totalPages}
          total={total}
          onPageChange={(p) => { setPage(p); loadEmployees(p, search); }}
          search={search}
          onSearch={handleSearch}
        />
      ) : (
        <RolesPermissionsCard />
      )}

      <EmployeeDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        employee={editEmployee}
        departments={departments}
        roles={roles}
        onSaved={() => loadEmployees(page, search)}
      />
    </>
  );
}
