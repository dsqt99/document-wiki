/** Folder/file tree built from flat "a/b/c.md" paths (shared by the editor and the explorer). */

export type TreeFile<T> = { kind: "file"; name: string; path: string; item: T };
export type TreeFolder<T> = { kind: "folder"; name: string; path: string; children: TreeNode<T>[] };
export type TreeNode<T> = TreeFile<T> | TreeFolder<T>;

/** Placeholder that keeps an otherwise empty folder alive; never shown. */
export const KEEP_FILE = ".gitkeep";

function sortLevel<T>(nodes: TreeNode<T>[]): TreeNode<T>[] {
  nodes.sort((a, b) => {
    if (a.kind !== b.kind) return a.kind === "folder" ? -1 : 1;
    return a.name.localeCompare(b.name);
  });
  nodes.forEach((n) => n.kind === "folder" && sortLevel(n.children));
  return nodes;
}

export function buildTree<T extends { path: string }>(items: T[]): TreeNode<T>[] {
  const root: TreeNode<T>[] = [];
  const folders = new Map<string, TreeFolder<T>>();

  for (const item of items) {
    const parts = item.path.split("/").filter(Boolean);
    let level = root;
    let prefix = "";
    parts.forEach((part, i) => {
      prefix = prefix ? `${prefix}/${part}` : part;
      if (i === parts.length - 1) {
        level.push({ kind: "file", name: part, path: item.path, item });
        return;
      }
      let folder = folders.get(prefix);
      if (!folder) {
        folder = { kind: "folder", name: part, path: prefix, children: [] };
        folders.set(prefix, folder);
        level.push(folder);
      }
      level = folder.children;
    });
  }
  return sortLevel(root);
}

/** Every file below a folder, hidden placeholders included. */
export function descendantFiles<T>(folder: TreeFolder<T>): TreeFile<T>[] {
  const out: TreeFile<T>[] = [];
  const walk = (nodes: TreeNode<T>[]) =>
    nodes.forEach((n) => (n.kind === "file" ? out.push(n) : walk(n.children)));
  walk(folder.children);
  return out;
}

/** Initial pick: the SKILL.md (any case) or, failing that, the first candidate. */
export function pickDefault<T extends { path: string }>(items: T[], candidates: T[] = items): T | undefined {
  return items.find((f) => f.path.toLowerCase().endsWith("skill.md")) ?? candidates[0];
}
