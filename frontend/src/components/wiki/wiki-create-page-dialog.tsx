"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { MarkdownEditor } from "@/components/wiki/markdown-editor";
import { encodeSlugPath } from "@/components/wiki/wiki-pages-loader";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { WikiPageDetail, WikiScope } from "@/types/wiki";

type CreateMode = "direct" | "propose";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mode: CreateMode;
  defaultScope: WikiScope;
  scopes: WikiScope[];
  getCreateModeForScope?: (scopeType: string, scopeId: string | null) => CreateMode | null;
  defaultTitle?: string;
};

/**
 * Slug suggested from a title: lowercased, accents removed (with Vietnamese đ
 * mapped to d), every run of other characters turned into one "-", and no
 * leading or trailing dashes.
 */
const SLUG_STEPS: ReadonlyArray<readonly [RegExp, string]> = [
  [/[̀-ͯ]/g, ""],
  [/đ/g, "d"],
  [/[^a-z0-9]+/g, "-"],
  [/^-+|-+$/g, ""],
];

function autoSlug(title: string): string {
  const decomposed = title.toLowerCase().normalize("NFKD");
  return SLUG_STEPS.reduce((acc, [pattern, replacement]) => acc.replace(pattern, replacement), decomposed);
}

const scopeKey = (s: { scope_type: string; scope_id: string | null }) => `${s.scope_type}:${s.scope_id ?? ""}`;

const CONTENT_PLACEHOLDER =
  "# Overview\n\nDescribe the topic here. Use [[wikilinks]] to link to other pages.";

export function WikiCreatePageDialog(props: Props) {
  const { open, onOpenChange } = props;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-3xl">
        {/* The form only lives while the dialog is open, so every opening starts fresh. */}
        {open && <CreatePageForm {...props} />}
      </DialogContent>
    </Dialog>
  );
}

function CreatePageForm({ onOpenChange, mode, defaultScope, scopes, getCreateModeForScope, defaultTitle = "" }: Props) {
  const { t } = useI18n();
  const router = useRouter();
  const [title, setTitle] = useState(defaultTitle);
  const [slug, setSlug] = useState(() => autoSlug(defaultTitle));
  const [slugTouched, setSlugTouched] = useState(false);
  const [scope, setScope] = useState<WikiScope>(defaultScope);
  const [content, setContent] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const scopeOptions = useMemo(() => {
    const list = getCreateModeForScope
      ? scopes.filter((s) => getCreateModeForScope(s.scope_type, s.scope_id) !== null)
      : scopes;
    // keep the current scope selectable even if the caller did not list it
    if (!list.some((s) => scopeKey(s) === scopeKey(scope))) return [scope, ...list];
    return list;
  }, [scopes, getCreateModeForScope, scope]);

  const effectiveMode: CreateMode = getCreateModeForScope?.(scope.scope_type, scope.scope_id) ?? mode;
  const isPropose = effectiveMode === "propose";

  const scopeLabel = (s: WikiScope) => (s.scope_type === "global" ? s.name : `${s.name} (${s.scope_type})`);

  const submit = async () => {
    const tt = title.trim();
    const sl = slug.trim();
    if (!tt || !sl || !content.trim()) {
      setError("Title, slug, and content are required.");
      return;
    }
    setBusy(true);
    setError(null);
    const body = {
      slug: sl,
      title: tt,
      page_type: "concept",
      content_md: content,
      scope_type: scope.scope_type,
      scope_id: scope.scope_id,
      knowledge_type_slugs: [] as string[],
    };
    try {
      if (isPropose) {
        await api("/api/wiki/drafts/create", { method: "POST", body: { ...body, note: note.trim() || null } });
        onOpenChange(false);
        router.push(`/wiki/${encodeSlugPath(sl)}`);
      } else {
        const created = await api<WikiPageDetail>("/api/wiki/pages", { method: "POST", body });
        const finalSlug = created?.slug || sl;
        const qs =
          scope.scope_type !== "global"
            ? `?scopeType=${encodeURIComponent(scope.scope_type)}&scopeId=${encodeURIComponent(scope.scope_id ?? "")}`
            : "";
        onOpenChange(false);
        router.push(`/wiki/${encodeSlugPath(finalSlug)}${qs}`);
      }
    } catch (e) {
      setError(e instanceof Error && e.message ? e.message : "Submit failed");
      setBusy(false);
    }
  };

  return (
    <>
      <DialogHeader>
        <DialogTitle>
          {isPropose ? t("wiki.proposeTitle", "Đề xuất trang mới") : t("wiki.createTitle", "Tạo trang mới")}
        </DialogTitle>
        <DialogDescription>{isPropose ? t("wiki.proposeDesc") : t("wiki.createDesc")}</DialogDescription>
      </DialogHeader>

      <div className="grid gap-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="grid gap-1.5">
            <label className="text-sm font-medium" htmlFor="wiki-new-title">
              {t("wiki.pageTitle")}
            </label>
            <Input
              id="wiki-new-title"
              autoFocus
              value={title}
              placeholder="e.g. Fire Safety Procedure"
              onChange={(e) => {
                setTitle(e.target.value);
                if (!slugTouched) setSlug(autoSlug(e.target.value));
              }}
            />
          </div>
          <div className="grid gap-1.5">
            <label className="text-sm font-medium" htmlFor="wiki-new-slug">
              {t("wiki.slugLabel")}
            </label>
            <Input
              id="wiki-new-slug"
              className="font-mono"
              value={slug}
              placeholder="fire-safety-procedure"
              onChange={(e) => {
                setSlug(e.target.value);
                setSlugTouched(true);
              }}
            />
          </div>
        </div>

        <div className="grid gap-1.5">
          <span className="text-sm font-medium">{t("wiki.scopeLabel")}</span>
          <Select
            value={scopeKey(scope)}
            onValueChange={(v) => {
              const found = scopeOptions.find((s) => scopeKey(s) === v);
              if (found) setScope(found);
            }}
          >
            <SelectTrigger className="w-full">
              <SelectValue>{() => scopeLabel(scope)}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              {scopeOptions.map((s) => (
                <SelectItem key={scopeKey(s)} value={scopeKey(s)}>
                  {scopeLabel(s)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="grid gap-1.5">
          <span className="text-sm font-medium">{t("wiki.contentLabel")}</span>
          <MarkdownEditor
            value={content}
            onChange={setContent}
            placeholder={CONTENT_PLACEHOLDER}
            minHeightClass="min-h-[280px]"
          />
        </div>

        {isPropose ? (
          <div className="grid gap-1.5">
            <label htmlFor="wiki-new-note" className="text-sm font-medium">
              {t("wiki.noteForReviewer")}
            </label>
            <Input
              id="wiki-new-note"
              placeholder={t("wiki.notePlaceholder")}
              onChange={(event) => setNote(event.target.value)}
              value={note}
            />
          </div>
        ) : null}

        {error ? <p className="text-sm text-destructive">{error}</p> : null}
      </div>

      <DialogFooter>
        <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
          {t("common.cancel", "Hủy")}
        </Button>
        <Button onClick={submit} disabled={busy}>
          <span className={busy ? "material-symbols-outlined animate-spin" : "material-symbols-outlined"} style={{ fontSize: 16 }}>
            {busy ? "progress_activity" : isPropose ? "send" : "add"}
          </span>
          {isPropose ? t("wiki.submitProposalBtn") : t("wiki.createPageBtn")}
        </Button>
      </DialogFooter>
    </>
  );
}
