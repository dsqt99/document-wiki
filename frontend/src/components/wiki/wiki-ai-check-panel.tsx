"use client";

import { useState } from "react";
import type { AiCheckItem, AiCheckMatch, AiCheckResults, AiCheckStatus } from "@/types/wiki";
import { cn } from "@/lib/utils";

type Tone = "emerald" | "amber" | "rose" | "blue" | "muted";

const STATUS_META: Record<string, { label: string; icon: string; tone: Tone; spin?: boolean }> = {
  passed: { label: "AI: all clear", icon: "check_circle", tone: "emerald" },
  warned: { label: "AI: needs attention", icon: "warning", tone: "amber" },
  failed: { label: "AI: critical flags", icon: "report", tone: "rose" },
  running: { label: "AI: running…", icon: "progress_activity", tone: "blue", spin: true },
  queued: { label: "AI: queued", icon: "schedule", tone: "blue", spin: true },
  skipped: { label: "AI: skipped", icon: "skip_next", tone: "muted" },
  pending: { label: "AI: pending", icon: "schedule", tone: "muted" },
};

const TONE_CLASS: Record<Tone, string> = {
  emerald: "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300",
  amber: "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300",
  rose: "border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-300",
  blue: "border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-500/30 dark:bg-blue-500/10 dark:text-blue-300",
  muted: "border-border bg-muted text-muted-foreground",
};

const CHECK_INFO: Record<string, [label: string, category: string]> = {
  "pii.email": ["Email addresses", "Sensitive data"],
  "pii.phone_vn": ["Phone numbers", "Sensitive data"],
  "pii.cccd_vn": ["National ID numbers", "Sensitive data"],
  "secret.api_key_sk": ["Generic API key (sk-…)", "Sensitive data"],
  "secret.anthropic": ["Anthropic API key", "Sensitive data"],
  "secret.aws_access": ["AWS access key", "Sensitive data"],
  "secret.github_pat": ["GitHub personal access token", "Sensitive data"],
  "secret.google_api": ["Google API key", "Sensitive data"],
  "secret.jwt": ["JWT token", "Sensitive data"],
  "secret.private_key": ["Private key block", "Sensitive data"],
  "links.broken": ["Broken wikilinks", "Structure"],
  "links.self": ["Self-referencing link", "Structure"],
  "length.sanity": ["Content length", "Structure"],
  "markdown.heading_jump": ["Heading hierarchy", "Structure"],
  "markdown.unclosed_fence": ["Unclosed code fence", "Structure"],
  "semantic.duplicate": ["Similar existing pages", "Duplicates"],
  "llm.tone": ["Writing tone", "AI judgment"],
  "llm.scope_fit": ["Topic fit", "AI judgment"],
  "llm.factual": ["Factual concerns", "AI judgment"],
  "runner.error": ["AI runner error", "System"],
};

function checkInfo(id: string): { label: string; category: string } {
  const known = CHECK_INFO[id];
  if (known) return { label: known[0], category: known[1] };
  const dot = id.indexOf(".");
  const head = dot >= 0 ? id.slice(0, dot) : id;
  const tail = dot >= 0 ? id.slice(dot + 1) : id;
  const label = tail
    .replace(/_/g, " ")
    .split(/\s+/)
    .filter(Boolean)
    .map((w) => w[0].toUpperCase() + w.slice(1))
    .join(" ");
  return { label, category: head.replace(/_/g, " ") };
}

function formatMatch(m: AiCheckMatch): string {
  if (typeof m === "string") return m;
  if (m && typeof m === "object") {
    if (m.slug && typeof m.score === "number") return `${m.slug} (${Math.round(m.score * 100)}%)`;
    if (m.slug) return m.slug;
    if (typeof m.line === "number") return `L${m.line}: ${m.snippet ?? ""}`;
  }
  return JSON.stringify(m);
}

export function AiStatusBadge({ status, className }: { status: AiCheckStatus | string; className?: string }) {
  const meta = STATUS_META[status] ?? STATUS_META.pending;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium whitespace-nowrap",
        TONE_CLASS[meta.tone],
        className,
      )}
    >
      <span className={cn("material-symbols-outlined", meta.spin && "animate-spin")} style={{ fontSize: 14 }}>
        {meta.icon}
      </span>
      {meta.label}
    </span>
  );
}

