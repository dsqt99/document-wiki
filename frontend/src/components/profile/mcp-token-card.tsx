"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { Button } from "@/components/ui/button";

type IssuedToken = { token: string; employee_name?: string; instructions?: string };

/** Personal MCP token: issue, re-issue, copy (only right after issuing) and revoke. */
export function McpTokenCard() {
  const { t } = useI18n();
  const [hasToken, setHasToken] = useState(false);
  // Plain value lives only in memory, right after issuing; never persisted.
  const [token, setToken] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let active = true;
    api<{ has_token: boolean }>("/api/my/mcp-token/status")
      .then((res) => {
        if (active) setHasToken(!!res.has_token);
      })
      .catch(() => {
        /* treat as no token */
      });
    return () => {
      active = false;
    };
  }, []);

  const fail = (err: unknown) => {
    window.alert(err instanceof Error && err.message ? err.message : t("common.error", "Lỗi"));
  };

  const generate = async () => {
    setBusy(true);
    try {
      const res = await api<IssuedToken>("/api/my/mcp-token", { method: "POST" });
      setToken(res.token);
      setHasToken(true);
      setCopied(false);
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  };

  const revoke = async () => {
    if (!window.confirm(t("profile.revokeConfirm"))) return;
    setBusy(true);
    try {
      await api<{ revoked: boolean }>("/api/my/mcp-token", { method: "DELETE" });
      setToken(null);
      setHasToken(false);
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  };

  const copy = async () => {
    if (!token) return;
    try {
      await navigator.clipboard.writeText(token);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard unavailable */
    }
  };

  const revokeButton = (
    <Button variant="ghost" size="sm" className="gap-1 px-3 text-destructive hover:text-destructive" onClick={revoke} disabled={busy}>
      <span className="material-symbols-outlined" style={{ fontSize: 24 }}>
        vpn_key_off
      </span>
      {t("profile.revokeToken", "Thu hồi mã")}
    </Button>
  );

  return (
    <div className="rounded-xl border bg-surface-variant p-6">
      <div className="flex items-start gap-3">
        <span className="material-symbols-outlined text-primary" style={{ fontSize: 24 }}>
          vpn_key
        </span>
        <div>
          <h3 className="text-lg font-semibold">{t("profile.mcpTokenTitle", "Mã xác thực MCP")}</h3>
          <p className="text-xs text-muted-foreground">{t("profile.mcpTokenDesc")}</p>
        </div>
      </div>

      <div className="mt-4">
        {token ? (
          <div className="flex flex-col gap-3">
            <pre className="rounded-lg bg-[#2b211b] p-4 font-mono text-xs break-all whitespace-pre-wrap text-[#f3e9d7]">
              {token}
            </pre>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" size="sm" onClick={copy}>
                <span className="material-symbols-outlined" style={{ fontSize: 24 }}>
                  {copied ? "check" : "content_copy"}
                </span>
                {copied ? t("dash.copied", "Đã sao chép!") : t("profile.copyToken", "Sao chép mã")}
              </Button>
              {revokeButton}
            </div>
          </div>
        ) : hasToken ? (
          <div className="flex flex-col gap-3">
            <div className="flex items-start gap-2 rounded-lg border border-emerald-300/60 bg-emerald-50 p-3 text-sm text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-400">
              <span className="material-symbols-outlined" style={{ fontSize: 18 }}>
                check_circle
              </span>
              <span>{t("profile.mcpTokenActive")}</span>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" size="sm" className="gap-1 px-3" onClick={generate} disabled={busy}>
                <span className="material-symbols-outlined" style={{ fontSize: 24 }}>
                  refresh
                </span>
                {busy ? t("common.loading", "Đang tải...") : t("profile.regenerateToken", "Tạo lại mã")}
              </Button>
              {revokeButton}
            </div>
          </div>
        ) : (
          <Button onClick={generate} disabled={busy}>
            {busy ? t("common.loading", "Đang tải...") : t("profile.generateToken", "Tạo mã MCP")}
          </Button>
        )}
      </div>
    </div>
  );
}
