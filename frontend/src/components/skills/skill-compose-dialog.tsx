"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ScopePicker, type ScopeMode } from "@/components/knowledge/scope-picker";
import { errMessage, toSkillName, trimTrailingDash } from "./skill-utils";
import type { Department, SkillContent } from "./types";

export { toSkillName };

/** Starter body offered for a brand new SKILL.md. */
export const SKILL_TEMPLATE = `# Mục đích
Kỹ năng này giúp trợ lý làm việc gì, cho ai.

# Khi nào dùng
Liệt kê các tình huống, câu hỏi hoặc loại văn bản cần áp dụng kỹ năng.

# Cách làm
1. Tra cứu kho tri thức để lấy căn cứ (văn bản, quy định liên quan).
2. Phân tích yêu cầu và đối chiếu với căn cứ.
3. Soạn câu trả lời theo định dạng bên dưới.

# Định dạng trả lời
Trả lời bằng tiếng Việt, ngắn gọn, nêu rõ căn cứ văn bản đã dùng.
`;

const NAME_RE = /^[a-z0-9][a-z0-9-]{1,79}$/;

type ComposeResult = { status?: string; message?: string };

export type SkillComposeInitial = Partial<Pick<SkillContent, "name" | "description" | "body">>;

/**
 * Quick single-file editor for SKILL.md. Create mode posts to /api/skills/compose; edit mode
 * loads and replaces the content of an existing skill. Mount with a fresh `key` each time it
 * opens so the form starts clean.
 */