function FlaggedItem({ item }: { item: AiCheckItem }) {
  const { label, category } = checkInfo(item.id);
  const fail = item.status === "fail";
  const matches = item.matches ?? [];
  return (
    <li className="flex gap-2 py-2">
      <span
        className={cn("material-symbols-outlined shrink-0", fail ? "text-rose-600" : "text-amber-600")}
        style={{ fontSize: 18 }}
      >
        {fail ? "cancel" : "warning"}
      </span>
      <div className="min-w-0 flex-1 text-xs">
        <div className="flex flex-wrap items-baseline gap-x-2">
          <span className="font-semibold text-foreground">{label}</span>
          <span className="text-muted-foreground">{category}</span>
        </div>
        {item.message && <p className="mt-0.5 text-muted-foreground">{item.message}</p>}
        {matches.length > 0 && (
          <ul className="mt-1 space-y-0.5">
            {matches.slice(0, 5).map((m, i) => (
              <li key={i} className="truncate rounded bg-muted/60 px-1.5 py-0.5 font-mono text-[11px]">
                {formatMatch(m)}
              </li>
            ))}
            {matches.length > 5 && <li className="text-[11px] text-muted-foreground">+{matches.length - 5} more…</li>}
          </ul>
        )}
      </div>
    </li>
  );
}

type WikiAiCheckPanelProps = {
  status: AiCheckStatus | string;
  results: AiCheckResults | null;
  className?: string;
};

export function WikiAiCheckPanel({ status, results, className }: WikiAiCheckPanelProps) {
  const checks = results?.checks ?? [];
  const flagged = checks.filter((c) => c.status === "warn" || c.status === "fail");
  const quiet = checks.filter((c) => c.status === "pass" || c.status === "skipped");
  const passCount = quiet.filter((c) => c.status === "pass").length;
  const skipCount = quiet.length - passCount;

  const [openOverride, setOpenOverride] = useState<boolean | null>(null);
  const [showQuiet, setShowQuiet] = useState(false);
  const open = openOverride ?? flagged.length > 0;

  const s = results?.summary;
  const summary = s
    ? `${s.pass} pass · ${s.warn} warn · ${s.fail} fail${s.skipped > 0 ? ` · ${s.skipped} skipped` : ""}`
    : null;

  return (
    <div className={cn("rounded-lg border bg-background", className)}>
      <button
        type="button"
        onClick={() => setOpenOverride(!open)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left"
      >
        <AiStatusBadge status={status} />
        {summary && <span className="text-xs text-muted-foreground">{summary}</span>}
        <span className="material-symbols-outlined ml-auto text-muted-foreground" style={{ fontSize: 18 }}>
          {open ? "expand_less" : "expand_more"}
        </span>
      </button>

      {open && (
        <div className="border-t px-3 py-2">
          {!results ? (
            <p className="py-1 text-xs text-muted-foreground">
              {status === "running"
                ? "AI pre-review in progress"
                : status === "queued"
                  ? "AI pre-review queued — worker will pick it up shortly"
                  : "AI pre-review has not run yet"}
            </p>
          ) : (
            <>
              {flagged.length === 0 ? (
                <p className="py-1 text-xs text-emerald-700 dark:text-emerald-300">All checks passed.</p>
              ) : (
                <ul className="divide-y">
                  {flagged.map((c) => (
                    <FlaggedItem key={c.id} item={c} />
                  ))}
                </ul>
              )}

              {quiet.length > 0 && (
                <div className="mt-1">
                  <button
                    type="button"
                    onClick={() => setShowQuiet((v) => !v)}
                    className="text-[11px] font-medium text-muted-foreground hover:text-foreground"
                  >
                    {showQuiet ? "Hide" : "Show"} {passCount} pass · {skipCount} skipped
                  </button>
                  {showQuiet && (
                    <ul className="mt-1 space-y-1">
                      {quiet.map((c) => {
                        const info = checkInfo(c.id);
                        const pass = c.status === "pass";
                        return (
                          <li key={c.id} className="flex items-center gap-2 text-xs text-muted-foreground">
                            <span
                              className={cn("material-symbols-outlined", pass ? "text-emerald-600" : "text-muted-foreground")}
                              style={{ fontSize: 16 }}
                            >
                              {pass ? "check_circle" : "remove_circle"}
                            </span>
                            <span className="text-foreground">{info.label}</span>
                            <span>{info.category}</span>
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </div>
              )}
            </>
          )}
          <p className="mt-2 border-t pt-2 text-[11px] text-muted-foreground italic">
            AI checks are advisory — they do not block approval.
          </p>
        </div>
      )}
    </div>
  );
}
