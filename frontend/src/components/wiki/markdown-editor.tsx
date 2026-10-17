"use client";

import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { getTextareaCaretCoords, type CaretCoords } from "@/lib/textarea-caret";
import type { WikiPageSummary } from "@/types/wiki";
import { WikiContent } from "@/components/wiki/wiki-content";
import { WikilinkAutocomplete } from "@/components/wiki/wikilink-autocomplete";
import { loadWikiPages } from "@/components/wiki/wiki-pages-loader";
import { cn } from "@/lib/utils";

type MarkdownEditorProps = {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  /** Tailwind min-height class for the textarea; defaults to 400px. */
  minHeightClass?: string;
};

type Autocomplete = { start: number; query: string; caret: CaretCoords };

type ToolDef = { id: "bold" | "italic" | "code" | "h2" | "h3" | "ul" | "ol" | "quote" | "block" | "link" | "wiki" | "hr"; icon?: string; text?: string; tip: string };

const TOOLS: (ToolDef | "sep")[] = [
  { id: "bold", icon: "format_bold", tip: "Bold (Ctrl+B)" },
  { id: "italic", icon: "format_italic", tip: "Italic (Ctrl+I)" },
  { id: "code", icon: "code", tip: "Inline code" },
  "sep",
  { id: "h2", text: "H2", tip: "Heading 2" },
  { id: "h3", text: "H3", tip: "Heading 3" },
  "sep",
  { id: "ul", icon: "format_list_bulleted", tip: "Bullet list" },
  { id: "ol", icon: "format_list_numbered", tip: "Numbered list" },
  { id: "quote", icon: "format_quote", tip: "Blockquote" },
  "sep",
  { id: "block", icon: "data_object", tip: "Code block" },
  { id: "link", icon: "link", tip: "Link" },
  { id: "wiki", icon: "account_tree", tip: "Wikilink — type [[ to pick a page" },
  { id: "hr", icon: "horizontal_rule", tip: "Horizontal rule" },
];

/** Look back (≤80 chars) from the caret for an open "[[" on the same line. */
function detectWikilink(text: string, caret: number): { start: number; query: string } | null {
  const from = Math.max(0, caret - 80);
  for (let i = caret - 1; i >= from; i--) {
    const ch = text[i];
    if (ch === "\n" || ch === "]") return null;
    if (ch === "[" && i > 0 && text[i - 1] === "[") {
      return { start: i - 1, query: text.slice(i + 1, caret) };
    }
  }
  return null;
}

