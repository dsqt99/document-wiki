"use client";

import { useState, useSyncExternalStore } from "react";
import { useI18n } from "@/lib/i18n";
import { Button } from "@/components/ui/button";

const noopSubscribe = () => () => {};

/** Claude Desktop config snippet pointing at this server's MCP endpoint. */
function buildConfig(origin: string): string {
  return JSON.stringify(
    {
      mcpServers: {
        arkon: {
          url: `${origin}/mcp`,
          headers: { Authorization: "Bearer <your-mcp-token>" },
        },
      },
    },
    null,
    2,
  );
}

export function McpConnectionCard() {
  const { t } = useI18n();
  const origin = useSyncExternalStore(
    noopSubscribe,
    () => window.location.origin,
    () => "https://your-server",
  );
  const [copied, setCopied] = useState(false);
  const config = buildConfig(origin);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(config);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard unavailable */
    }
  };

  return (
    <div className="rounded-xl border bg-surface-variant p-6">
      <h3 className="text-xl font-semibold">{t("dash.mcpConnection", "Kết nối MCP")}</h3>
      <p className="mt-1 text-xs text-muted-foreground">{t("dash.mcpDesc")}</p>
      <pre className="mt-4 overflow-x-auto rounded-lg bg-[#2b211b] p-4 font-mono text-xs text-[#f3e9d7]">{config}</pre>
      <Button variant="ghost" size="sm" className="mt-3 text-primary" onClick={copy}>
        <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
          {copied ? "check" : "content_copy"}
        </span>
        {copied ? t("dash.copied", "Đã sao chép!") : t("dash.copyConfig", "Sao chép cấu hình")}
      </Button>
    </div>
  );
}
