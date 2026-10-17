"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { SkillMarkdown, scrollCls } from "./skill-markdown";
import { buildTree, KEEP_FILE, type TreeNode } from "./skill-tree";
import { fmtSize } from "./skill-utils";
import type { SkillFile } from "./types";

const PREVIEW_LIMIT = 2 * 1024 * 1024;
const isMd = (p: string) => p.toLowerCase().endsWith(".md");

/** Drop a leading YAML front matter block and internal `--XXXX--` markers. */
function cleanContent(text: string): string {
  return text
    .replace(/^---\r?\n[\s\S]*?\r?\n---[ \t]*(\r?\n|$)/, "")
    .replace(/--[A-Za-z0-9]{4}--/g, "")
    .trim();
}

function ExplorerRows({
  nodes,
  depth,
  expanded,
  selected,
  onToggle,
  onSelect,
}: {
  nodes: TreeNode<SkillFile>[];
  depth: number;
  expanded: Set<string>;
  selected: string | null;
  onToggle: (p: string) => void;
  onSelect: (p: string) => void;
}) {
  return (
    <>
      {nodes.map((node) => {
        if (node.kind === "folder") {
          const open = expanded.has(node.path);
          return (
            <div key={`d:${node.path}`}>
              <button
                type="button"
                onClick={() => onToggle(node.path)}
                className="flex h-9 w-full items-center gap-1.5 rounded-md py-1.5 pr-2 text-left text-[13px] text-muted-foreground hover:bg-muted/60 hover:text-foreground"
                style={{ paddingLeft: 8 + depth * 16 }}
              >
                <span
                  className={cn("material-symbols-outlined transition-transform duration-200", open && "rotate-90")}
                  style={{ fontSize: 16 }}
                >
                  chevron_right
                </span>
                <span className="material-symbols-outlined text-amber-500" style={{ fontSize: 18 }}>
                  {open ? "folder_open" : "folder"}
                </span>
                <span className="truncate font-medium">{node.name}</span>
              </button>
              {open && (
                <ExplorerRows
                  nodes={node.children}
                  depth={depth + 1}
                  expanded={expanded}
                  selected={selected}
                  onToggle={onToggle}
                  onSelect={onSelect}
                />
              )}
            </div>
          );
        }
        if (node.name === KEEP_FILE) return null;
        const active = node.path === selected;
        const icon = isMd(node.name) ? "article" : node.item.is_text ? "description" : "draft";
        return (
          <button
            key={`f:${node.path}`}
            type="button"
            onClick={() => onSelect(node.path)}
            className={cn(
              "relative flex h-9 w-full items-center gap-1.5 rounded-md py-1.5 pr-2 text-left text-[13px]",
              active
                ? "bg-primary/10 font-semibold text-primary before:absolute before:top-1 before:bottom-1 before:left-0 before:w-0.5 before:rounded-full before:bg-primary"
                : "text-foreground/80 hover:bg-muted/60",
            )}
            style={{ paddingLeft: 32 + depth * 16 }}
          >
            <span className="material-symbols-outlined" style={{ fontSize: 20 }}>{icon}</span>
            <span className="truncate">{node.name}</span>
          </button>
        );
      })}
    </>
  );
}

type Doc = { id: string; text: string | null; failed: boolean };

