"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { EmptyState } from "@/components/shared/empty-state";
import { ScopeDialog } from "@/components/shared/scope-dialog";
import { useI18n } from "@/lib/i18n";

type Employee = {
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

type Props = {
  employees: Employee[];
  loading: boolean;
  onEdit: (emp: Employee) => void;
  onRefresh: () => void;
  page: number;
  totalPages: number;
  total: number;
  onPageChange: (page: number) => void;
  search: string;
  onSearch: (q: string) => void;
};

export function EmployeeTable({
  employees,
  loading,
  onEdit,
  onRefresh,
  page,
  totalPages,
  total,
  onPageChange,
  search,
  onSearch,
}: Props) {
  const { t } = useI18n();
  const [actionError, setActionError] = useState<string | null>(null);
  const [tokenDialog, setTokenDialog] = useState<{ token: string; instructions: string } | null>(null);
  const [scopeEmployee, setScopeEmployee] = useState<Employee | null>(null);
  const [searchInput, setSearchInput] = useState(search);

  const handleToggle = async (id: string) => {
    setActionError(null);
    try {
      await api(`/api/employees/${id}/toggle`, { method: "PATCH" });
      onRefresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Action failed");
    }
  };

  const handleGenerateToken = async (id: string) => {
    setActionError(null);
    try {
      const data = await api<{ token: string; instructions: string }>(
        `/api/employees/${id}/token`,
        { method: "POST" }
      );
      setTokenDialog(data);
      onRefresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to generate token");
    }
  };

  const handleRevokeToken = async (id: string) => {
    if (!confirm(t("emp.revokeToken", "Revoke this employee's MCP token?"))) return;
    setActionError(null);
    try {
      await api(`/api/employees/${id}/token`, { method: "DELETE" });
      onRefresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to revoke token");
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm(t("common.delete", "Delete this employee? This cannot be undone."))) return;
    setActionError(null);
    try {
      await api(`/api/employees/${id}`, { method: "DELETE" });
      onRefresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to delete");
    }
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSearch(searchInput);
  };

  const getRoleLabel = (role: string) => {
    switch (role) {
      case "admin":
        return t("emp.roleAdmin", "System Admin");
      case "knowledge_manager":
        return t("emp.roleKM", "Knowledge Manager");
      case "contributor":
        return t("emp.roleContributor", "Contributor");
      case "viewer":
        return t("emp.roleViewer", "Viewer");
      default:
        return role;
    }
  };

  return (
    <>
      {actionError && (
        <div className="text-sm text-destructive bg-destructive/10 px-4 py-2 rounded-lg flex items-center gap-2 mb-4">
          <span className="material-symbols-outlined text-base">error</span>
          {actionError}
        </div>
      )}

      {/* Search bar + stats */}
      <div className="flex items-center justify-between mb-4">
        <form onSubmit={handleSearchSubmit} className="flex items-center gap-2">
          <div className="relative">
            <span className="material-symbols-outlined text-sm text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2">
              search
            </span>
            <input
              type="text"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder={t("common.search", "Search by name or email...")}
              className="h-9 pl-9 pr-3 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary/50 w-[280px] placeholder:text-muted-foreground/60"
            />
            {searchInput && (
              <button
                type="button"
                onClick={() => { setSearchInput(""); onSearch(""); }}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                <span className="material-symbols-outlined text-sm">close</span>
              </button>
            )}
          </div>
        </form>
        <span className="text-xs text-muted-foreground tabular-nums">
          {total} {t("dept.employees", "employees")}
        </span>
      </div>

      {/* Table */}
      <div className="bg-card rounded-xl border border-border shadow-sahara overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <span className="material-symbols-outlined text-3xl text-muted-foreground animate-spin">
              progress_activity
            </span>
          </div>
        ) : employees.length === 0 ? (
          <EmptyState
            icon="badge"
            title={search ? t("common.noResults", "No results found") : t("emp.noEmployees", "No employees")}
            description={search ? `${t("common.noResults", "No results found")}: "${search}"` : ""}
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground">{t("emp.colEmp", "Employee")}</TableHead>
                <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground">{t("emp.colRole", "Role")}</TableHead>
                <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground">{t("emp.colDept", "Department")}</TableHead>
                <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground">{t("emp.colStatus", "Status")}</TableHead>
                <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground">{t("emp.colToken", "MCP Token")}</TableHead>
                <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground text-right w-[60px]"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {employees.map((emp) => (
                <TableRow key={emp.id} className="group hover:bg-secondary/30 transition-colors">
                  <TableCell>
                    <div className="flex items-center gap-3">
                      <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 text-xs font-bold ${emp.role === "admin"
                        ? "bg-primary/15 text-primary"
                        : "bg-accent text-accent-foreground"
                        }`}>
                        {emp.name.charAt(0).toUpperCase()}
                      </div>
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-foreground truncate">{emp.name}</p>
                        <p className="text-xs text-muted-foreground truncate">{emp.email}</p>
                      </div>
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant={emp.global_role === "admin" ? "default" : emp.global_role === "knowledge_manager" ? "outline" : "secondary"}
                      className="text-[10px] capitalize h-5 px-2 font-medium"
                    >
                      {getRoleLabel(emp.global_role)}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    {emp.department_names.length === 0 ? (
                      <span className="text-xs text-muted-foreground/50">—</span>
                    ) : (
                      <div className="flex flex-wrap gap-1">
                        {emp.department_names.map((n) => (
                          <span
                            key={n}
                            className="inline-block px-1.5 py-0.5 rounded bg-secondary text-secondary-foreground text-xs"
                          >
                            {n}
                          </span>
                        ))}
                      </div>
                    )}
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-1.5">
                      <span className={`w-2 h-2 rounded-full ${emp.is_active ? "bg-green-500" : "bg-muted-foreground/40"
                        }`} />
                      <span className={`text-xs ${emp.is_active ? "text-green-700" : "text-muted-foreground"
                        }`}>
                        {emp.is_active ? t("emp.statusActive", "Active") : t("emp.statusInactive", "Inactive")}
                      </span>
                    </div>
                  </TableCell>
                  <TableCell>
                    {emp.has_token ? (
                      <span className="text-xs text-green-600 flex items-center gap-1">
                        <span className="material-symbols-outlined text-sm filled">vpn_key</span>
                        {t("emp.connected", "Connected")}
                      </span>
                    ) : (
                      <span className="text-xs text-muted-foreground/50">—</span>
                    )}
                  </TableCell>

                  <TableCell className="text-right">
                    <DropdownMenu>
                      <DropdownMenuTrigger className="inline-flex items-center justify-center h-7 w-7 rounded-md hover:bg-accent text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity">
                        <span className="material-symbols-outlined text-base">more_vert</span>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => onEdit(emp)}>
                          <span className="material-symbols-outlined text-base mr-2" style={{ fontSize: 16 }}>edit</span>
                          {t("common.edit", "Edit")}
                        </DropdownMenuItem>
                        <DropdownMenuItem onClick={() => handleToggle(emp.id)}>
                          <span className="material-symbols-outlined text-base mr-2" style={{ fontSize: 16 }}>
                            {emp.is_active ? "lock" : "lock_open"}
                          </span>
                          {emp.is_active ? t("emp.statusInactive", "Disable") : t("emp.statusActive", "Enable")}
                        </DropdownMenuItem>
                        <DropdownMenuItem onClick={() => setScopeEmployee(emp)}>
                          <span className="material-symbols-outlined text-base mr-2" style={{ fontSize: 16 }}>folder_shared</span>
                          {t("scope.project", "Workspaces")}
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem onClick={() => handleGenerateToken(emp.id)}>
                          <span className="material-symbols-outlined text-base mr-2" style={{ fontSize: 16 }}>vpn_key</span>
                          {t("emp.generateToken", "Generate Token")}
                        </DropdownMenuItem>
                        {emp.has_token && (
                          <DropdownMenuItem onClick={() => handleRevokeToken(emp.id)} className="text-destructive">
                            <span className="material-symbols-outlined text-base mr-2" style={{ fontSize: 16 }}>key_off</span>
                            {t("emp.revokeToken", "Revoke Token")}
                          </DropdownMenuItem>
                        )}
                        <DropdownMenuSeparator />
                        <DropdownMenuItem onClick={() => handleDelete(emp.id)} className="text-destructive">
                          <span className="material-symbols-outlined text-base mr-2" style={{ fontSize: 16 }}>delete</span>
                          {t("common.delete", "Delete")}
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-4">
          <span className="text-xs text-muted-foreground">
            {t("common.page", "Page")} {page} {t("common.of", "of")} {totalPages}
          </span>
          <div className="flex items-center gap-1">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => onPageChange(page - 1)}
              className="h-8 px-2.5"
            >
              <span className="material-symbols-outlined text-sm">chevron_left</span>
            </Button>
            {Array.from({ length: Math.min(totalPages, 7) }, (_, i) => {
              let p: number;
              if (totalPages <= 7) {
                p = i + 1;
              } else if (page <= 4) {
                p = i + 1;
              } else if (page >= totalPages - 3) {
                p = totalPages - 6 + i;
              } else {
                p = page - 3 + i;
              }
              return (
                <Button
                  key={p}
                  variant={p === page ? "default" : "outline"}
                  size="sm"
                  onClick={() => onPageChange(p)}
                  className={`h-8 w-8 p-0 text-xs ${p === page
                    ? "bg-primary text-primary-foreground"
                    : ""
                    }`}
                >
                  {p}
                </Button>
              );
            })}
            <Button
              variant="outline"
              size="sm"
              disabled={page >= totalPages}
              onClick={() => onPageChange(page + 1)}
              className="h-8 px-2.5"
            >
              <span className="material-symbols-outlined text-sm">chevron_right</span>
            </Button>
          </div>
        </div>
      )}

      {scopeEmployee && (
        <ScopeDialog
          open={!!scopeEmployee}
          onOpenChange={(open) => { if (!open) setScopeEmployee(null); }}
          label={scopeEmployee.name}
          employeeId={scopeEmployee.id}
        />
      )}

      <Dialog open={!!tokenDialog} onOpenChange={() => setTokenDialog(null)}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle className="text-xl flex items-center gap-2">
              <span className="material-symbols-outlined text-primary">vpn_key</span>
              MCP Token Generated
            </DialogTitle>
          </DialogHeader>
          <div className="flex flex-col gap-4 mt-2">
            <p className="text-sm text-muted-foreground">
              Copy this token and share it securely with the employee. It will not be shown again.
            </p>
            <div className="bg-secondary rounded-lg px-4 py-3 font-mono text-sm break-all select-all">
              {tokenDialog?.token}
            </div>
            {tokenDialog?.instructions && (
              <p className="text-sm text-muted-foreground whitespace-pre-line">
                {tokenDialog.instructions}
              </p>
            )}
            <div className="flex justify-end gap-2">
              <Button
                variant="outline"
                onClick={() => {
                  if (tokenDialog?.token) navigator.clipboard.writeText(tokenDialog.token);
                }}
              >
                <span className="material-symbols-outlined text-base mr-1">content_copy</span>
                Copy Token
              </Button>
              <Button
                className="bg-primary text-primary-foreground hover:bg-primary/90"
                onClick={() => setTokenDialog(null)}
              >
                Done
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
