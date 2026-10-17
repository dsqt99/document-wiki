"use client";

/* Read-only table of audit log rows (who did what to which resource, and the verdict). */
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/shared/empty-state";
import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/i18n";

interface AuditPrincipal {
  principal_id: string;
  principal_email?: string;
  principal_name?: string;
}

interface AuditTarget {
  resource_type: string;
  resource_id?: string;
}

export interface AuditLogEntry extends AuditPrincipal, AuditTarget {
  id: string;
  action: string;
  decision: string;
  reason?: string;
  timestamp: string;
}

const capitalize = (s: string) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);

function actionClass(action: string): string {
  const a = (action || "").toLowerCase();
  if (a === "create") return "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400";
  if (a === "delete") return "border-red-500/40 bg-red-500/10 text-red-700 dark:text-red-400";
  return "border-blue-500/40 bg-blue-500/10 text-blue-700 dark:text-blue-400";
}

/** Column share of the table width (time, principal, action, resource, decision). */
const COL_WIDTHS = ["13.77%", "26.48%", "20.84%", "15.92%", "22.99%"];

function shortId(id?: string): string {
  if (!id) return "";
  return id.length > 20 ? `${id.slice(0, 8)}...` : id;
}

export function AuditTable({ logs, loading }: { logs: AuditLogEntry[]; loading: boolean }) {
  const { t } = useI18n();

  return (
    <div className="overflow-hidden rounded-xl border bg-card shadow-lift">
      {loading ? (
        <div className="flex justify-center py-16">
          <span className="material-symbols-outlined animate-spin text-muted-foreground" style={{ fontSize: 30 }}>
            progress_activity
          </span>
        </div>
      ) : logs.length === 0 ? (
        <EmptyState
          icon="policy"
          title={t("audit.noLogs", "Không có nhật ký kiểm toán")}
          description={t("audit.noLogsDesc")}
        />
      ) : (
        <Table className="table-fixed">
          <colgroup>
            {COL_WIDTHS.map((w, i) => (
              <col key={i} style={{ width: w }} />
            ))}
          </colgroup>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              {(["audit.colTimestamp", "audit.colPrincipal", "audit.colAction", "audit.colResource", "audit.colDecision"] as const).map(
                (key) => (
                  <TableHead key={key} className="px-2 text-xs tracking-[0.05em] text-muted-foreground uppercase">
                    {t(key)}
                  </TableHead>
                ),
              )}
            </TableRow>
          </TableHeader>
          <TableBody>
            {logs.map((log) => {
              const allowed = (log.decision || "").toLowerCase() === "allow";
              return (
                <TableRow key={log.id} className="hover:bg-muted/40">
                  <TableCell className="px-2 text-xs whitespace-nowrap text-muted-foreground">
                    {new Date(log.timestamp).toLocaleString()}
                  </TableCell>
                  <TableCell className="px-2">
                    <p className="text-sm font-medium">{log.principal_name || "System/Unknown"}</p>
                    <p className="text-xs text-muted-foreground">
                      {log.principal_email || `${(log.principal_id || "").slice(0, 8)}...`}
                    </p>
                  </TableCell>
                  <TableCell className="px-2">
                    <Badge variant="outline" className={cn("font-mono text-xs font-normal", actionClass(log.action))}>
                      {log.action}
                    </Badge>
                  </TableCell>
                  <TableCell className="px-2">
                    <p className="text-sm">{capitalize(log.resource_type)}</p>
                    {log.resource_id && (
                      <p className="font-mono text-xs text-muted-foreground" title={log.resource_id}>
                        {shortId(log.resource_id)}
                      </p>
                    )}
                  </TableCell>
                  <TableCell className="px-2">
                    <div className="flex flex-col items-start gap-1">
                      <Badge
                        variant="outline"
                        className={cn(
                          "text-xs",
                          allowed
                            ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
                            : "border-red-500/40 bg-red-500/10 text-red-700 dark:text-red-400",
                        )}
                      >
                        {(log.decision || "").toUpperCase()}
                      </Badge>
                      {log.reason && (
                        <p className="max-w-[200px] truncate text-xs text-muted-foreground" title={log.reason}>
                          {log.reason}
                        </p>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
