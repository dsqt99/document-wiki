"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { WikiContent } from "@/components/wiki/wiki-content";

/**
 * Test-lab building blocks shared by the Document-processing and OCR cards:
 * a file dropzone and a Markdown preview studio (rendered/raw, copy, .md
 * download, fullscreen).
 */

function fileBadgeColor(name: string) {
  const ext = name.split(".").pop()?.toLowerCase();
  switch (ext) {
    case "pdf":
      return "bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/20";
    case "xlsx":
    case "xls":
    case "csv":
      return "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20";
    case "docx":
    case "doc":
      return "bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20";
    default:
      return "bg-slate-500/10 text-slate-600 dark:text-slate-400 border-slate-500/20";
  }
}

function formatSize(bytes: number) {
  return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${(bytes / 1024).toFixed(1)} KB`;
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
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [dragging, setDragging] = useState(false);

  return (
    <div
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") inputRef.current?.click();
      }}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        const f = e.dataTransfer.files?.[0];
        if (f) onFile(f);
      }}
      onClick={() => inputRef.current?.click()}
      className={`group cursor-pointer rounded-xl border-2 border-dashed p-3 transition-colors outline-none focus-visible:ring-2 focus-visible:ring-primary/40 ${
        dragging
          ? "border-primary bg-primary/10"
          : file
            ? "border-primary/40 bg-primary/5 hover:border-primary/60"
            : "border-border/80 bg-muted/15 hover:border-primary/50 hover:bg-muted/30"
      }`}
    >
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onFile(f);
          e.target.value = "";
        }}
      />
      {file ? (
        <div className="flex items-center gap-3 text-left">
          {thumbnailUrl ? (
            <div className="h-10 w-10 shrink-0 overflow-hidden rounded-lg border border-border/80 bg-background">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={thumbnailUrl} alt="" className="h-full w-full object-cover" />
            </div>
          ) : (
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-border/80 bg-background">
              <span className="material-symbols-outlined text-xl text-primary">description</span>
            </div>
          )}
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5">
              <span
                className={`rounded border px-1.5 font-mono text-[9px] uppercase ${fileBadgeColor(file.name)}`}
              >
                {file.name.split(".").pop()}
              </span>
              <p className="truncate text-xs font-medium text-foreground">{file.name}</p>
            </div>
            <p className="mt-0.5 text-[11px] text-muted-foreground">
              {formatSize(file.size)} · Nhấn để đổi file
            </p>
          </div>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onClear();
            }}
            className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-muted/80 hover:text-foreground"
            title="Gỡ file"
          >
            <span className="material-symbols-outlined text-base">close</span>
          </button>
        </div>
      ) : (
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary transition-transform group-hover:scale-105">
            <span className="material-symbols-outlined text-xl">upload_file</span>
          </div>
          <div className="min-w-0">
            <p className="text-xs font-semibold text-foreground">Kéo thả file hoặc bấm để chọn</p>
            <p className="mt-0.5 text-[11px] text-muted-foreground">{hint}</p>
          </div>
        </div>
      )}
    </div>
  );
}

export type StudioTab = { key: string; label: string; badge?: string };

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
  /** Markdown shown in the studio; null = nothing to show yet. */
  content: string | null;
  error?: string | null;
  successLabel?: string | null;
  telemetry?: React.ReactNode;
  tabs?: StudioTab[];
  activeTab?: string;
  onTab?: (key: string) => void;
  downloadName: string;
  emptyTitle: string;
  emptyHint: string;
}) {
  const [viewMode, setViewMode] = useState<"rendered" | "raw">("rendered");
  const [copied, setCopied] = useState(false);
  const [expanded, setExpanded] = useState(false);

  // Esc leaves fullscreen.
  useEffect(() => {
    if (!expanded) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setExpanded(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [expanded]);

  function copy() {
    if (!content) return;
    void navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  function download() {
    if (!content) return;
    const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = downloadName;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <>
      {expanded && (
        <div className="fixed inset-0 z-40 bg-black/40 backdrop-blur-[1px]" onClick={() => setExpanded(false)} />
      )}
      <div
        className={`flex flex-col overflow-hidden rounded-xl border border-border/80 bg-card shadow-xs ${
          expanded ? "fixed inset-4 z-50 bg-background shadow-2xl" : "h-full min-h-[420px]"
        }`}
      >
        {/* Toolbar */}
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/70 bg-muted/40 px-3 py-2 text-xs select-none">
          <div className="flex items-center gap-2">
            <span className="flex items-center gap-1.5 font-semibold text-foreground">
              <span className="material-symbols-outlined text-base text-primary">{icon}</span>
              {title}
            </span>
            {successLabel && (
              <span className="inline-flex h-5 items-center gap-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 text-[10px] font-medium text-emerald-600 dark:text-emerald-400">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                {successLabel}
              </span>
            )}
          </div>
          <div className="flex items-center gap-1">
            <div className="flex rounded-md border border-border/80 bg-background p-0.5">
              {(["rendered", "raw"] as const).map((m) => (
                <button
                  key={m}
                  onClick={() => setViewMode(m)}
                  className={`rounded px-2.5 py-0.5 text-[11px] font-medium transition-colors ${
                    viewMode === m ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {m === "rendered" ? "Rendered" : "Raw"}
                </button>
              ))}
            </div>
            <Button
              variant="ghost"
              size="sm"
              disabled={!content}
              onClick={copy}
              className="h-7 w-7 p-0 text-muted-foreground hover:text-foreground"
              title="Sao chép"
            >
              <span className="material-symbols-outlined text-sm">{copied ? "check" : "content_copy"}</span>
            </Button>
            <Button
              variant="ghost"
              size="sm"
              disabled={!content}
              onClick={download}
              className="h-7 w-7 p-0 text-muted-foreground hover:text-foreground"
              title="Tải về .md"
            >
              <span className="material-symbols-outlined text-sm">download</span>
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setExpanded((x) => !x)}
              className="h-7 w-7 p-0 text-muted-foreground hover:text-foreground"
              title={expanded ? "Thu nhỏ (Esc)" : "Toàn màn hình"}
            >
              <span className="material-symbols-outlined text-sm">
                {expanded ? "close_fullscreen" : "open_in_full"}
              </span>
            </Button>
          </div>
        </div>

        {telemetry && (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-border/50 bg-muted/20 px-3 py-1.5 font-mono text-[11px] text-muted-foreground">
            {telemetry}
          </div>
        )}

        {tabs && tabs.length > 1 && (
          <div className="flex items-center gap-1 overflow-x-auto border-b border-border/50 bg-muted/10 px-3 py-1.5">
            {tabs.map((t) => (
              <button
                key={t.key}
                onClick={() => onTab?.(t.key)}
                className={`flex shrink-0 items-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium whitespace-nowrap transition-colors ${
                  activeTab === t.key
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted/40 text-muted-foreground hover:bg-muted hover:text-foreground"
                }`}
              >
                {t.label}
                {t.badge && (
                  <span className="rounded bg-blue-500/20 px-1 font-mono text-[9px] text-blue-600 dark:text-blue-300">
                    {t.badge}
                  </span>
                )}
              </button>
            ))}
          </div>
        )}

        <div
          className={`relative flex-1 overflow-y-auto p-4 ${expanded ? "" : "max-h-[520px]"}`}
        >
          {loading ? (
            <div className="flex h-full min-h-[280px] flex-col items-center justify-center gap-3 text-center">
              <div className="relative flex h-16 w-16 items-center justify-center overflow-hidden rounded-2xl border border-primary/20 bg-primary/10">
                <span className="material-symbols-outlined animate-pulse text-3xl text-primary">document_scanner</span>
                <div className="absolute inset-x-0 h-1 animate-[scan_2s_ease-in-out_infinite] bg-gradient-to-r from-transparent via-cyan-400 to-transparent" />
              </div>
              <p className="text-xs font-semibold text-foreground">{loadingTitle}</p>
            </div>
          ) : error ? (
            <div className="flex items-start gap-2 rounded-lg border border-destructive/20 bg-destructive/10 p-3 text-xs text-destructive">
              <span className="material-symbols-outlined mt-0.5 shrink-0 text-base">error</span>
              <div className="min-w-0 space-y-1">
                <p className="font-semibold">Thử nghiệm thất bại</p>
                <p className="font-mono text-[11px] break-all opacity-90">{error}</p>
              </div>
            </div>
          ) : content != null ? (
            content.trim() ? (
              viewMode === "rendered" ? (
                <div className="prose prose-sm max-w-none text-xs leading-relaxed dark:prose-invert">
                  <WikiContent markdown={content} />
                </div>
              ) : (
                <pre className="overflow-x-auto rounded-lg border border-slate-800 bg-slate-950 p-4 font-mono text-[11px] leading-relaxed whitespace-pre-wrap break-words text-slate-200">
                  {content}
                </pre>
              )
            ) : (
              <p className="py-10 text-center text-xs text-muted-foreground">Trang này không có nội dung.</p>
            )
          ) : (
            <div className="flex h-full min-h-[280px] flex-col items-center justify-center p-6 text-center text-muted-foreground">
              <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-2xl border border-border bg-muted/40 text-muted-foreground/60">
                <span className="material-symbols-outlined text-2xl">find_in_page</span>
              </div>
              <p className="text-xs font-semibold text-foreground">{emptyTitle}</p>
              <p className="mt-1 max-w-[300px] text-[11px]">{emptyHint}</p>
            </div>
          )}
        </div>
      </div>
    </>
  );
}

/** One "icon value" item of the studio telemetry bar. */
export function Stat({ icon, children }: { icon: string; children: React.ReactNode }) {
  return (
    <span className="flex items-center gap-1">
      <span className="material-symbols-outlined text-[13px]">{icon}</span>
      {children}
    </span>
  );
}
