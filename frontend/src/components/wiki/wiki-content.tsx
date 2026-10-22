"use client";

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import Link from "next/link";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useImageResolver } from "@/lib/hooks/use-image-resolver";
import { normalizeMarkup } from "@/components/wiki/formatted-inline-text";
import { WikiImage } from "@/components/wiki/wiki-image";
import { cn } from "@/lib/utils";

export { normalizeMarkup };

// ---------------------------------------------------------------------------
// Pre-processing
// ---------------------------------------------------------------------------

/** Turn `[[slug|label]]` / `[[slug]]` into markdown links to /wiki/slug, then tidy markup. */
export function preprocessWikilinks(md: string): string {
  if (!md) return "";
  const linked = md.replace(/\[\[([^\]|\n]+?)(?:\|([^\]\n]+?))?\]\]/g, (_m, rawSlug: string, rawLabel?: string) => {
    const slug = rawSlug.trim();
    const label = (rawLabel ?? slug).trim();
    const href = `/wiki/${slug.split("/").map(encodeURIComponent).join("/")}`;
    return `[${label.replace(/([[\]])/g, "\\$1")}](${href})`;
  });
  return normalizeMarkup(linked);
}

// ---------------------------------------------------------------------------
// URL filter
// ---------------------------------------------------------------------------

const SAFE_DATA_IMAGE = /^data:image\/(png|jpe?g|gif|webp|bmp);base64,/i;

function filterUrl(url: string): string {
  const u = (url ?? "").trim();
  if (!u) return "";
  if (u.startsWith("image://")) return u;
  if (SAFE_DATA_IMAGE.test(u)) return u;
  if (/^(https?:\/\/|mailto:|tel:)/i.test(u)) return u;
  if (u.startsWith("#") || u.startsWith("/") || u.startsWith("./") || u.startsWith("../")) return u;
  return "";
}

// ---------------------------------------------------------------------------
// Headings / table of contents
// ---------------------------------------------------------------------------

/** Heading anchor id; the TOC and the heading renderer both use this. */
function headingId(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s-]/gu, "")
    .trim()
    .replace(/\s+/g, "-");
}

function stripInline(text: string): string {
  const undecorated = text.replace(/<[^>]+>|[*_`]/g, "").trim();
  if (/^Điều\s+\d/iu.test(undecorated)) text = text.replace(/<sup\b[^>]*>.*?<\/sup>/gi, "");
  return text
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/<[^>]+>/g, "")
    .replace(/[*_`]/g, "")
    .trim();
}

type TocItem = { id: string; text: string; level: number };

