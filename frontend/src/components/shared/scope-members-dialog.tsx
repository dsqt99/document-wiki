"use client";

import { useEffect, useState } from "react";
import { EmptyState } from "@/components/shared/empty-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

type ScopeMember = { employee_id: string; employee_name: string; employee_email: string; role: string };
type Person = { id: string; name: string; email: string };

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  label: string;
  scopeType: "global" | "department" | "project";
  scopeId: string;
};

const ROLES = [
  { value: "reader", key: "scope.roleReader" },
  { value: "contributor", key: "scope.roleContributor" },
  { value: "owner", key: "scope.roleOwner" },
  { value: "admin", key: "scope.roleAdmin" },
];

function capitalize(s: string): string {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
}

/** Manage direct members (with a role) of a scope. */
export function ScopeMembersDialog({ open, onOpenChange, label, scopeType, scopeId }: Props) {
  const { t } = useI18n();
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogTitle className="pr-8 text-xl font-semibold">{t("scope.membersTitle").replace("{label}", label)}</DialogTitle>
        <ScopeMembersBody key={`${scopeType}:${scopeId}`} scopeType={scopeType} scopeId={scopeId} />
      </DialogContent>
    </Dialog>
  );
}

function ScopeMembersBody({ scopeType, scopeId }: { scopeType: Props["scopeType"]; scopeId: string }) {
  const { t } = useI18n();
  const [members, setMembers] = useState<ScopeMember[] | null>(null);
  const [people, setPeople] = useState<Person[]>([]);
  const [employeeId, setEmployeeId] = useState<string | null>(null);
  const [role, setRole] = useState("reader");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const base = `/api/scopes/${scopeType}/${encodeURIComponent(scopeId)}/members`;
  const errMsg = (err: unknown) => (err instanceof Error && err.message ? err.message : t("common.error"));

  const fetchMembers = () =>
    api<ScopeMember[]>(base).then((res) => (Array.isArray(res) ? res : []));

  useEffect(() => {
    let cancelled = false;
    api<ScopeMember[]>(base)
      .then((res) => {
        if (!cancelled) setMembers(Array.isArray(res) ? res : []);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setMembers([]);
        setError(err instanceof Error && err.message ? err.message : t("common.error"));
      });
    api<{ items?: Person[] }>("/api/employees?page_size=200")
      .then((res) => {
        if (!cancelled) setPeople(Array.isArray(res?.items) ? res.items : []);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [base, t]);

  const reload = async () => {
    try {
      setMembers(await fetchMembers());
    } catch (err) {
      setMembers([]);
      setError(errMsg(err));
    }
  };

  const memberIds = new Set((members ?? []).map((m) => m.employee_id));
  const candidates = people.filter((p) => !memberIds.has(p.id));
  const picked = candidates.find((p) => p.id === employeeId);

  const add = async () => {
    if (!employeeId) return;
    setSaving(true);
    setError(null);
    try {
      await api(base, { method: "POST", body: { employee_id: employeeId, role } });
      setEmployeeId(null);
      await reload();
    } catch (err) {
      setError(errMsg(err));
    } finally {
      setSaving(false);
    }
  };

  const remove = async (id: string) => {
    if (!confirm(t("scope.removeConfirm"))) return;
    setError(null);
    try {
      await api(`${base}/${encodeURIComponent(id)}`, { method: "DELETE" });
      await reload();
    } catch (err) {
      setError(errMsg(err));
    }
  };

  const roleLabel = (v: string) => t(ROLES.find((r) => r.value === v)?.key ?? "", v);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-start gap-3 rounded-lg border border-blue-500/20 bg-blue-50 px-3 py-2.5 text-blue-800 dark:bg-blue-500/10 dark:text-blue-300">
        <span className="material-symbols-outlined shrink-0" style={{ fontSize: 20 }}>
          shield_person
        </span>
        <div className="text-xs">
          <p className="font-semibold">{scopeType === "department" ? t("scope.realmOrg") : t("scope.realmWorkspace")}</p>
          <p className="mt-0.5 opacity-90">{t("scope.realmDesc")}</p>
        </div>
      </div>

      {error && <div className="rounded-lg bg-destructive/10 px-3 py-2 text-xs text-destructive">{error}</div>}

      <div className="flex gap-2">
        <Select value={employeeId} onValueChange={(v) => setEmployeeId(v ? String(v) : null)}>
          <SelectTrigger className="min-w-0 flex-1">
            <SelectValue>
              {() =>
                picked ? (
                  <span className="truncate">
                    {picked.name} — {picked.email}
                  </span>
                ) : (
                  <span className="text-muted-foreground">{t("scope.selectEmp")}</span>
                )
              }
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            {candidates.map((p) => (
              <SelectItem key={p.id} value={p.id}>
                {p.name} — {p.email}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={role} onValueChange={(v) => setRole(v ? String(v) : "reader")}>
          <SelectTrigger className="w-32 shrink-0">
            <SelectValue>{(v: unknown) => roleLabel(String(v ?? "reader"))}</SelectValue>
          </SelectTrigger>
          <SelectContent>
            {ROLES.map((r) => (
              <SelectItem key={r.value} value={r.value}>
                {t(r.key)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button onClick={() => void add()} disabled={saving || !employeeId}>
          {saving && (
            <span className="material-symbols-outlined animate-spin" style={{ fontSize: 16 }}>
              progress_activity
            </span>
          )}
          {t("common.create")}
        </Button>
      </div>

      <div className="overflow-hidden rounded-lg border">
        <div className="bg-muted px-3 py-2 text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">
          {t("dept.currentMembers")} ({members?.length ?? 0})
        </div>
        {members === null ? (
          <div className="flex justify-center py-6 text-muted-foreground">
            <span className="material-symbols-outlined animate-spin" style={{ fontSize: 20 }}>
              progress_activity
            </span>
          </div>
        ) : members.length === 0 ? (
          <EmptyState icon="group_off" title={t("scope.noMembers")} description={t("scope.noMembersDesc")} />
        ) : (
          <ul className="max-h-60 divide-y overflow-y-auto">
            {members.map((m) => {
              const strong = m.role === "admin" || m.role === "owner";
              return (
                <li key={m.employee_id} className="flex items-center gap-3 px-3 py-2">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">{m.employee_name}</p>
                    <p className="truncate text-xs text-muted-foreground">{m.employee_email}</p>
                  </div>
                  <Badge variant="outline" className={cn(strong && "border-primary text-primary")}>
                    {capitalize(m.role)}
                  </Badge>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    title={t("common.delete")}
                    aria-label={t("common.delete")}
                    className="hover:text-destructive"
                    onClick={() => void remove(m.employee_id)}
                  >
                    <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
                      close
                    </span>
                  </Button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