export function MarkdownEditor({
  value,
  onChange,
  placeholder = "Write markdown here...",
  minHeightClass = "min-h-[400px]",
}: MarkdownEditorProps) {
  const taRef = useRef<HTMLTextAreaElement>(null);
  const blurTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [tab, setTab] = useState<"edit" | "preview">("edit");
  const [pages, setPages] = useState<WikiPageSummary[]>([]);
  const [ac, setAc] = useState<Autocomplete | null>(null);

  useEffect(() => {
    let cancelled = false;
    loadWikiPages()
      .then((list) => {
        if (!cancelled) setPages(list);
      })
      .catch(() => {
        /* autocomplete simply has no suggestions */
      });
    return () => {
      cancelled = true;
      if (blurTimer.current) clearTimeout(blurTimer.current);
    };
  }, []);

  const refreshAutocomplete = (text?: string) => {
    const ta = taRef.current;
    if (!ta) return;
    const content = text ?? ta.value;
    const pos = ta.selectionStart ?? 0;
    if (ta.selectionEnd !== pos) {
      setAc(null);
      return;
    }
    const hit = detectWikilink(content, pos);
    if (!hit) {
      setAc(null);
      return;
    }
    setAc({ ...hit, caret: getTextareaCaretCoords(ta, pos) });
  };

  /** Replace [start, end) with `insert`, then select [selStart, selEnd) (absolute offsets). */
  const applyEdit = (start: number, end: number, insert: string, selStart: number, selEnd: number, thenDetect = false) => {
    const next = value.slice(0, start) + insert + value.slice(end);
    onChange(next);
    setTimeout(() => {
      const ta = taRef.current;
      if (!ta) return;
      ta.focus();
      ta.setSelectionRange(selStart, selEnd);
      if (thenDetect) refreshAutocomplete(next);
    }, 0);
  };

  const wrap = (marker: string, sample: string) => {
    const ta = taRef.current;
    if (!ta) return;
    const s = ta.selectionStart;
    const e = ta.selectionEnd;
    const inner = s !== e ? value.slice(s, e) : sample;
    applyEdit(s, e, `${marker}${inner}${marker}`, s + marker.length, s + marker.length + inner.length);
  };

  const prefixLine = (prefix: string) => {
    const ta = taRef.current;
    if (!ta) return;
    const s = ta.selectionStart;
    const e = ta.selectionEnd;
    const lineStart = value.lastIndexOf("\n", s - 1) + 1;
    applyEdit(lineStart, lineStart, prefix, s + prefix.length, e + prefix.length);
  };

  const insertCodeBlock = () => {
    const ta = taRef.current;
    if (!ta) return;
    const s = ta.selectionStart;
    const e = ta.selectionEnd;
    const selected = value.slice(s, e);
    const lead = s > 0 && value[s - 1] !== "\n" ? "\n" : "";
    const block = `${lead}\`\`\`\n${selected}\n\`\`\`\n`;
    const innerStart = s + lead.length + 4;
    applyEdit(s, e, block, innerStart, innerStart + selected.length);
  };

  const insertLink = () => {
    const ta = taRef.current;
    if (!ta) return;
    const s = ta.selectionStart;
    const e = ta.selectionEnd;
    const text = s !== e ? value.slice(s, e) : "link text";
    const md = `[${text}](url)`;
    const urlStart = s + text.length + 3;
    applyEdit(s, e, md, urlStart, urlStart + 3);
  };

  const insertWikilink = () => {
    const ta = taRef.current;
    if (!ta) return;
    const s = ta.selectionStart;
    const e = ta.selectionEnd;
    applyEdit(s, e, "[[", s + 2, s + 2, true);
  };

  const insertRule = () => {
    const ta = taRef.current;
    if (!ta) return;
    const s = ta.selectionStart;
    const e = ta.selectionEnd;
    const snippet = "\n\n---\n\n";
    applyEdit(s, e, snippet, s + snippet.length, s + snippet.length);
  };

  const pickPage = (page: WikiPageSummary) => {
    const ta = taRef.current;
    if (!ta || !ac) return;
    const pos = ta.selectionStart;
    const insert = `[[${page.slug}]]`;
    setAc(null);
    applyEdit(ac.start, pos, insert, ac.start + insert.length, ac.start + insert.length);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (!(e.ctrlKey || e.metaKey) || e.altKey) return;
    const k = e.key.toLowerCase();
    if (k === "b") {
      e.preventDefault();
      wrap("**", "bold text");
    } else if (k === "i") {
      e.preventDefault();
      wrap("*", "italic text");
    }
  };

  const runTool = (id: ToolDef["id"]) => {
    switch (id) {
      case "bold":
        return wrap("**", "bold text");
      case "italic":
        return wrap("*", "italic text");
      case "code":
        return wrap("`", "code");
      case "h2":
        return prefixLine("## ");
      case "h3":
        return prefixLine("### ");
      case "ul":
        return prefixLine("- ");
      case "ol":
        return prefixLine("1. ");
      case "quote":
        return prefixLine("> ");
      case "block":
        return insertCodeBlock();
      case "link":
        return insertLink();
      case "wiki":
        return insertWikilink();
      case "hr":
        return insertRule();
    }
  };

  return (
    <div className="overflow-hidden rounded-lg border bg-background">
      <div className="flex items-center gap-1 border-b px-2 pt-1.5">
        {(["edit", "preview"] as const).map((k) => (
          <button
            key={k}
            type="button"
            onClick={() => {
              setTab(k);
              setAc(null);
            }}
            className={cn(
              "-mb-px border-b-2 px-3 py-1.5 text-xs font-medium",
              tab === k ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            {k === "edit" ? "Edit" : "Preview"}
          </button>
        ))}
        <span className="ml-auto pr-1 text-[11px] text-muted-foreground">Markdown</span>
      </div>

      {tab === "edit" ? (
        <>
          <div className="flex flex-wrap items-center gap-0.5 border-b bg-muted/30 px-1.5 py-1">
            {TOOLS.map((tool, i) =>
              tool === "sep" ? (
                <span key={`sep-${i}`} className="mx-1 h-4 w-px bg-border" />
              ) : (
                <Tooltip key={tool.tip}>
                  <TooltipTrigger
                    render={
                      <button
                        type="button"
                        aria-label={tool.tip}
                        onMouseDown={(e) => e.preventDefault()}
                        onClick={() => runTool(tool.id)}
                        className="flex h-7 min-w-7 items-center justify-center rounded px-1 text-muted-foreground hover:bg-muted hover:text-foreground"
                      />
                    }
                  >
                    {tool.icon ? (
                      <span className="material-symbols-outlined" style={{ fontSize: 18 }}>
                        {tool.icon}
                      </span>
                    ) : (
                      <span className="text-xs font-bold">{tool.text}</span>
                    )}
                  </TooltipTrigger>
                  <TooltipContent>{tool.tip}</TooltipContent>
                </Tooltip>
              ),
            )}
          </div>
          <textarea
            ref={taRef}
            value={value}
            placeholder={placeholder}
            spellCheck={false}
            onChange={(e) => {
              onChange(e.target.value);
              refreshAutocomplete(e.target.value);
            }}
            onClick={() => refreshAutocomplete()}
            onKeyDown={onKeyDown}
            onKeyUp={(e) => {
              if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"].includes(e.key)) {
                refreshAutocomplete();
              }
            }}
            onBlur={() => {
              if (blurTimer.current) clearTimeout(blurTimer.current);
              blurTimer.current = setTimeout(() => setAc(null), 150);
            }}
            onFocus={() => {
              if (blurTimer.current) clearTimeout(blurTimer.current);
            }}
            className={cn(
              "block w-full resize-y bg-transparent px-3 py-2.5 font-mono text-[13px] leading-relaxed outline-none placeholder:text-muted-foreground",
              minHeightClass,
            )}
          />
          {ac && (
            <WikilinkAutocomplete
              pages={pages}
              query={ac.query}
              caret={ac.caret}
              onPick={pickPage}
              onClose={() => setAc(null)}
            />
          )}
        </>
      ) : (
        <div className={cn("overflow-auto px-4 py-3", minHeightClass)}>
          {value.trim() ? (
            <WikiContent markdown={value} />
          ) : (
            <p className="text-sm text-muted-foreground italic">Nothing to preview.</p>
          )}
        </div>
      )}
    </div>
  );
}
