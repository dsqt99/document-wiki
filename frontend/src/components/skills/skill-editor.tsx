"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api, ApiError, apiUpload } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { DiffViewer } from "./diff-viewer";
import { SkillMarkdown, scrollCls } from "./skill-markdown";
import { buildTree, descendantFiles, KEEP_FILE, pickDefault, type TreeFolder, type TreeNode } from "./skill-tree";
import { errMessage, titleSlug, TONE } from "./skill-utils";
import type { ContributionFile, ContributionMeta, DiffCode } from "./types";

type SaveState = "idle" | "saving" | "saved" | "error";
type DiffMap = Record<string, DiffCode>;

const SAVE_LABEL: Record<SaveState, { dot: string; text: string }> = {
  idle: { dot: "bg-muted-foreground/40", text: "Ready" },
  saving: { dot: "bg-amber-500 animate-pulse", text: "Saving..." },
  saved: { dot: "bg-emerald-500", text: "All Saved" },
  error: { dot: "bg-destructive", text: "Save Error" },
};

const DIFF_BADGE: Record<DiffCode, { title: string; cls: string }> = {
  M: { title: "Modified", cls: "border-amber-500/40 " + TONE.amber },
  A: { title: "Added", cls: "border-emerald-500/40 " + TONE.green },
  D: { title: "Deleted", cls: "border-destructive/40 " + TONE.red },
};

function DiffBadge({ code }: { code: DiffCode | null | undefined }) {
  if (!code) return null;
  const b = DIFF_BADGE[code];
  return (
    <span
      title={b.title}
      className={cn(
        "inline-flex size-4 shrink-0 cursor-help items-center justify-center rounded-full border text-[9px] font-bold",
        b.cls,
      )}
    >
      {code}
    </span>
  );
}

/** Aggregate status of a folder from all files below it. */
function folderCode(folder: TreeFolder<ContributionFile>, diff: DiffMap): DiffCode | null {
  const codes = descendantFiles(folder).map((f) => diff[f.path]);
  const changed = codes.filter(Boolean) as DiffCode[];
  if (changed.length === 0) return null;
  const kinds = new Set(changed);
  if (kinds.size === 1 && changed.length === codes.length) return changed[0];
  return "M";
}

const enc = encodeURIComponent;
const isMd = (p: string) => p.toLowerCase().endsWith(".md");
const baseName = (p: string) => p.split("/").pop() ?? p;
const parentOf = (p: string) => (p.includes("/") ? p.slice(0, p.lastIndexOf("/")) : "");

type TreeAction = "newFile" | "newFolder" | "upload" | "rename" | "delete";

const menuTriggerCls =
  "inline-flex size-7 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground";

function MenuEntry({
  icon,
  label,
  onClick,
  disabled,
  danger,
}: {
  icon: string;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  danger?: boolean;
}) {
  return (
    <DropdownMenuItem disabled={disabled} variant={danger ? "destructive" : "default"} onClick={onClick}>
      <span className="material-symbols-outlined" style={{ fontSize: 16 }}>{icon}</span>
      {label}
    </DropdownMenuItem>
  );
}