export function SkillComposeDialog({
  open,
  onOpenChange,
  mode,
  slug,
  initial,
  departments,
  onSaved,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mode: "create" | "edit";
  slug?: string | null;
  initial?: SkillComposeInitial | null;
  departments: Department[];
  onSaved: (message: string) => void;
}) {
  const isEdit = mode === "edit";
  const [name, setName] = useState(isEdit ? "" : toSkillName(initial?.name ?? ""));
  const [description, setDescription] = useState(isEdit ? "" : (initial?.description ?? ""));
  const [body, setBody] = useState(isEdit ? "" : initial?.body || SKILL_TEMPLATE);
  const [scope, setScope] = useState<ScopeMode>("global");
  const [deptIds, setDeptIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(isEdit && !!slug);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Edit mode: fetch the current content when the dialog opens.
  useEffect(() => {
    if (!isEdit || !slug || !open) return;
    let alive = true;
    api<SkillContent>(`/api/skills/${encodeURIComponent(slug)}/content`)
      .then((c) => {
        if (!alive) return;
        setName(c.name ?? "");
        setDescription(c.description ?? "");
        setBody(c.body ?? "");
      })
      .catch((err) => alive && setError(errMessage(err, "Không tải được nội dung kỹ năng")))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [isEdit, slug, open]);

  const finalName = trimTrailingDash(name);
  const valid =
    NAME_RE.test(finalName) &&
    description.trim().length > 0 &&
    (isEdit || scope !== "department" || deptIds.length > 0);

  const save = async () => {
    if (!valid || saving || loading) return;
    setSaving(true);
    setError(null);
    try {
      let message: string;
      if (isEdit && slug) {
        const res = await api<ComposeResult>(`/api/skills/${encodeURIComponent(slug)}/content`, {
          method: "PUT",
          body: { description, body },
        });
        message =
          res?.status === "skipped"
            ? "Nội dung không đổi"
            : res?.status === "contribution_pending"
              ? "Đã gửi bản sửa, chờ duyệt"
              : "Đã lưu — đang tạo phiên bản mới";
      } else {
        const isDept = scope === "department";
        const res = await api<{ results?: ComposeResult[] }>("/api/skills/compose", {
          method: "POST",
          body: {
            name: finalName,
            description,
            body,
            scope_type: isDept ? "department" : "global",
            department_ids: isDept ? deptIds : [],
          },
        });
        const first = res?.results?.[0];
        if (first?.status === "error" || first?.status === "rejected") {
          setError(first.message || "Kho từ chối kỹ năng");
          return;
        }
        message =
          first?.status === "contribution_pending" ? "Đã gửi đề xuất kỹ năng, chờ duyệt" : `Đã tạo kỹ năng ${finalName}`;
      }
      onSaved(message);
      onOpenChange(false);
    } catch (err) {
      setError(errMessage(err, "Lưu thất bại"));
    } finally {
      setSaving(false);
    }
  };

  const labelCls = "pt-2 text-xs text-muted-foreground sm:pt-2.5";

  return (
    <Dialog open={open} onOpenChange={(o) => !saving && onOpenChange(o)}>
      <DialogContent className="flex max-h-[92vh] flex-col gap-0 overflow-hidden p-0 sm:max-w-3xl">
        <DialogHeader className="border-b px-5 py-4">
          <DialogTitle className="text-lg">{isEdit ? `Sửa kỹ năng ${name}` : "Tạo kỹ năng"}</DialogTitle>
          <DialogDescription className="text-xs">
            {isEdit
              ? "Lưu sẽ tạo phiên bản mới; các tệp đính kèm khác của kỹ năng được giữ nguyên."
              : "Kỹ năng là bộ hướng dẫn trợ lý AI đọc khi gặp đúng loại yêu cầu (gói SKILL.md)."}
          </DialogDescription>
        </DialogHeader>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          {loading ? (
            <div className="flex justify-center py-16">
              <span className="material-symbols-outlined animate-spin text-muted-foreground" style={{ fontSize: 32 }}>
                progress_activity
              </span>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="grid gap-x-4 gap-y-3 sm:grid-cols-[120px_1fr]">
                <label htmlFor="compose-name" className={labelCls}>Tên kỹ năng</label>
                <div className="space-y-1">
                  <Input
                    id="compose-name"
                    value={name}
                    onChange={(e) => setName(toSkillName(e.target.value))}
                    placeholder="vd: tom-tat-bien-ban"
                    disabled={isEdit || saving}
                    className="h-9 font-mono"
                  />
                  {!isEdit && (
                    <p className="text-[11px] text-muted-foreground">
                      Chữ thường không dấu, số và “-”. Trợ lý gọi kỹ năng bằng tên này.
                    </p>
                  )}
                </div>

                <label htmlFor="compose-desc" className={labelCls}>Khi nào dùng</label>
                <div className="space-y-1">
                  <Textarea
                    id="compose-desc"
                    rows={2}
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="vd: Dùng khi cán bộ cần tóm tắt biên bản, nêu người, việc, thời hạn."
                    disabled={saving}
                    className="field-sizing-fixed resize-none"
                  />
                  <p className="text-[11px] text-muted-foreground">
                    Trợ lý dựa vào mô tả này để chọn kỹ năng — viết rõ tình huống áp dụng.
                  </p>
                </div>

                {!isEdit && (
                  <>
                    <span className={labelCls}>Phạm vi</span>
                    <ScopePicker
                      mode={scope}
                      onModeChange={setScope}
                      departments={departments}
                      selected={deptIds}
                      onSelectedChange={setDeptIds}
                      disabled={saving}
                    />
                  </>
                )}
              </div>

              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <label htmlFor="compose-body" className="text-xs text-muted-foreground">Hướng dẫn (Markdown)</label>
                  {body.trim() === "" && (
                    <button
                      type="button"
                      className="text-xs font-medium text-primary hover:underline"
                      onClick={() => setBody(SKILL_TEMPLATE)}
                    >
                      Chèn khung mẫu
                    </button>
                  )}
                </div>
                <Textarea
                  id="compose-body"
                  value={body}
                  onChange={(e) => setBody(e.target.value)}
                  disabled={saving}
                  className="min-h-72 font-mono text-[13px]! leading-relaxed"
                />
              </div>

              {error && <p className="text-xs text-destructive">{error}</p>}
            </div>
          )}
        </div>

        <div className={cn("flex justify-end gap-2 border-t bg-muted/50 px-5 py-3")}>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={saving}>Hủy</Button>
          <Button onClick={save} disabled={!valid || saving || loading}>
            <span className={cn("material-symbols-outlined", saving && "animate-spin")} style={{ fontSize: 16 }}>
              {saving ? "progress_activity" : "save"}
            </span>
            {isEdit ? "Lưu phiên bản mới" : "Tạo kỹ năng"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
