"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkFrontmatter from "remark-frontmatter";
import { cn } from "@/lib/utils";
import styles from "./skills.module.css";

/**
 * README-style markdown (GFM tables, task lists, strikethrough). A leading YAML front
 * matter block is parsed by remark-frontmatter and therefore never rendered.
 */
export function SkillMarkdown({
  content,
  variant = "detail",
  className,
}: {
  content: string;
  variant?: "detail" | "editor";
  className?: string;
}) {
  return (
    <div className={cn(styles.md, variant === "detail" ? styles.mdDetail : styles.mdEditor, className)}>
      <ReactMarkdown remarkPlugins={[remarkGfm, [remarkFrontmatter, ["yaml"]]]}>{content}</ReactMarkdown>
    </div>
  );
}

export const scrollCls = { thin: styles.thinScroll, none: styles.noScroll };
