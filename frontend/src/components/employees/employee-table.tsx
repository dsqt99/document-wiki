"use client";

import { useState, type FormEvent } from "react";
import { EmptyState } from "@/components/shared/empty-state";
import { ScopeDialog } from "@/components/shared/scope-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

export type Employee = {
  id: string;
  name: string;
  email: string;
  role: "admin" | "employee" | string;
  global_role?: string | null;
  department_ids: string[];
  department_names: string[];
  is_active: boolean;
  has_token: boolean;
  last_connected?: string | null;
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

type TokenResult = { token: string; instructions?: string | null };

function Icon({ name, size = 16, className, fill }: { name: string; size?: number; className?: string; fill?: boolean }) {
  return (
    <span
      className={cn("material-symbols-outlined", className)}
      style={{ fontSize: size, fontVariationSettings: fill ? "'FILL' 1" : undefined }}
    >
      {name}
    </span>
  );
}

/** At most 7 page numbers centred on the current page. */
export function pageWindow(page: number, totalPages: number): number[] {
  let start: number;
  let end: number;
  if (totalPages <= 7) {
    start = 1;
    end = totalPages;
  } else if (page <= 4) {
    start = 1;
    end = 7;
  } else if (page >= totalPages - 3) {
    start = totalPages - 6;
    end = totalPages;
  } else {
    start = page - 3;
    end = page + 3;
  }
  const out: number[] = [];
  for (let p = start; p <= end; p++) out.push(p);
  return out;
}

/** Capitalise the first letter of every word ("Người xem" -> "Người Xem"). */
function titleCase(label: string): string {
  return label
    .split(/(\s+)/)
    .map((w) => (w.trim() ? w.charAt(0).toLocaleUpperCase("vi") + w.slice(1) : w))
    .join("");
}

const ROLE_BADGES: Record<string, { key: string; variant?: "outline" | "secondary" }> = {
  admin: { key: "emp.roleAdmin" },
  knowledge_manager: { key: "emp.roleKM", variant: "outline" },
  contributor: { key: "emp.roleContributor", variant: "secondary" },
  viewer: { key: "emp.roleViewer", variant: "secondary" },
};

function RoleBadge({ role }: { role?: string | null }) {
  const { t } = useI18n();
  const cls = "h-5 px-2 text-[10px] capitalize";
  const def = role ? ROLE_BADGES[role] : undefined;
  const label = def ? t(def.key) : (role ?? "");
  return (
    <Badge variant={def ? def.variant : "secondary"} className={cls}>
      {titleCase(label)}
    </Badge>
  );
}

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
  const [query, setQuery] = useState(search);
  const [syncedSearch, setSyncedSearch] = useState(search);
  const [actionError, setActionError] = useState<string | null>(null);
  const [scopeFor, setScopeFor] = useState<Employee | null>(null);
  const [tokenResult, setTokenResult] = useState<TokenResult | null>(null);

  // Keep the input in step when the parent changes the active search.
  if (syncedSearch !== search) {
    setSyncedSearch(search);
    setQuery(search);
  }

  const submitSearch = (e: FormEvent) => {
    e.preventDefault();
    onSearch(query);
  };

  const run = async (fn: () => Promise<unknown>, failure: string) => {
    setActionError(null);
    try {
      await fn();
      onRefresh();
    } catch {
      setActionError(failure);
    }
  };

  const toggle = (emp: Employee) =>
    run(() => api(`/api/employees/${emp.id}/toggle`, { method: "PATCH" }), "Action failed");

  const generateToken = async (emp: Employee) => {
    setActionError(null);
    try {
      const res = await api<TokenResult>(`/api/employees/${emp.id}/token`, { method: "POST" });
      setTokenResult({ token: res?.token ?? "", instructions: res?.instructions ?? null });
      onRefresh();
    } catch {
      setActionError("Failed to generate token");
    }
  };

  const revokeToken = (emp: Employee) => {
    if (!confirm(t("emp.revokeToken"))) return;
    void run(() => api(`/api/employees/${emp.id}/token`, { method: "DELETE" }), "Failed to revoke token");
  };

  const remove = (emp: Employee) => {
    if (!confirm(t("common.delete"))) return;
    void run(() => api(`/api/employees/${emp.id}`, { method: "DELETE" }), "Failed to delete");
  };

  const copyToken = () => {
    if (tokenResult?.token) void navigator.clipboard?.writeText(tokenResult.token).catch(() => undefined);
  };

  const searching = search.trim().length > 0;

  return (
    <div className="flex flex-col gap-12">
      {actionError && (
        <div className="flex items-center gap-2 rounded-lg border border-destructive/20 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          <Icon name="error" size={18} />
          <span>{actionError}</span>
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <form onSubmit={submitSearch} className="relative w-full max-w-[280px]">
          <Icon
            name="search"
            size={18}
            className="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-muted-foreground"
          />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("common.search")}
            className="h-9 w-full rounded-lg border bg-background pr-3 pl-9 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30"
          />
          {query && (
            <button
              type="button"
              aria-label="Clear search"
              onClick={() => {
                setQuery("");
                onSearch("");
              }}
              className="absolute top-1/2 right-2 flex -translate-y-1/2 items-center text-muted-foreground hover:text-foreground"
            >
              <Icon name="close" size={16} />
            </button>
          )}
        </form>
        <span className="text-xs text-muted-foreground">
          {total} {t("dept.employees")}
        </span>
      </div>

      <div className="overflow-hidden rounded-xl border bg-card shadow-sm">
        {loading ? (
          <div className="flex justify-center py-16 text-muted-foreground">
            <Icon name="progress_activity" size={30} className="animate-spin" />
          </div>
        ) : employees.length === 0 ? (
          <EmptyState
            icon="badge"
            title={searching ? t("common.noResults") : t("emp.noEmployees")}
            description={searching ? `${t("common.noResults")}: "${search}"` : undefined}
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-[11px] tracking-[0.05em] text-muted-foreground uppercase *:h-10 *:font-semibold">
                  <th className="px-2">{t("emp.colEmp")}</th>
                  <th className="px-2">{t("emp.colRole")}</th>
                  <th className="px-2">{t("emp.colDept")}</th>
                  <th className="px-2">{t("emp.colStatus")}</th>
                  <th className="px-2">{t("emp.colToken")}</th>
                  <th className="w-[60px] px-2 text-right" />
                </tr>
              </thead>
              <tbody>
                {employees.map((emp) => (
                  <tr key={emp.id} className="group border-b last:border-b-0 hover:bg-secondary/30">
                    <td className="px-2 py-2">
                      <div className="flex min-w-0 items-center gap-3">
                        <span
                          className={cn(
                            "flex size-8 shrink-0 items-center justify-center rounded-full text-sm font-bold",
                            emp.role === "admin" ? "bg-primary/15 text-primary" : "bg-accent text-accent-foreground",
                          )}
                        >
                          {(emp.name || "?").charAt(0).toUpperCase()}
                        </span>
                        <div className="min-w-0">
                          <p className="truncate text-sm font-medium">{emp.name}</p>
                          <p className="truncate text-xs text-muted-foreground">{emp.email}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-2 py-2">
                      <RoleBadge role={emp.global_role} />
                    </td>
                    <td className="px-2 py-2">
                      {emp.department_names?.length ? (
                        <div className="flex flex-wrap gap-1">
                          {emp.department_names.map((d) => (
                            <span key={d} className="rounded bg-secondary px-1.5 py-0.5 text-[11px] text-secondary-foreground">
                              {d}
                            </span>
                          ))}
                        </div>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </td>
                    <td className="px-2 py-2">
                      <span className="inline-flex items-center gap-1.5 text-xs">
                        <span
                          className={cn("size-2 rounded-full", emp.is_active ? "bg-emerald-500" : "bg-muted-foreground/40")}
                        />
                        <span
                          className={
                            emp.is_active
                              ? "font-medium text-emerald-700 dark:text-emerald-400"
                              : "text-muted-foreground"
                          }
                        >
                          {emp.is_active ? t("emp.statusActive") : t("emp.statusInactive")}
                        </span>
                      </span>
                    </td>
                    <td className="px-2 py-2">
                      {emp.has_token ? (
                        <span className="inline-flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400">
                          <Icon name="vpn_key" size={15} fill />
                          {t("emp.connected")}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </td>
                    <td className="px-2 py-2 text-right">
                      <DropdownMenu>
                        <DropdownMenuTrigger
                          aria-label="Actions"
                          className="inline-flex size-7 items-center justify-center rounded-md text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 hover:bg-secondary hover:text-foreground focus-visible:opacity-100 data-popup-open:opacity-100"
                        >
                          <Icon name="more_vert" size={18} />
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="min-w-48">
                          <DropdownMenuItem onClick={() => onEdit(emp)}>
                            <Icon name="edit" />
                            {t("common.edit")}
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => void toggle(emp)}>
                            <Icon name={emp.is_active ? "lock" : "lock_open"} />
                            {emp.is_active ? t("emp.statusInactive") : t("emp.statusActive")}
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => setScopeFor(emp)}>
                            <Icon name="folder_shared" />
                            {t("scope.project")}
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem onClick={() => void generateToken(emp)}>
                            <Icon name="vpn_key" />
                            {t("emp.generateToken")}
                          </DropdownMenuItem>
                          {emp.has_token && (
                            <DropdownMenuItem variant="destructive" onClick={() => revokeToken(emp)}>
                              <Icon name="key_off" />
                              {t("emp.revokeToken")}
                            </DropdownMenuItem>
                          )}
                          <DropdownMenuSeparator />
                          <DropdownMenuItem variant="destructive" onClick={() => remove(emp)}>
                            <Icon name="delete" />
                            {t("common.delete")}
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {totalPages > 1 && (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <span className="text-xs text-muted-foreground">
            {t("common.page")} {page} {t("common.of")} {totalPages}
          </span>
          <div className="flex items-center gap-1">
            <Button
              variant="outline"
              size="icon-sm"
              aria-label="Previous page"
              disabled={page <= 1}
              onClick={() => onPageChange(page - 1)}
            >
              <Icon name="chevron_left" size={18} />
            </Button>
            {pageWindow(page, totalPages).map((p) => (
              <Button
                key={p}
                variant={p === page ? "default" : "outline"}
                size="icon-sm"
                className="size-8 text-xs"
                onClick={() => onPageChange(p)}
              >
                {p}
              </Button>
            ))}
            <Button
              variant="outline"
              size="icon-sm"
              aria-label="Next page"
              disabled={page >= totalPages}
              onClick={() => onPageChange(page + 1)}
            >
              <Icon name="chevron_right" size={18} />
            </Button>
          </div>
        </div>
      )}

      <ScopeDialog
        open={!!scopeFor}
        onOpenChange={(o) => {
          if (!o) setScopeFor(null);
        }}
        label={scopeFor?.name ?? ""}
        employeeId={scopeFor?.id ?? ""}
      />

      <Dialog
        open={!!tokenResult}
        onOpenChange={(o) => {
          if (!o) setTokenResult(null);
        }}
      >
        <DialogContent className="sm:max-w-lg">
          <DialogTitle className="flex items-center gap-2 pr-8 text-xl font-semibold">
            <Icon name="vpn_key" size={22} className="text-primary" />
            MCP Token Generated
          </DialogTitle>
          <p className="text-sm text-muted-foreground">
            Copy this token and share it securely with the employee. It will not be shown again.
          </p>
          <div className="rounded-lg bg-secondary p-3 font-mono text-xs break-all select-all">{tokenResult?.token}</div>
          {tokenResult?.instructions && (
            <p className="text-xs whitespace-pre-wrap text-muted-foreground">{tokenResult.instructions}</p>
          )}
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={copyToken}>
              <Icon name="content_copy" />
              Copy Token
            </Button>
            <Button onClick={() => setTokenResult(null)}>Done</Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
