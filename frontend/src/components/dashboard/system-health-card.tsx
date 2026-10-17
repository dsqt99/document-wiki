"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

type Health = { api: string; database: string; worker: string };
type ProbeState = "loading" | "ok" | "fail";

const FAILED: Health = { api: "error", database: "error", worker: "error" };

function stateOf(health: Health | null, key: keyof Health): ProbeState {
  if (!health) return "loading";
  return health[key] === "healthy" ? "ok" : "fail";
}

const TILE: Record<ProbeState, { icon: string; box: string; iconClass: string }> = {
  ok: {
    icon: "check_circle",
    box: "bg-emerald-500/10",
    iconClass: "filled text-emerald-600 dark:text-emerald-400",
  },
  fail: { icon: "error", box: "bg-destructive/10", iconClass: "text-destructive" },
  loading: { icon: "progress_activity", box: "bg-muted", iconClass: "animate-spin text-muted-foreground" },
};

export function SystemHealthCard() {
  const { t } = useI18n();
  const [health, setHealth] = useState<Health | null>(null);

  useEffect(() => {
    let active = true;
    api<Health>("/api/health")
      .then((res) => {
        if (active) setHealth(res);
      })
      .catch(() => {
        if (active) setHealth(FAILED);
      });
    return () => {
      active = false;
    };
  }, []);

  const probes: { key: keyof Health; label: string }[] = [
    { key: "api", label: t("dash.healthApi", "API") },
    { key: "database", label: t("dash.healthDb", "Cơ sở dữ liệu") },
    { key: "worker", label: t("dash.healthWorker", "Tiến trình nền") },
  ];
  const allOk = probes.every((p) => stateOf(health, p.key) === "ok");

  return (
    <div className="rounded-xl border bg-card p-6 shadow-lift">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-xl font-semibold">{t("dash.healthTitle", "Trạng thái hệ thống")}</h3>
        {health && (
          <span className={cn("flex items-center gap-1 text-xs font-medium", allOk ? "text-primary" : "text-destructive")}>
            <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
              {allOk ? "check_circle" : "warning"}
            </span>
            {allOk ? t("dash.healthOnline") : t("dash.healthDegraded")}
          </span>
        )}
      </div>
      <div className="mt-4 grid grid-cols-3 gap-3">
        {probes.map((p) => {
          const tile = TILE[stateOf(health, p.key)];
          return (
            <div key={p.key} className={cn("flex flex-col items-center gap-2 rounded-lg p-4", tile.box)}>
              <span className={cn("material-symbols-outlined", tile.iconClass)} style={{ fontSize: 24 }}>
                {tile.icon}
              </span>
              <span className="text-xs font-medium">{p.label}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
