"use client";

import { useEffect, useState } from "react";
import { EmptyState } from "@/components/shared/empty-state";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

type Person = { id: string; name: string; email: string; department_ids?: string[] };
type EmployeePage = { items?: Person[] };

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  deptId: string;
  deptName: string;
};

function fetchItems(path: string): Promise<Person[]> {
  return api<EmployeePage>(path)
    .then((res) => (Array.isArray(res?.items) ? res.items : []))
    .catch(() => []);
}

export function DeptMembersDialog({ open, onOpenChange, deptId, deptName }: Props) {
  const { t } = useI18n();
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogTitle className="pr-8 text-xl font-semibold">{t("dept.membersTitle").replace("{name}", deptName)}</DialogTitle>
        {/* remounts on every open → fresh selection/error state and a new fetch */}
        <MembersBody key={deptId} deptId={deptId} deptName={deptName} />
      </DialogContent>
    </Dialog>
  );
}

function MembersBody({ deptId, deptName }: { deptId: string; deptName: string }) {
  const { t } = useI18n();
  const [members, setMembers] = useState<Person[] | null>(null);
  const [everyone, setEveryone] = useState<Person[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const membersPath = `/api/employees?department_id=${encodeURIComponent(deptId)}&page_size=200`;

  useEffect(() => {
    let cancelled = false;
    fetchItems(membersPath).then((items) => {
      if (!cancelled) setMembers(items);
    });
    fetchItems("/api/employees?page_size=500").then((items) => {
      if (!cancelled) setEveryone(items);
    });
    return () => {
      cancelled = true;
    };
  }, [membersPath]);

  const reloadMembers = () => fetchItems(membersPath).then(setMembers);

  const memberIds = new Set((members ?? []).map((m) => m.id));
  const candidates = everyone.filter((p) => !memberIds.has(p.id));
  const selectedPerson = candidates.find((p) => p.id === selectedId);

  const add = async () => {
    if (!selectedId) return;
    setSaving(true);
    setError(null);
    try {
      await api(`/api/employees/${selectedId}/departments`, { method: "POST", body: { department_id: deptId } });
      setSelectedId(null);
      await reloadMembers();
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : t("common.error"));
    } finally {
      setSaving(false);
    }
  };

  const remove = async (empId: string) => {
    setError(null);
    try {
      await api(`/api/employees/${empId}/departments/${deptId}`, { method: "DELETE" });
      await reloadMembers();
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : t("common.error"));
    }
  };

  return (
    <div className="flex flex-col gap-4">
      {error && (
        <div className="flex items-start gap-2 rounded-lg bg-destructive/10 px-3 py-2 text-xs text-destructive">
          <span className="material-symbols-outlined shrink-0" style={{ fontSize: 16 }}>
            error
          </span>
          <span>{error}</span>
        </div>
      )}

      <div className="flex gap-2">
        <Select value={selectedId} onValueChange={(v) => setSelectedId(v ? String(v) : null)}>
          <SelectTrigger className="min-w-0 flex-1">
            <SelectValue>
              {() =>
                selectedPerson ? (
                  <span className="truncate">
                    {selectedPerson.name} — {selectedPerson.email}
                  </span>
                ) : (
                  <span className="text-muted-foreground">{t("dept.selectEmpToAdd")}</span>
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
        <Button onClick={() => void add()} disabled={saving || !selectedId}>
          {saving && (
            <span className="material-symbols-outlined animate-spin" style={{ fontSize: 16 }}>
              progress_activity
            </span>
          )}
          {t("dept.addMember")}
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
          <EmptyState icon="group_off" title={t("dept.noMembers")} description={t("dept.noMembersDesc")} />
        ) : (
          <ul className="max-h-60 divide-y overflow-y-auto">
            {members.map((m) => (
              <li key={m.id} className="flex items-center gap-3 px-3 py-2">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{m.name}</p>
                  <p className="truncate text-xs text-muted-foreground">{m.email}</p>
                </div>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label={`Remove ${m.name} from ${deptName}`}
                  className="hover:text-destructive"
                  onClick={() => void remove(m.id)}
                >
                  <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
                    close
                  </span>
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <p className="text-xs text-muted-foreground">{t("dept.memberMultiHint")}</p>
    </div>
  );
}
