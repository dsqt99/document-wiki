"use client";

import { useEffect, useRef, useState, type DragEvent, type KeyboardEvent, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { WikiContent } from "@/components/wiki/wiki-content";
import { cn } from "@/lib/utils";

/* ------------------------------------------------------------------ */
/* TestFileDropzone                                                    */
/* ------------------------------------------------------------------ */

function formatSize(bytes: number): string {
  const mb = bytes / (1024 * 1024);
  if (mb >= 1) return `${mb.toFixed(1)} MB`;
  return `${(bytes / 1024).toFixed(1)} KB`;
}

function extensionTone(ext: string): string {
  switch (ext) {
    case "pdf":
      return "bg-rose-500/10 text-rose-600 dark:text-rose-400";
    case "xlsx":
    case "xls":
    case "csv":
      return "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400";
    case "docx":
    case "doc":
      return "bg-blue-500/10 text-blue-600 dark:text-blue-400";
    default:
      return "bg-slate-500/10 text-slate-600 dark:text-slate-400";
  }
}

export function TestFileDropzone({
  file,
  onFile,
  onClear,
  accept,
  hint,
  thumbnailUrl,
}: {
  file: File | null;
  onFile: (file: File) => void;
  onClear: () => void;
  accept: string;
  hint: string;
  thumbnailUrl?: string | null;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const openPicker = () => inputRef.current?.click();

  function handleKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (e.target !== e.currentTarget) return;
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      openPicker();
    }
  }

  function handleDragOver(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    if (!dragging) setDragging(true);
  }

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragging(false);
    const dropped = e.dataTransfer.files?.[0];
    if (dropped) onFile(dropped);
  }

  const ext = file ? (file.name.includes(".") ? file.name.split(".").pop()!.toLowerCase() : "") : "";

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={openPicker}
      onKeyDown={handleKeyDown}
      onDragOver={handleDragOver}
      onDragEnter={handleDragOver}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      className={cn(
        "group relative cursor-pointer rounded-xl border-2 border-dashed p-4 outline-none transition-colors focus-visible:ring-3 focus-visible:ring-ring/50",
        dragging
          ? "border-primary bg-primary/5"
          : file
            ? "border-primary/40 bg-background hover:border-primary/60"
            : "border-border bg-background hover:border-primary/40 hover:bg-muted/30",
      )}
    >
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        className="hidden"
        onChange={(e) => {
          const picked = e.target.files?.[0];
          if (picked) onFile(picked);
          // Reset so picking the same file again still fires onChange.
          e.target.value = "";
        }}
      />

      {file ? (
        <div className="flex items-center gap-3">
          <div className="flex size-10 shrink-0 items-center justify-center overflow-hidden rounded-lg border border-border bg-muted/40">
            {thumbnailUrl ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={thumbnailUrl} alt="" className="size-full object-cover" />
            ) : (
              <span className="material-symbols-outlined text-xl text-primary">description</span>
            )}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex min-w-0 items-center gap-1.5">
              {ext && (
                <span
                  className={cn(
                    "shrink-0 rounded px-1 py-px font-mono text-[9px] font-semibold uppercase",
                    extensionTone(ext),
                  )}
                >
                  {ext}
                </span>
              )}
              <span className="truncate text-xs font-semibold text-foreground" title={file.name}>
                {file.name}
              </span>
            </div>
            <p className="mt-0.5 text-[11px] text-muted-foreground">
              {formatSize(file.size)} · Nhấn để đổi file
            </p>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon-xs"
            title="Gỡ file"
            aria-label="Gỡ file"
            onClick={(e) => {
              e.stopPropagation();
              onClear();
            }}
          >
            <span className="material-symbols-outlined text-base">close</span>
          </Button>
        </div>
      ) : (
        <div className="flex flex-col items-center gap-2 py-4 text-center">
          <div className="flex size-11 items-center justify-center rounded-full bg-primary/10 text-primary transition-transform group-hover:scale-110">
            <span className="material-symbols-outlined text-[22px]">upload_file</span>
          </div>
          <p className="text-xs font-semibold text-foreground">Kéo thả file hoặc bấm để chọn</p>
          <p className="text-[11px] text-muted-foreground">{hint}</p>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* PreviewStudio                                                       */
/* ------------------------------------------------------------------ */

export type StudioTab = { key: string; label: string; badge?: string };

export function Stat({ icon, children }: { icon: string; children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span className="material-symbols-outlined text-[13px]">{icon}</span>
      <span>{children}</span>
    </span>
  );
}

function ToolbarIconButton({
  icon,
  label,
  onClick,
  disabled,
}: {
  icon: string;
  label: string;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <Button
      type="button"
      variant="ghost"
      size="icon-xs"
      title={label}
      aria-label={label}
      onClick={onClick}
      disabled={disabled}
    >
      <span className="material-symbols-outlined text-[15px]">{icon}</span>
    </Button>
  );
}

export function PreviewStudio({
  title,
  icon,
  loading,
  loadingTitle,
  content,
  error,
  successLabel,
  telemetry,
  tabs,
  activeTab,
  onTab,
  downloadName,
  emptyTitle,
  emptyHint,
}: {
  title: string;
  icon: string;
  loading: boolean;
  loadingTitle: string;
  content: string | null;
  error?: string | null;
  successLabel?: string | null;
  telemetry?: ReactNode;
  tabs?: StudioTab[];
  activeTab?: string;
  onTab?: (key: string) => void;
  downloadName: string;
  emptyTitle: string;
  emptyHint: string;
}) {
  const [mode, setMode] = useState<"rendered" | "raw">("rendered");
  const [copied, setCopied] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const copyTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!expanded) return;
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key === "Escape") setExpanded(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [expanded]);

  useEffect(() => {
    return () => {
      if (copyTimer.current) clearTimeout(copyTimer.current);
    };
  }, []);

  const hasContent = content !== null && content.length > 0;

  async function handleCopy() {
    if (!content) return;
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      if (copyTimer.current) clearTimeout(copyTimer.current);
      copyTimer.current = setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard unavailable */
    }
  }

  function handleDownload() {
    if (!content) return;
    const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = downloadName;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  const showTabs = !!tabs && tabs.length > 1;

  let body: ReactNode;
  if (loading) {
    body = (
      <div className="flex h-full min-h-[320px] flex-col items-center justify-center gap-4">
        <div className="relative flex size-20 items-center justify-center overflow-hidden rounded-2xl bg-primary/10">
          <span className="material-symbols-outlined animate-pulse text-4xl text-primary">document_scanner</span>
          <span className="pointer-events-none absolute inset-x-2 h-0.5 animate-scan rounded-full bg-primary shadow-[0_0_8px_var(--primary)]" />
        </div>
        <p className="text-xs font-medium text-muted-foreground">{loadingTitle}</p>
      </div>
    );
  } else if (error) {
    body = (
      <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4">
        <div className="flex items-center gap-2 text-destructive">
          <span className="material-symbols-outlined text-lg">error</span>
          <span className="text-sm font-semibold">Thử nghiệm thất bại</span>
        </div>
        <p className="mt-2 font-mono text-xs break-all whitespace-pre-wrap text-destructive/90">{error}</p>
      </div>
    );
  } else if (content !== null) {
    if (content.trim()) {
      body =
        mode === "rendered" ? (
          <div className="prose-wiki text-sm">
            <WikiContent markdown={content} />
          </div>
        ) : (
          <pre className="rounded-lg bg-slate-950 p-4 font-mono text-xs leading-relaxed whitespace-pre-wrap text-slate-100">
            {content}
          </pre>
        );
    } else {
      body = (
        <div className="flex h-full min-h-[320px] items-center justify-center text-xs text-muted-foreground">
          Trang này không có nội dung.
        </div>
      );
    }
  } else {
    body = (
      <div className="flex h-full min-h-[320px] flex-col items-center justify-center gap-2 text-center">
        <div className="flex size-12 items-center justify-center rounded-xl bg-muted/60 text-muted-foreground/60">
          <span className="material-symbols-outlined text-2xl">find_in_page</span>
        </div>
        <p className="text-sm font-semibold text-foreground">{emptyTitle}</p>
        <p className="max-w-[300px] text-xs text-muted-foreground">{emptyHint}</p>
      </div>
    );
  }

  return (
    <>
      {expanded && (
        <div className="fixed inset-0 z-40 bg-black/50 backdrop-blur-[1px]" onClick={() => setExpanded(false)} />
      )}
      <div
        className={cn(
          "flex min-h-[420px] flex-col overflow-hidden rounded-xl border border-border bg-card",
          expanded && "fixed inset-4 z-50 min-h-0 shadow-2xl",
        )}
      >
        {/* Toolbar */}
        <div className="flex flex-wrap items-center gap-2 border-b border-border bg-muted/30 px-3 py-2 text-xs select-none">
          <div className="flex min-w-0 flex-1 items-center gap-1.5">
            <span className="material-symbols-outlined text-base text-primary">{icon}</span>
            <span className="truncate font-semibold text-foreground">{title}</span>
            {successLabel && (
              <span className="ml-1 inline-flex items-center gap-1 rounded-full border border-emerald-500/40 px-2 py-px text-[10px] font-medium text-emerald-600 dark:text-emerald-400">
                <span className="size-1.5 rounded-full bg-emerald-500" />
                {successLabel}
              </span>
            )}
          </div>
          <div className="flex items-center gap-1">
            <div className="flex rounded-md border border-border bg-background p-0.5">
              {(["rendered", "raw"] as const).map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => setMode(m)}
                  className={cn(
                    "rounded px-2 py-0.5 text-[11px] font-medium transition-colors",
                    mode === m ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {m === "rendered" ? "Rendered" : "Raw"}
                </button>
              ))}
            </div>
            <ToolbarIconButton
              icon={copied ? "check" : "content_copy"}
              label="Sao chép"
              onClick={() => void handleCopy()}
              disabled={!hasContent}
            />
            <ToolbarIconButton icon="download" label="Tải về .md" onClick={handleDownload} disabled={!hasContent} />
            <ToolbarIconButton
              icon={expanded ? "close_fullscreen" : "open_in_full"}
              label={expanded ? "Thu nhỏ (Esc)" : "Toàn màn hình"}
              onClick={() => setExpanded((v) => !v)}
            />
          </div>
        </div>

        {/* Telemetry */}
        {telemetry && (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-border/60 px-3 py-1.5 font-mono text-[11px] text-muted-foreground">
            {telemetry}
          </div>
        )}

        {/* Sub tabs */}
        {showTabs && (
          <div className="flex gap-1 overflow-x-auto border-b border-border/60 px-3 py-1.5">
            {tabs!.map((tab) => {
              const on = tab.key === activeTab;
              return (
                <button
                  key={tab.key}
                  type="button"
                  onClick={() => onTab?.(tab.key)}
                  className={cn(
                    "inline-flex shrink-0 items-center gap-1 rounded-md px-2.5 py-1 text-[11px] font-medium transition-colors",
                    on ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:text-foreground",
                  )}
                >
                  {tab.label}
                  {tab.badge && (
                    <span className="rounded bg-blue-500/15 px-1 font-mono text-[9px] font-semibold text-blue-600 dark:text-blue-300">
                      {tab.badge}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        )}

        {/* Content */}
        <div className={cn("flex-1 overflow-y-auto p-4", !expanded && "max-h-[520px]")}>{body}</div>
      </div>
    </>
  );
}