/** Read-only browser of a skill package at a given version. */
export function SkillFileExplorer({ skillId, version }: { skillId: string; version?: number | null }) {
  const key = `${skillId}:${version ?? ""}`;
  const verQs = version != null ? `version=${version}` : "";

  const [list, setList] = useState<{ key: string; files: SkillFile[] } | null>(null);
  const [pick, setPick] = useState<{ key: string; path: string } | null>(null);
  const [doc, setDoc] = useState<Doc | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());

  // File list for the version being viewed; stale lists are ignored by comparing keys.
  useEffect(() => {
    let alive = true;
    api<SkillFile[]>(`/api/skills/${skillId}/files${verQs ? `?${verQs}` : ""}`)
      .then((f) => alive && setList({ key, files: Array.isArray(f) ? f : [] }))
      .catch(() => alive && setList({ key, files: [] }));
    return () => {
      alive = false;
    };
  }, [key, skillId, verQs]);

  const files = list?.key === key ? list.files : null;
  const tree = useMemo(() => (files ? buildTree(files) : []), [files]);

  const autoPick = useMemo(() => {
    if (!files) return null;
    const visible = files.filter((f) => !f.path.endsWith(`/${KEEP_FILE}`));
    return (
      visible.find((f) => f.path.toLowerCase().endsWith("skill.md")) ?? visible.find((f) => f.is_text) ?? null
    )?.path ?? null;
  }, [files]);

  const selectedPath = pick?.key === key ? pick.path : autoPick;
  const selectedFile = files?.find((f) => f.path === selectedPath) ?? null;
  const tooLarge = !!selectedFile && selectedFile.is_text && selectedFile.size > PREVIEW_LIMIT;
  const needFetch = !!selectedFile && selectedFile.is_text && !tooLarge;
  const docId = `${key}|${selectedPath ?? ""}`;

  useEffect(() => {
    if (!needFetch || !selectedPath) return;
    let alive = true;
    const qs = `path=${encodeURIComponent(selectedPath)}${verQs ? `&${verQs}` : ""}`;
    api<{ content: string }>(`/api/skills/${skillId}/files/content?${qs}`)
      .then((r) => alive && setDoc({ id: docId, text: cleanContent(r?.content ?? ""), failed: false }))
      .catch(() => alive && setDoc({ id: docId, text: null, failed: true }));
    return () => {
      alive = false;
    };
  }, [needFetch, selectedPath, skillId, verQs, docId]);

  const current = doc?.id === docId ? doc : null;
  const contentLoading = needFetch && !current;
  const shownText = current ? (current.failed ? "Error loading file content." : (current.text ?? "")) : null;

  const toggle = (p: string) =>
    setExpanded((s) => {
      const n = new Set(s);
      if (n.has(p)) n.delete(p);
      else n.add(p);
      return n;
    });

  const copy = async () => {
    if (shownText == null) return;
    try {
      await navigator.clipboard.writeText(shownText);
    } catch {
      // clipboard blocked: nothing to do
    }
  };

  const md = selectedPath ? isMd(selectedPath) : false;

  let body;
  if (contentLoading) {
    body = (
      <div className="flex h-full flex-col items-center justify-center gap-3 text-muted-foreground/60">
        <span className="material-symbols-outlined animate-spin" style={{ fontSize: 40 }}>progress_activity</span>
        <span className="text-xs font-semibold tracking-wider uppercase">Loading content...</span>
      </div>
    );
  } else if (tooLarge) {
    body = (
      <div className="flex h-full flex-col items-center justify-center gap-3 bg-amber-500/5 text-amber-700 dark:text-amber-300">
        <div className="flex size-16 items-center justify-center rounded-full bg-amber-500/10">
          <span className="material-symbols-outlined" style={{ fontSize: 32 }}>warning</span>
        </div>
        <p className="font-semibold">File Too Large</p>
        <p className="text-sm opacity-80">This file exceeds the 2MB preview limit.</p>
      </div>
    );
  } else if (selectedFile && !selectedFile.is_text) {
    body = (
      <div className="flex h-full flex-col items-center justify-center gap-3 opacity-40">
        <div className="flex size-16 items-center justify-center rounded-full bg-muted">
          <span className="material-symbols-outlined" style={{ fontSize: 32 }}>visibility_off</span>
        </div>
        <p className="font-semibold">No Preview Available</p>
        <p className="text-sm">Binary or non-text files cannot be previewed.</p>
      </div>
    );
  } else if (md && current && !current.failed) {
    body = (
      <div className="px-10 pt-[88px] pb-10 lg:px-16">
        <div className="mx-auto max-w-4xl">
          <SkillMarkdown content={shownText ?? ""} variant="detail" />
        </div>
      </div>
    );
  } else {
    body = <pre className="p-8 font-mono text-[13px] break-words whitespace-pre-wrap">{shownText}</pre>;
  }

  return (
    <div className="flex h-[800px] flex-col overflow-hidden rounded-2xl border bg-card shadow-sm lg:flex-row">
      <aside className="flex min-h-0 shrink-0 flex-col border-b bg-muted/20 max-lg:h-64 lg:w-80 lg:border-r lg:border-b-0">
        <div className="flex h-[61px] shrink-0 items-center gap-2 border-b px-4">
          <span className="material-symbols-outlined text-primary/60" style={{ fontSize: 18 }}>account_tree</span>
          <span className="text-[11px] font-bold tracking-[0.15em] text-muted-foreground uppercase">Skill Explorer</span>
        </div>
        <div className={cn("min-h-0 flex-1 overflow-y-auto p-3", scrollCls.none)}>
          {!files ? (
            <div className="space-y-1.5">
              {Array.from({ length: 8 }).map((_, i) => (
                <div key={i} className="h-8 animate-pulse rounded-md bg-muted" />
              ))}
            </div>
          ) : files.length === 0 ? (
            <div className="flex flex-col items-center gap-2 py-12 text-center opacity-40">
              <span className="material-symbols-outlined" style={{ fontSize: 48 }}>folder_open</span>
              <p className="text-xs">No files available in this package.</p>
            </div>
          ) : (
            <ExplorerRows
              nodes={tree}
              depth={0}
              expanded={expanded}
              selected={selectedPath}
              onToggle={toggle}
              onSelect={(p) => setPick({ key, path: p })}
            />
          )}
        </div>
      </aside>

      <section className="flex min-h-0 min-w-0 flex-1 flex-col">
        {!selectedFile ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-4 opacity-30">
            <div className="flex size-32 animate-pulse items-center justify-center rounded-full bg-primary/5">
              <span className="material-symbols-outlined" style={{ fontSize: 64 }}>account_tree</span>
            </div>
            <p className="font-serif text-3xl">Skill Explorer</p>
            <p className="text-xs font-semibold tracking-wider uppercase">
              Select a file from the tree to preview its content
            </p>
          </div>
        ) : (
          <>
            <div className="flex h-[61px] shrink-0 items-center gap-3 border-b px-4">
              <span className="min-w-0 truncate rounded border bg-muted/40 px-2 py-0.5 font-mono text-xs" title={selectedFile.path}>
                {selectedFile.path}
              </span>
              <div className="ml-auto flex shrink-0 items-center gap-3">
                {shownText != null && !tooLarge && (
                  <button
                    type="button"
                    onClick={() => void copy()}
                    className="inline-flex h-8 items-center gap-2 rounded-md border bg-muted/40 px-3 text-[11px] font-bold tracking-[0.1em] uppercase hover:bg-muted"
                  >
                    <span className="material-symbols-outlined" style={{ fontSize: 16 }}>content_copy</span>
                    Copy
                  </button>
                )}
                <span className="font-mono text-[10px] text-muted-foreground">{fmtSize(selectedFile.size)}</span>
              </div>
            </div>
            <div className={cn("min-h-0 flex-1 overflow-y-auto", scrollCls.none, md ? "bg-card" : "bg-muted/30")}>
              {body}
            </div>
          </>
        )}
      </section>
    </div>
  );
}
