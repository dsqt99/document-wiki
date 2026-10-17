"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ScopePicker, type ScopeMode } from "@/components/knowledge/scope-picker";
import { errMessage, toSkillName, trimTrailingDash } from "@/components/skills/skill-utils";

export type PromptTemplate = {
  id: string;
  title: string;
  command: string;
  description: string | null;
  content: string;
  tags: string[];
  scope_type: ScopeMode;
  department_ids: string[];
  department_names: string[];
  owner_id: string | null;
  owner_name: string | null;
  source: string;
  can_edit: boolean;
  updated_at: string;
};

export type PromptInitial = Partial<
  Pick<PromptTemplate, "title" | "command" | "description" | "content" | "tags" | "scope_type" | "department_ids">
>;

const VARIABLES = ["{{nội_dung}}", "{{CLIPBOARD}}", "{{CURRENT_DATE}}"];
const COMMAND_RE = /^[a-z0-9][a-z0-9_-]{0,99}$/;

/** Like the skill-name normaliser, but "_" survives (commands may use it). */
function normalizeCommand(input: string): string {
  return input
    .replace(/đ/g, "d")
    .replace(/Đ/g, "D")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "-")
    .replace(/-{2,}/g, "-")
    .replace(/^-+/, "")
    .slice(0, 100);
}

const labelCls = "text-sm font-medium sm:pt-2";

/**
 * Create / edit a prompt template. Mount with a fresh `key` each time it opens so the form
 * starts from `prompt` (edit), `initial` (prefilled create) or blank.
 */
export function PromptDialog({
  open,
  onOpenChange,
  prompt,
  initial,
  departments,
  onSaved,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  prompt?: PromptTemplate | null;
  initial?: PromptInitial | null;
  departments: { id: string; name: string }[];
  onSaved: (saved: PromptTemplate) => void;
}) {
  const src: PromptInitial = prompt ?? initial ?? {};
  const isEdit = !!prompt;

  const [title, setTitle] = useState(src.title ?? "");
  const [command, setCommand] = useState(src.command ?? "");
  const [commandTouched, setCommandTouched] = useState(!!src.command);
  const [description, setDescription] = useState(src.description ?? "");
  const [content, setContent] = useState(src.content ?? "");
  const [tags, setTags] = useState((src.tags ?? []).join(", "));
  const [scope, setScope] = useState<ScopeMode>(src.scope_type ?? "personal");
  const [deptIds, setDeptIds] = useState<string[]>(src.department_ids ?? []);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const finalCommand = trimTrailingDash(command);
  const valid =
    title.trim().length > 0 &&
    COMMAND_RE.test(finalCommand) &&
    content.trim().length > 0 &&
    (scope !== "department" || deptIds.length > 0);

  const onTitle = (v: string) => {
    setTitle(v);
    if (!commandTouched) setCommand(toSkillName(v).slice(0, 60));
  };

  const insertVar = (v: string) =>
    setContent((c) => (c.length === 0 || /\s$/.test(c) ? `${c}${v}` : `${c} ${v}`));

  const save = async () => {
    if (!valid || saving) return;
    setSaving(true);
    setError(null);
    const body = {
      title: title.trim(),
      command: finalCommand,
      description: description.trim(),
      content,
      tags: tags
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean),
      scope_type: scope,
      department_ids: scope === "department" ? deptIds : [],
    };
    try {
      const saved = isEdit
        ? await api<PromptTemplate>(`/api/prompts/${prompt!.id}`, { method: "PATCH", body })
        : await api<PromptTemplate>("/api/prompts", { method: "POST", body });
      onSaved(saved);
      onOpenChange(false);
    } catch (err) {
      setError(errMessage(err, "Lưu thất bại"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !saving && onOpenChange(o)}>
      <DialogContent className="flex max-h-[92vh] flex-col gap-0 p-0 sm:max-w-2xl">
        <DialogHeader className="shrink-0 border-b px-5 py-4">
          <DialogTitle>{isEdit ? "Sửa prompt" : "Tạo prompt"}</DialogTitle>
          <DialogDescription>
            Mẫu yêu cầu dùng lại trong chatbot: gõ <span className="font-mono">/lệnh</span> để chèn nội dung.
          </DialogDescription>
        </DialogHeader>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          <div className="grid grid-cols-1 gap-x-4 gap-y-3 sm:grid-cols-[120px_1fr]">
            <label htmlFor="prompt-title" className={labelCls}>Tiêu đề</label>
            <Input
              id="prompt-title"
              className="h-9"
              value={title}
              onChange={(e) => onTitle(e.target.value)}
              placeholder="vd: Tóm tắt văn bản chỉ đạo"
              disabled={saving}
            />

            <label htmlFor="prompt-command" className={labelCls}>Lệnh</label>
            <div className="flex h-9 items-center rounded-lg border border-input px-2.5 focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/50">
              <span className="font-mono text-sm text-muted-foreground">/</span>
              <input
                id="prompt-command"
                className="h-full min-w-0 flex-1 bg-transparent px-1 font-mono text-sm outline-none placeholder:text-muted-foreground"
                value={command}
                onChange={(e) => {
                  setCommandTouched(true);
                  setCommand(normalizeCommand(e.target.value));
                }}
                placeholder="tom-tat-van-ban"
                disabled={saving}
              />
            </div>

            <label htmlFor="prompt-desc" className={labelCls}>Mô tả</label>
            <Input
              id="prompt-desc"
              className="h-9"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Dùng khi nào (không bắt buộc)"
              disabled={saving}
            />

            <label htmlFor="prompt-tags" className={labelCls}>Nhãn</label>
            <Input
              id="prompt-tags"
              className="h-9"
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              placeholder="vd: văn bản, tổng hợp (cách nhau bởi dấu phẩy)"
              disabled={saving}
            />

            <span className={labelCls}>Phạm vi</span>
            <ScopePicker
              mode={scope}
              onModeChange={setScope}
              departments={departments}
              selected={deptIds}
              onSelectedChange={setDeptIds}
              disabled={saving}
              allowPersonal
            />
          </div>

          <div className="mt-4 flex flex-col gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <label htmlFor="prompt-content" className="text-sm font-medium">Nội dung</label>
              <div className="ml-auto flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                Chèn biến:
                {VARIABLES.map((v) => (
                  <button
                    key={v}
                    type="button"
                    disabled={saving}
                    onClick={() => insertVar(v)}
                    className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px] text-foreground transition-colors hover:bg-muted/70"
                  >
                    {v}
                  </button>
                ))}
              </div>
            </div>
            <Textarea
              id="prompt-content"
              className="min-h-56"
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder={"Tóm tắt văn bản sau thành 5 ý chính, mỗi ý một dòng, nêu rõ cơ quan và thời hạn nếu có:\n\n{{nội_dung}}"}
              disabled={saving}
            />
            <p className="text-xs text-muted-foreground">
              Biến {"{{tên}}"} sẽ được hỏi khi người dùng chọn prompt trong chatbot.
            </p>
          </div>

          {error && <p className="mt-3 text-xs text-destructive">{error}</p>}
        </div>

        <div className="flex shrink-0 justify-end gap-2 border-t px-5 py-3">
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={saving}>
            Hủy
          </Button>
          <Button onClick={() => void save()} disabled={!valid || saving}>
            <span className={saving ? "material-symbols-outlined animate-spin" : "material-symbols-outlined"} style={{ fontSize: 16 }}>
              {saving ? "progress_activity" : "save"}
            </span>
            {isEdit ? "Lưu" : "Tạo prompt"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
