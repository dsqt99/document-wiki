"use client";

import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { Employee } from "./employee-table";

export type DepartmentOption = { id: string; name: string };
export type RoleOption = { id: string; name: string };

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  employee: Employee | null;
  departments: DepartmentOption[];
  roles?: RoleOption[];
  onSaved: () => void;
};

/** Select value that opens the "create department" sub-dialog instead of adding. */
const CREATE_DEPT = "__create_department__";

function errorMessage(err: unknown, fallback: string): string {
  if (err instanceof Error && err.message) return err.message;
  if (typeof err === "string" && err) return err;
  return fallback;
}

export function EmployeeDialog({ open, onOpenChange, employee, departments, roles = [], onSaved }: Props) {
  // Remount the form whenever the target employee or the department list changes.
  const formKey = `${employee?.id ?? "new"}|${departments.map((d) => d.id).join(",")}`;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <EmployeeForm
          key={formKey}
          employee={employee}
          departments={departments}
          roles={roles}
          onCancel={() => onOpenChange(false)}
          onSaved={() => {
            onSaved();
            onOpenChange(false);
          }}
        />
      </DialogContent>
    </Dialog>
  );
}

function EmployeeForm({
  employee,
  departments,
  roles,
  onCancel,
  onSaved,
}: {
  employee: Employee | null;
  departments: DepartmentOption[];
  roles: RoleOption[];
  onCancel: () => void;
  onSaved: () => void;
}) {
  const { t } = useI18n();
  const editing = !!employee;
  const [name, setName] = useState(employee?.name ?? "");
  const [email, setEmail] = useState(employee?.email ?? "");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState(employee?.global_role || "viewer");
  const [deptList, setDeptList] = useState<DepartmentOption[]>(departments);
  const [selected, setSelected] = useState<string[]>(() =>
    employee ? [...(employee.department_ids ?? [])] : departments[0] ? [departments[0].id] : [],
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);

  const deptName = (id: string) => deptList.find((d) => d.id === id)?.name ?? id;
  const available = deptList.filter((d) => !selected.includes(d.id));
  const roleName = (id: string) => roles.find((r) => r.id === id)?.name ?? id;

  const pickDept = (value: unknown) => {
    if (value == null || value === "") return;
    const id = String(value);
    if (id === CREATE_DEPT) {
      setCreateOpen(true);
      return;
    }
    setSelected((cur) => (cur.includes(id) ? cur : [...cur, id]));
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!editing && !password) {
      setError(t("emp.passwordRequired"));
      return;
    }
    const body: Record<string, unknown> = {
      name,
      email,
      role: role === "admin" ? "admin" : "employee",
      global_role: role,
      department_ids: selected,
    };
    if (password) body.password = password;
    setSaving(true);
    try {
      if (employee) await api(`/api/employees/${employee.id}`, { method: "PUT", body });
      else await api("/api/employees", { method: "POST", body });
      onSaved();
    } catch (err) {
      setError(errorMessage(err, t("common.error")));
      setSaving(false);
    }
  };

  return (
    <>
      <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-4">
        <DialogTitle className="text-xl font-semibold">{editing ? t("emp.editTitle") : t("emp.createTitle")}</DialogTitle>

        <div className="space-y-1.5">
          <Label htmlFor="emp-name">{t("emp.name")}</Label>
          <Input id="emp-name" required value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="emp-email">{t("emp.email")}</Label>
          <Input id="emp-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="emp-password">
            {t("emp.password")}
            {editing && <span className="ml-1 font-normal text-muted-foreground">{t("emp.passwordEditHint")}</span>}
          </Label>
          <Input
            id="emp-password"
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={editing ? "••••••••" : t("emp.passwordMinHint")}
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="min-w-0 space-y-1.5">
            <Label>{t("emp.role")}</Label>
            <Select value={role} onValueChange={(v) => setRole(v ? String(v) : "viewer")}>
              <SelectTrigger className="w-full">
                <SelectValue>{(v: unknown) => roleName(String(v ?? ""))}</SelectValue>
              </SelectTrigger>
              <SelectContent>
                {roles.map((r) => (
                  <SelectItem key={r.id} value={r.id}>
                    {r.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="min-w-0 space-y-1.5">
            <Label>{t("emp.departments")}</Label>
            <Select value={null} onValueChange={pickDept}>
              <SelectTrigger className="w-full">
                <SelectValue>
                  {() => <span className="text-muted-foreground">{t("emp.addDeptPlaceholder")}</span>}
                </SelectValue>
              </SelectTrigger>
              <SelectContent className="w-auto min-w-(--anchor-width)" alignItemWithTrigger={false}>
                {available.map((d) => (
                  <SelectItem key={d.id} value={d.id}>
                    {d.name}
                  </SelectItem>
                ))}
                {available.length > 0 && <SelectSeparator />}
                <SelectItem value={CREATE_DEPT} className="font-medium text-primary">
                  <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
                    add
                  </span>
                  {t("emp.createNewDept")}
                </SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <div>
          {selected.length === 0 ? (
            <p className="text-xs text-muted-foreground italic">{t("emp.noDeptsHint")}</p>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {selected.map((id) => {
                const label = deptName(id);
                return (
                  <span
                    key={id}
                    className="inline-flex items-center gap-1 rounded-md bg-secondary py-0.5 pr-1 pl-2 text-xs text-secondary-foreground"
                  >
                    {label}
                    <button
                      type="button"
                      aria-label={`Remove ${label}`}
                      className="flex items-center rounded text-muted-foreground hover:text-destructive"
                      onClick={() => setSelected((cur) => cur.filter((x) => x !== id))}
                    >
                      <span className="material-symbols-outlined" style={{ fontSize: 14 }}>
                        close
                      </span>
                    </button>
                  </span>
                );
              })}
            </div>
          )}
        </div>

        {error && (
          <div className="flex items-start gap-2 rounded-lg bg-destructive/10 px-3 py-2 text-xs text-destructive">
            <span className="material-symbols-outlined shrink-0" style={{ fontSize: 16 }}>
              error
            </span>
            <span>{error}</span>
          </div>
        )}

        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onCancel}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" disabled={saving}>
            {saving ? t("common.loading") : editing ? t("common.save") : t("common.create")}
          </Button>
        </div>
      </form>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="sm:max-w-sm">
          <CreateDepartmentBody
            onCancel={() => setCreateOpen(false)}
            onCreated={(dept) => {
              setDeptList((cur) => (cur.some((d) => d.id === dept.id) ? cur : [...cur, dept]));
              setSelected((cur) => (cur.includes(dept.id) ? cur : [...cur, dept.id]));
              setCreateOpen(false);
            }}
          />
        </DialogContent>
      </Dialog>
    </>
  );
}

/**
 * Body of the nested "create department" dialog. Deliberately not a <form>:
 * React events bubble through portals, so a nested submit would also reach the
 * employee form. Enter is handled on the input instead.
 */
function CreateDepartmentBody({
  onCancel,
  onCreated,
}: {
  onCancel: () => void;
  onCreated: (dept: DepartmentOption) => void;
}) {
  const { t } = useI18n();
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const create = async () => {
    const trimmed = name.trim();
    if (!trimmed || saving) return;
    setSaving(true);
    setError(null);
    try {
      const dept = await api<DepartmentOption>("/api/departments", {
        method: "POST",
        body: { name: trimmed, description: "" },
      });
      onCreated({ id: dept.id, name: dept.name ?? trimmed });
    } catch (err) {
      setError(errorMessage(err, t("common.error")));
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <DialogTitle className="text-lg font-semibold">{t("emp.createDeptModalTitle")}</DialogTitle>
      <div className="space-y-1.5">
        <Label htmlFor="emp-new-dept">{t("emp.createDeptModalLabel")}</Label>
        <Input
          id="emp-new-dept"
          autoFocus
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              e.stopPropagation();
              void create();
            }
          }}
        />
      </div>
      {error && <p className="text-xs text-destructive">{error}</p>}
      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={onCancel}>
          {t("common.cancel")}
        </Button>
        <Button type="button" disabled={saving || !name.trim()} onClick={() => void create()}>
          {saving ? t("common.loading") : t("common.create")}
        </Button>
      </div>
    </div>
  );
}