function extractToc(md: string): TocItem[] {
  const items: TocItem[] = [];
  let fence: string | null = null;
  for (const line of md.split(/\r?\n/)) {
    const f = line.match(/^\s{0,3}(`{3,}|~{3,})/);
    if (f) {
      if (!fence) fence = f[1][0];
      else if (f[1][0] === fence) fence = null;
      continue;
    }
    if (fence) continue;
    const m = line.match(/^\s{0,3}(#{2,4})\s+(.+?)\s*#*\s*$/);
    if (!m) continue;
    const text = stripInline(m[2]);
    if (!text) continue;
    items.push({ id: headingId(text), text, level: m[1].length });
  }
  return items;
}

type HastLike = { type?: string; tagName?: string; value?: string; children?: HastLike[] };

function hastText(node: HastLike | undefined, omitFootnotes = false): string {
  if (!node) return "";
  if (omitFootnotes && node.tagName === "sup") return "";
  if (node.type === "text") return node.value ?? "";
  return (node.children ?? []).map((child) => hastText(child, omitFootnotes)).join("");
}

function headingNodeText(node: HastLike | undefined): string {
  const text = hastText(node);
  return /^Điều\s+\d/iu.test(text.trim()) ? hastText(node, true) : text;
}

function TableOfContents({ items }: { items: TocItem[] }) {
  const [open, setOpen] = useState(true);
  const [activeId, setActiveId] = useState<string | null>(null);

  useEffect(() => {
    if (typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((e) => e.isIntersecting);
        if (visible.length > 0) setActiveId(visible[0].target.id);
      },
      { rootMargin: "-80px 0px -60% 0px", threshold: 0.5 },
    );
    for (const it of items) {
      const el = document.getElementById(it.id);
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
  }, [items]);

  return (
    <nav className="mb-6 rounded-xl border bg-surface/60 text-sm">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-4 pt-3 pb-2 text-left text-xs font-semibold tracking-wide text-muted-foreground uppercase"
      >
        <span className="material-symbols-outlined text-muted-foreground" style={{ fontSize: 18 }}>
          toc
        </span>
        <span className="flex-1">Mục lục · {items.length}</span>
        <span className="material-symbols-outlined text-muted-foreground" style={{ fontSize: 18 }}>
          {open ? "expand_less" : "expand_more"}
        </span>
      </button>
      {open && (
        <ul className="space-y-0.5 px-4 pb-3">
          {items.map((it, i) => (
            <li key={`${it.id}-${i}`} style={{ paddingLeft: (it.level - 2) * 16 }}>
              <button
                type="button"
                onClick={() => document.getElementById(it.id)?.scrollIntoView({ behavior: "smooth", block: "start" })}
                className={cn(
                  "w-full truncate rounded px-1 py-0.5 text-left text-[13px] text-muted-foreground hover:text-foreground",
                  activeId === it.id && "font-semibold text-primary hover:text-primary",
                )}
              >
                {it.text}
              </button>
            </li>
          ))}
        </ul>
      )}
    </nav>
  );
}

// ---------------------------------------------------------------------------
// Code block with copy button
// ---------------------------------------------------------------------------

function CodeBlock({ children }: { children: ReactNode }) {
  const preRef = useRef<HTMLPreElement>(null);
  const [copied, setCopied] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);

  const copy = async () => {
    const text = preRef.current?.textContent ?? "";
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard unavailable: leave the icon unchanged */
    }
  };

  return (
    <div className="group relative my-4 rounded-lg border bg-surface">
      <pre
        ref={preRef}
        className="overflow-x-auto p-4 font-mono text-[13px] leading-relaxed [&_code]:bg-transparent [&_code]:p-0 [&_code]:text-foreground"
      >
        {children}
      </pre>
      <Tooltip>
        <TooltipTrigger
          render={
            <button
              type="button"
              onClick={copy}
              aria-label="Copy code"
              className="absolute top-2 right-2 flex size-7 items-center justify-center rounded-md border bg-background/90 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 hover:text-foreground focus-visible:opacity-100"
            />
          }
        >
          <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
            {copied ? "check" : "content_copy"}
          </span>
        </TooltipTrigger>
        <TooltipContent>Copy code</TooltipContent>
      </Tooltip>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

type WikiContentProps = {
  markdown: string;
  showToc?: boolean;
  onWikiLinkClick?: (slug: string) => void;
  linkSuffix?: string;
};

const IMAGE_ID_RE = /image:\/\/([A-Za-z0-9-]+)/g;

export function WikiContent({ markdown, onWikiLinkClick, linkSuffix = "", showToc = true }: WikiContentProps) {
  const processed = useMemo(() => preprocessWikilinks(markdown ?? ""), [markdown]);
  const toc = useMemo(() => extractToc(processed), [processed]);
  const imageIds = useMemo(() => Array.from(processed.matchAll(IMAGE_ID_RE), (m) => m[1]), [processed]);
  const images = useImageResolver(imageIds);

  const components = useMemo<Components>(() => {
    const heading = (Tag: "h2" | "h3" | "h4", cls: string) => {
      function Heading({ node, children }: { node?: unknown; children?: ReactNode }) {
        return (
          <Tag id={headingId(headingNodeText(node as HastLike))} className={cls}>
            {children}
          </Tag>
        );
      }
      return Heading;
    };

    return {
      h1: ({ children }) => <h1 className="mt-8 mb-4 text-3xl font-bold tracking-tight first:mt-0">{children}</h1>,
      h2: heading("h2", "mt-8 mb-3 scroll-mt-24 border-b pb-1.5 text-2xl font-semibold tracking-tight"),
      h3: heading("h3", "mt-6 mb-2 scroll-mt-24 text-xl font-semibold"),
      h4: heading("h4", "mt-5 mb-2 scroll-mt-24 text-base font-semibold"),
      p: ({ children }) => <p className="my-3 text-sm leading-7">{children}</p>,
      mark: ({ children }) => (
        <mark className="rounded-sm bg-amber-200/70 px-0.5 text-inherit dark:bg-amber-500/30">{children}</mark>
      ),
      a: ({ href, children }) => {
        const h = href ?? "";
        if (h.startsWith("/wiki/")) {
          if (onWikiLinkClick) {
            let slug = h.slice("/wiki/".length);
            try {
              slug = decodeURIComponent(slug);
            } catch {
              /* keep raw slug */
            }
            return (
              <button
                type="button"
                onClick={() => onWikiLinkClick(slug)}
                className="font-medium text-primary underline-offset-4 hover:underline"
              >
                {children}
              </button>
            );
          }
          return (
            <Link href={h + linkSuffix} className="font-medium text-primary underline-offset-4 hover:underline">
              {children}
            </Link>
          );
        }
        if (/^https?:\/\//i.test(h)) {
          return (
            <a href={h} target="_blank" rel="noopener noreferrer" className="text-primary underline underline-offset-4">
              {children}
            </a>
          );
        }
        return (
          <a href={h || undefined} className="text-primary underline underline-offset-4">
            {children}
          </a>
        );
      },
      code: ({ className, children }) => (
        <code className={cn("rounded bg-surface-variant px-1.5 py-0.5 font-mono text-[0.85em] text-primary", className)}>
          {children}
        </code>
      ),
      pre: ({ children }) => <CodeBlock>{children}</CodeBlock>,
      blockquote: ({ children }) => (
        <blockquote className="my-4 border-l-4 border-primary pl-4 text-muted-foreground italic">{children}</blockquote>
      ),
      ul: ({ children, className }) => (
        <ul className={cn("my-3 list-disc pl-6 text-sm", className?.includes("contains-task-list") && "list-none pl-1")}>
          {children}
        </ul>
      ),
      ol: ({ children }) => <ol className="my-3 list-decimal pl-6 text-sm">{children}</ol>,
      li: ({ children }) => <li className="my-1 leading-7">{children}</li>,
      hr: () => <hr className="my-6 border-border" />,
      strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
      em: ({ children }) => <em className="italic">{children}</em>,
      img: ({ src, alt }) => {
        const s = typeof src === "string" ? src : "";
        if (s.startsWith("image://")) {
          const id = s.slice("image://".length);
          if (images.resolved[id]) return <WikiImage src={images.resolved[id]} alt={alt} status="ok" />;
          if (images.denied.has(id)) return <WikiImage alt={alt} status="denied" />;
          if (images.loading) return <WikiImage alt={alt} status="loading" />;
          return <WikiImage alt={alt} status="missing" />;
        }
        if (!s) return null;
        // eslint-disable-next-line @next/next/no-img-element
        return <img src={s} alt={alt ?? ""} loading="lazy" className="my-3 max-w-full rounded-lg" />;
      },
      table: ({ children }) => (
        <div className="my-4 overflow-x-auto rounded-lg border">
          <Table>{children}</Table>
        </div>
      ),
      thead: ({ children }) => <TableHeader className="bg-surface-variant/50">{children}</TableHeader>,
      tbody: ({ children }) => <TableBody>{children}</TableBody>,
      tr: ({ children }) => <TableRow>{children}</TableRow>,
      th: ({ children, style }) => (
        <TableHead style={style} className="text-xs font-semibold tracking-wide uppercase">
          {children}
        </TableHead>
      ),
      td: ({ children, style }) => (
        <TableCell style={style} className="align-top whitespace-normal">
          {children}
        </TableCell>
      ),
    };
  }, [images, onWikiLinkClick, linkSuffix]);

  return (
    <div className="wiki-content min-w-0 text-foreground">
      {showToc && toc.length >= 3 && <TableOfContents items={toc} />}
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeRaw]}
        urlTransform={filterUrl}
        components={components}
      >
        {processed}
      </ReactMarkdown>
    </div>
  );
}