function RowMenu({ children }: { children: ReactNode }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger className={menuTriggerCls} title="Actions" aria-label="Actions">
        <span className="material-symbols-outlined" style={{ fontSize: 16 }}>more_vert</span>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-40">
        {children}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

type TreeRowsProps = {
  nodes: TreeNode<ContributionFile>[];
  depth: number;
  expanded: Set<string>;
  selected: string | null;
  rootFolder: string;
  review: boolean;
  diff: DiffMap;
  onToggle: (path: string) => void;
  onSelect: (path: string) => void;
  onAction: (action: TreeAction, path: string, isFolder: boolean) => void;
};

/** Recursive rows of the editor's file tree (folders first, collapsed by default). */
function TreeRows(props: TreeRowsProps) {
  const { nodes, depth, expanded, selected, rootFolder, review, diff, onToggle, onSelect, onAction } = props;
  return (
    <>
      {nodes.map((node) => {
        if (node.kind === "folder") {
          const open = expanded.has(node.path);
          const isRoot = node.path === rootFolder;
          return (
            <div key={`d:${node.path}`}>
              <div
                role="button"
                tabIndex={0}
                onClick={() => onToggle(node.path)}
                onKeyDown={(e) => e.key === "Enter" && onToggle(node.path)}
                className="group/row flex cursor-pointer items-center gap-1 rounded-md py-1 pr-1 text-[13px] text-muted-foreground hover:bg-muted/60 hover:font-semibold hover:text-foreground"
                style={{ paddingLeft: 8 + depth * 16 }}
              >
                <span
                  className={cn("material-symbols-outlined transition-transform", open && "rotate-90")}
                  style={{ fontSize: 16 }}
                >
                  chevron_right
                </span>
                <span className="material-symbols-outlined text-amber-500" style={{ fontSize: 18 }}>
                  {open ? "folder_open" : "folder"}
                </span>
                <span className="min-w-0 flex-1 truncate font-medium">{node.name}</span>
                {review && <DiffBadge code={folderCode(node, diff)} />}
                <span className="opacity-0 group-hover/row:opacity-100" onClick={(e) => e.stopPropagation()}>
                  <RowMenu>
                    <MenuEntry icon="add_box" label="New File" onClick={() => onAction("newFile", node.path, true)} />
                    <MenuEntry
                      icon="create_new_folder"
                      label="New Folder"
                      onClick={() => onAction("newFolder", node.path, true)}
                    />
                    <MenuEntry icon="upload_file" label="Upload File" onClick={() => onAction("upload", node.path, true)} />
                    <MenuEntry
                      icon="edit"
                      label="Rename"
                      disabled={isRoot}
                      onClick={() => onAction("rename", node.path, true)}
                    />
                    <MenuEntry
                      icon="delete"
                      label="Delete"
                      danger
                      disabled={isRoot}
                      onClick={() => onAction("delete", node.path, true)}
                    />
                  </RowMenu>
                </span>
              </div>
              {open && <TreeRows {...props} nodes={node.children} depth={depth + 1} />}
            </div>
          );
        }
        if (node.name === KEEP_FILE) return null;
        const active = node.path === selected;
        const locked = node.path === `${rootFolder}/SKILL.md`;
        return (
          <div
            key={`f:${node.path}`}
            role="button"
            tabIndex={0}
            onClick={() => onSelect(node.path)}
            onKeyDown={(e) => e.key === "Enter" && onSelect(node.path)}
            className={cn(
              "group/row flex cursor-pointer items-center gap-1.5 rounded-md py-1 pr-1 text-[13px]",
              active ? "bg-primary/10 font-semibold text-primary" : "text-foreground/80 hover:bg-muted/60",
            )}
            style={{ paddingLeft: 32 + depth * 16 }}
          >
            <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
              {isMd(node.name) ? "article" : "description"}
            </span>
            <span className="min-w-0 flex-1 truncate">{node.name}</span>
            {review && <DiffBadge code={diff[node.path]} />}
            <span
              className={cn(active ? "opacity-100" : "opacity-0 group-hover/row:opacity-100")}
              onClick={(e) => e.stopPropagation()}
            >
              <RowMenu>
                <MenuEntry
                  icon="edit"
                  label="Rename"
                  disabled={locked}
                  onClick={() => onAction("rename", node.path, false)}
                />
                <MenuEntry
                  icon="delete"
                  label="Delete"
                  danger
                  disabled={locked}
                  onClick={() => onAction("delete", node.path, false)}
                />
              </RowMenu>
            </span>
          </div>
        );
      })}
    </>
  );
}

type Ctx = { list: ContributionFile[]; diff: DiffMap; meta: ContributionMeta | null };

/**
 * Multi-file proposal editor: file tree on the left, editor/preview/diff on the right.
 * `edit` mode autosaves every change after 500ms; `review` mode never writes content.
 */
export function SkillEditor({
  contributionId,
  mode = "review",
}: {
  contributionId: string;
  mode?: "edit" | "review";
  onSubmitted?: () => void;
  onStatusChange?: () => void;
}) {
  const { user, hasPermission } = useAuth();
  const canSeeOriginal = user?.role === "admin" || hasPermission("skill:contribution:review");
  const base = `/api/skill-contributions/${contributionId}`;

  const [meta, setMeta] = useState<ContributionMeta | null>(null);
  const [files, setFiles] = useState<ContributionFile[]>([]);
  const [diff, setDiff] = useState<DiffMap>({});
  const [filesLoading, setFilesLoading] = useState(true);
  const [readOnly, setReadOnly] = useState(false);
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());

  const [selected, setSelected] = useState<string | null>(null);
  const [content, setContent] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const [original, setOriginal] = useState<string | null>(null);
  const [contentLoading, setContentLoading] = useState(false);
  const [view, setView] = useState<"edit" | "preview">("edit");
  const [showDiff, setShowDiff] = useState(false);
  const [saveState, setSaveState] = useState<SaveState>("idle");

  // Mirrors used inside async callbacks (only written from handlers/callbacks).
  const ctxRef = useRef<Ctx>({ list: [], diff: {}, meta: null });
  const selectedRef = useRef<string | null>(null);
  const pendingRef = useRef<{ path: string; text: string } | null>(null);
  const requestRef = useRef(0);
  const uploadInput = useRef<HTMLInputElement>(null);
  const uploadDir = useRef("");

  const visible = useMemo(() => {
    if (mode !== "review") return files;
    const known = new Set(files.map((f) => f.path));
    const deleted = Object.entries(diff)
      .filter(([p, c]) => c === "D" && !known.has(p))
      .map(([path]) => ({ path, size: 0, is_text: true }));
    return [...files, ...deleted];
  }, [files, diff, mode]);

  const rootFolder = visible.length ? visible[0].path.split("/")[0] : "";
  const tree = useMemo(() => buildTree(visible), [visible]);

  const refreshDiff = useCallback(async (): Promise<DiffMap> => {
    try {
      const d = await api<DiffMap>(`${base}/diff-status`);
      const map = d && typeof d === "object" ? d : {};
      setDiff(map);
      ctxRef.current = { ...ctxRef.current, diff: map };
      return map;
    } catch {
      return ctxRef.current.diff;
    }
  }, [base]);

  const visibleOf = (ctx: Ctx): ContributionFile[] => {
    if (mode !== "review") return ctx.list;
    const known = new Set(ctx.list.map((f) => f.path));
    const extra = Object.entries(ctx.diff)
      .filter(([p, c]) => c === "D" && !known.has(p))
      .map(([path]) => ({ path, size: 0, is_text: true }));
    return [...ctx.list, ...extra];
  };

  /** Write a file's content; returns true on success. */
  const persist = useCallback(
    async (path: string, text: string) => {
      setSaveState("saving");
      try {
        await api(`${base}/files`, { method: "PUT", body: { path, content: text } });
        if (pendingRef.current?.path === path && pendingRef.current.text === text) pendingRef.current = null;
        if (selectedRef.current === path) {
          setSaved(text);
          setSaveState("saved");
        }
        await refreshDiff();
        return true;
      } catch {
        if (selectedRef.current === path) setSaveState("error");
        return false;
      }
    },
    [base, refreshDiff],
  );

  const loadOriginal = async (path: string, ctx: Ctx, req: number) => {
    const m = ctx.meta;
    if (!m || !m.skill_id || !(m.status === "pending" || canSeeOriginal)) return;
    const root = visibleOf(ctx)[0]?.path.split("/")[0] ?? "";
    const stripped = root && path.startsWith(`${root}/`) ? path.slice(root.length + 1) : path;
    const ver = m.base_version != null ? `&version=${m.base_version}` : "";
    for (const candidate of stripped === path ? [path] : [stripped, path]) {
      try {
        const r = await api<{ content: string }>(
          `/api/skills/${m.skill_id}/files/content?path=${enc(candidate)}${ver}`,
        );
        if (requestRef.current === req) setOriginal(r?.content ?? "");
        return;
      } catch {
        // try the next form of the path
      }
    }
  };

  const selectFile = async (path: string | null, ctx: Ctx = ctxRef.current) => {
    // Flush an unsaved edit of the file we are leaving (the debounce timer is cancelled).
    const pending = pendingRef.current;
    if (mode === "edit" && pending && pending.path !== path) void persist(pending.path, pending.text);
    pendingRef.current = null;

    const req = ++requestRef.current;
    selectedRef.current = path;
    setSelected(path);
    setSaveState("idle");
    setOriginal(null);
    setContentLoading(false);
    if (!path) {
      setContent(null);
      setSaved(null);
      return;
    }
    const entry = visibleOf(ctx).find((f) => f.path === path);
    const code = ctx.diff[path];
    if (code === "D") {
      setContent("");
      setSaved("");
    } else if (entry?.is_text || code) {
      setContentLoading(true);
      let text = "";
      try {
        const r = await api<{ content: string }>(`${base}/files/content?path=${enc(path)}`);
        text = r?.content ?? "";
      } catch {
        text = "";
      }
      if (requestRef.current !== req) return;
      setContent(text);
      setSaved(text);
      setContentLoading(false);
    } else {
      setContent(null);
      setSaved(null);
    }
    void loadOriginal(path, ctx, req);
  };

  /** Reload the file list (and diff map); returns the fresh context or null on failure. */
  const loadFiles = async (metaArg?: ContributionMeta | null): Promise<Ctx | null> => {
    setFilesLoading(true);
    try {
      const list = await api<ContributionFile[]>(`${base}/files`);
      const arr = Array.isArray(list) ? list : [];
      setFiles(arr);
      ctxRef.current = { ...ctxRef.current, list: arr, meta: metaArg !== undefined ? metaArg : ctxRef.current.meta };
      await refreshDiff();
      return ctxRef.current;
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) window.location.reload();
      else setReadOnly(true);
      return null;
    } finally {
      setFilesLoading(false);
    }
  };

  // Initial load: proposal metadata first, then files, then pick a default file.
  useEffect(() => {
    let alive = true;
    (async () => {
      let m: ContributionMeta | null = null;
      try {
        m = await api<ContributionMeta>(base);
      } catch {
        m = null;
      }
      if (!alive) return;
      setMeta(m);
      const ctx = await loadFiles(m);
      if (!alive || !ctx || selectedRef.current) return;
      const vis = visibleOf(ctx);
      const first = pickDefault(vis);
      if (first) await selectFile(first.path, ctx);
    })();
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reload only when the proposal changes
  }, [base]);

  // Autosave 500ms after the last keystroke (edit mode only).
  useEffect(() => {
    if (mode !== "edit" || selected == null || content == null || content === saved) return;
    const path = selected;
    const text = content;
    pendingRef.current = { path, text };
    const timer = setTimeout(() => void persist(path, text), 500);
    return () => clearTimeout(timer);
  }, [mode, selected, content, saved, persist]);

  /* ---------- file operations ---------- */

  const baseDirFor = (folder?: string) =>
    folder || rootFolder || (meta?.title ? titleSlug(meta.title) : "") || "skill";

  const reloadAndSelect = async (path?: string | null) => {
    const ctx = await loadFiles();
    if (ctx && path !== undefined) await selectFile(path, ctx);
  };

  const newFile = async (folder?: string) => {
    const dir = baseDirFor(folder);
    const name = window.prompt(`Enter file name inside ${dir}/ (e.g. src/utils.py):`);
    if (!name || !name.trim()) return;
    const path = `${dir}/${name.trim().replace(/^\/+/, "")}`;
    try {
      await api(`${base}/files`, { method: "PUT", body: { path, content: "" } });
      setExpanded((s) => new Set(s).add(dir));
      await reloadAndSelect(path);
      setView("edit");
      setShowDiff(false);
    } catch (err) {
      console.error("Create file failed", err);
    }
  };

  const newFolder = async (folder?: string) => {
    const dir = baseDirFor(folder);
    const name = window.prompt(`Enter folder name inside ${dir}/:`);
    if (!name || !name.trim()) return;
    try {
      await api(`${base}/files`, {
        method: "PUT",
        body: { path: `${dir}/${name.trim().replace(/^\/+|\/+$/g, "")}/${KEEP_FILE}`, content: "" },
      });
      setExpanded((s) => new Set(s).add(dir));
      await loadFiles();
    } catch (err) {
      console.error("Create folder failed", err);
    }
  };

  const startUpload = (folder?: string) => {
    uploadDir.current = baseDirFor(folder);
    uploadInput.current?.click();
  };

  const onUploadPicked = async (file: File | undefined) => {
    if (uploadInput.current) uploadInput.current.value = "";
    if (!file) return;
    const path = `${uploadDir.current}/${file.name}`;
    const fd = new FormData();
    fd.append("file", file);
    try {
      await apiUpload(`${base}/upload?path=${enc(path)}`, fd);
      await reloadAndSelect(path);
    } catch {
      alert("Upload failed");
    }
  };

  const remove = async (path: string, isFolder: boolean) => {
    if (isFolder && path === rootFolder) return alert("Cannot delete the root folder.");
    if (!isFolder && path === `${rootFolder}/SKILL.md`) return alert("Cannot delete the SKILL.md file.");
    if (!confirm(`Are you sure you want to delete this ${isFolder ? "folder" : "file"}: ${path}?`)) return;
    try {
      await api(`${base}/files?path=${enc(path)}`, { method: "DELETE" });
      const cur = selectedRef.current;
      const hit = cur && (cur === path || cur.startsWith(`${path}/`));
      if (hit) await selectFile(null);
      await loadFiles();
    } catch (err) {
      alert(`Delete failed: ${errMessage(err, "Unknown error")}`);
    }
  };

  const rename = async (path: string, isFolder: boolean) => {
    if (isFolder && path === rootFolder) return alert("Cannot rename the root folder.");
    if (!isFolder && path === `${rootFolder}/SKILL.md`) return alert("Cannot rename the SKILL.md file.");
    const oldName = baseName(path);
    const next = window.prompt(`Enter new name for ${isFolder ? "folder" : "file"}:`, oldName);
    if (!next || !next.trim() || next.trim() === oldName) return;
    const parent = parentOf(path);
    const newPath = parent ? `${parent}/${next.trim()}` : next.trim();
    try {
      await api(`${base}/rename?old_path=${enc(path)}&new_path=${enc(newPath)}`, { method: "POST" });
      const cur = selectedRef.current;
      if (cur === path || (cur && cur.startsWith(`${path}/`))) {
        const moved = newPath + cur.slice(path.length);
        selectedRef.current = moved;
        setSelected(moved);
      }
      await loadFiles();
    } catch (err) {
      alert(`Rename failed: ${errMessage(err, "Unknown error")}`);
    }
  };

  const toggleFolder = (path: string) =>
    setExpanded((s) => {
      const n = new Set(s);
      if (n.has(path)) n.delete(path);
      else n.add(path);
      return n;
    });

  /* ---------- rendering ---------- */

  if (readOnly) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 bg-card p-8 text-center">
        <div className="flex size-16 items-center justify-center rounded-full bg-amber-500/10 text-amber-600">
          <span className="material-symbols-outlined" style={{ fontSize: 32 }}>lock</span>
        </div>
        <h3 className="font-serif text-xl font-semibold">Read Only Mode</h3>
        <p className="text-sm text-muted-foreground">An error occurred while loading files.</p>
      </div>
    );
  }

  const review = mode === "review";
  const saveInfo = SAVE_LABEL[review ? "idle" : saveState];
  const md = selected ? isMd(selected) : false;
  const segBtn = (active: boolean) =>
    cn(
      "rounded px-2.5 py-1 text-[10px] font-bold tracking-wider uppercase transition-colors",
      active ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
    );
  const textareaCls = cn(
    "h-full w-full resize-none border-0 bg-transparent p-4 font-mono text-[13px] leading-relaxed outline-none",
    scrollCls.none,
  );

  let body: ReactNode;
  if (contentLoading) {
    body = <div className="flex h-full items-center justify-center text-sm text-muted-foreground">Loading content...</div>;
  } else if (content === null) {
    body = (
      <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
        Binary file or no preview available.
      </div>
    );
  } else if (showDiff) {
    body = <DiffViewer original={original ?? ""} current={content} />;
  } else if (md && view === "preview") {
    body = (
      <div className="grid h-full grid-cols-2 divide-x">
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder="Enter markdown here..."
          className={textareaCls}
          spellCheck={false}
        />
        <div className={cn("h-full overflow-y-auto p-6", scrollCls.thin)}>
          <SkillMarkdown content={content} variant="editor" />
        </div>
      </div>
    );
  } else if (view === "edit") {
    body = (
      <textarea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        placeholder="Enter code or markdown here..."
        className={textareaCls}
        spellCheck={false}
      />
    );
  } else {
    body = (
      <div className={cn("h-full overflow-y-auto p-8", scrollCls.thin)}>
        <div className="mx-auto max-w-4xl">
          <SkillMarkdown content={content} variant="editor" />
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col bg-card lg:flex-row">
      <aside className="flex min-h-0 shrink-0 flex-col border-b bg-muted/20 lg:w-80 lg:border-r lg:border-b-0">
        <div className="flex items-center justify-between border-b px-3 py-2">
          <span className="text-[10px] font-bold tracking-[0.2em] text-muted-foreground uppercase">Files</span>
          <button
            type="button"
            title="Refresh"
            aria-label="Refresh"
            onClick={() => void loadFiles()}
            className="inline-flex size-7 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <span className="material-symbols-outlined" style={{ fontSize: 16 }}>refresh</span>
          </button>
          <input
            ref={uploadInput}
            type="file"
            className="hidden"
            onChange={(e) => void onUploadPicked(e.target.files?.[0])}
          />
        </div>
        <div className={cn("min-h-0 flex-1 overflow-y-auto p-3", scrollCls.none)}>
          {filesLoading && files.length === 0 ? (
            <p className="text-xs text-muted-foreground/70">Loading...</p>
          ) : (
            <TreeRows
              nodes={tree}
              depth={0}
              expanded={expanded}
              selected={selected}
              rootFolder={rootFolder}
              review={review}
              diff={diff}
              onToggle={toggleFolder}
              onSelect={(p) => void selectFile(p)}
              onAction={(action, p, isFolder) => {
                if (action === "newFile") void newFile(p);
                else if (action === "newFolder") void newFolder(p);
                else if (action === "upload") startUpload(p);
                else if (action === "rename") void rename(p, isFolder);
                else void remove(p, isFolder);
              }}
            />
          )}
        </div>
      </aside>

      <section className="flex min-h-0 min-w-0 flex-1 flex-col">
        {!selected ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-3 opacity-30">
            <span className="material-symbols-outlined" style={{ fontSize: 96 }}>edit_note</span>
            <p className="text-sm font-bold tracking-wider uppercase">Select a file to start editing</p>
          </div>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-2 border-b px-4 py-2">
              <span
                className="max-w-[300px] truncate rounded border px-2 py-0.5 font-mono text-xs font-semibold"
                title={selected}
              >
                {selected}
              </span>
              <div className="ml-auto flex items-center gap-2">
                {md && (
                  <div className="flex rounded-md bg-muted p-0.5">
                    <button
                      type="button"
                      className={segBtn(view === "edit" && !showDiff)}
                      onClick={() => {
                        setView("edit");
                        setShowDiff(false);
                      }}
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      className={segBtn(view === "preview" && !showDiff)}
                      onClick={() => {
                        setView("preview");
                        setShowDiff(false);
                      }}
                    >
                      Preview
                    </button>
                  </div>
                )}
                {review && (
                  <button
                    type="button"
                    onClick={() => setShowDiff((v) => !v)}
                    className={cn(
                      "inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-[10px] font-bold tracking-wider uppercase transition-colors",
                      showDiff ? "bg-background text-foreground shadow-sm ring-1 ring-border" : "text-muted-foreground hover:text-foreground",
                    )}
                  >
                    <span className="material-symbols-outlined" style={{ fontSize: 14 }}>difference</span>
                    Diff
                  </button>
                )}
                <span className="inline-flex items-center gap-1.5 rounded-full bg-muted px-2 py-0.5 text-[10px] font-bold tracking-wider text-muted-foreground uppercase">
                  <span className={cn("size-1.5 rounded-full", saveInfo.dot)} />
                  {saveInfo.text}
                </span>
              </div>
            </div>
            <div className="min-h-0 flex-1">{body}</div>
          </>
        )}
      </section>
    </div>
  );
}
