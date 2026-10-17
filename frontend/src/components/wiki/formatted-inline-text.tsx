"use client";

import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";

/**
 * Tidy simple HTML tags that arrive with stray whitespace, e.g. "< mark >" or "< / Mark >",
 * into canonical lowercase tags, then trim.
 */
export function normalizeMarkup(text: string): string {
  if (!text) return "";
  return text
    .replace(/<\s*(\/?)\s*([a-zA-Z][a-zA-Z0-9]*)\s*>/g, (_m, slash: string, name: string) => `<${slash}${name.toLowerCase()}>`)
    .trim();
}

function hasFormatting(text: string): boolean {
  if (text.includes("**") || text.includes("*") || text.includes("__")) return true;
  if (/<\/?mark>/.test(text)) return true;
  return text.includes("<") && text.includes(">");
}

const inlineComponents: Components = {
  p: ({ children }) => <>{children}</>,
  mark: ({ children }) => <mark className="rounded-sm bg-amber-200/70 px-0.5 text-inherit dark:bg-amber-500/30">{children}</mark>,
  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
};

/** Renders a title / snippet that may carry search highlight markup (<mark>, **bold**, *italic*). */
export function FormattedInlineText({ text, className }: { text?: string | null; className?: string }) {
  if (!text) return null;
  const normalized = normalizeMarkup(text);
  if (!hasFormatting(normalized)) return <span className={className}>{text}</span>;
  return (
    <span className={["inline-block", className].filter(Boolean).join(" ")}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]} components={inlineComponents}>
        {normalized}
      </ReactMarkdown>
    </span>
  );
}
