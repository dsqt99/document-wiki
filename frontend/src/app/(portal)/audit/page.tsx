"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { AuditTable, type AuditLogEntry } from "@/components/audit/audit-table";

/** The backend reads `page_size`; the page count is derived from `total`. */
const PAGE_SIZE = 20;

type AuditLogResponse = {
  items: AuditLogEntry[];
  total: number;
  page: number;
  page_size: number;
};

export default function AuditPage() {
  const [logs, setLogs] = useState<AuditLogEntry[]>([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async (target: number) => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({ page: String(target), page_size: String(PAGE_SIZE) });
      const res = await api<AuditLogResponse>(`/api/audit/log?${params.toString()}`);
      const size = res.page_size > 0 ? res.page_size : PAGE_SIZE;
      setLogs(res.items ?? []);
      setPage(res.page ?? target);
      setTotalPages(Math.max(1, Math.ceil((res.total ?? 0) / size)));
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : "Failed to load audit logs");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    void Promise.resolve().then(() => {
      if (active) void load(1);
    });
    return () => {
      active = false;
    };
  }, [load]);

  return (
    <>
      <PageHeader actionClassName="sm:mb-0.5"
        title="Audit Log"
        description="Review access control decisions and policy evaluations across the system."
        action={
          <Button variant="outline" onClick={() => void load(1)} disabled={loading}>
            <span className={cn("material-symbols-outlined", loading && "animate-spin")} style={{ fontSize: 24, width: 30 }}>
              refresh
            </span>
            Refresh
          </Button>
        }
      />

      <div className="flex flex-col gap-4">
        {error && (
          <div className="mb-2 flex items-center gap-2 rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">
            <span className="material-symbols-outlined" style={{ fontSize: 18 }}>
              error
            </span>
            {error}
          </div>
        )}

        <AuditTable logs={logs} loading={loading} />

        {totalPages > 1 && (
          <div className="flex items-center justify-between rounded-xl border bg-card px-4 py-3">
            <p className="text-sm text-muted-foreground">
              Page {page} of {totalPages}
            </p>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" disabled={page <= 1 || loading} onClick={() => void load(page - 1)}>
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPages || loading}
                onClick={() => void load(page + 1)}
              >
                Next
              </Button>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
