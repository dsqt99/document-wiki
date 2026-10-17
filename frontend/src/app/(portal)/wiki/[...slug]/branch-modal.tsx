"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";

export type WikiBranch = {
  id: string;
  name: string;
  description?: string | null;
  status?: string;
  scope_type?: string;
  scope_id?: string | null;
};

type Props = {
  open: boolean;
  onClose: () => void;
  scopeType: string;
  scopeId: string | null;
  onCreated: (branch: WikiBranch) => void;
};

/** Plain overlay modal for creating a contribution branch. */
export function BranchModal({ open, onClose, scopeType, scopeId, onCreated }: Props) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  const close = () => {
    setError(null);
    onClose();
  };

  const submit = async () => {
    const n = name.trim();
    if (!n || busy) return;
    setBusy(true);
    setError(null);
    try {
      const created = await api<WikiBranch>("/api/wiki/branches", {
        method: "POST",
        body: { name: n, description: description.trim(), scope_type: scopeType, scope_id: scopeId },
      });
      onCreated(created);
      setName("");
      setDescription("");
      onClose();
    } catch (e) {
      setError(e instanceof Error && e.message ? e.message : "Tạo nhánh thất bại");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onMouseDown={close}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="branch-modal-title"
        onMouseDown={(e) => e.stopPropagation()}
        className="w-full max-w-md rounded-xl border bg-background shadow-xl"
      >
        <div className="flex items-center justify-between border-b px-5 py-3">
          <h2 id="branch-modal-title" className="text-base font-semibold">
            Tạo nhánh đóng góp mới
          </h2>
          <button
            type="button"
            aria-label="Đóng"
            onClick={close}
            className="flex size-7 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <span className="material-symbols-outlined" style={{ fontSize: 18 }}>
              close
            </span>
          </button>
        </div>
        <div className="flex flex-col gap-4 px-5 py-4">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="branch-name" className="text-sm font-medium">
              Tên nhánh
            </label>
            <Input
              id="branch-name"
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Ví dụ: thay-doi-quy-che-lam-viec"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="branch-desc" className="text-sm font-medium">
              Mô tả (Không bắt buộc)
            </label>
            <textarea
              id="branch-desc"
              rows={3}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Mô tả tóm tắt nội dung đợt đóng góp này..."
              className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none focus:border-primary"
            />
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>
        <div className="flex justify-end gap-2 border-t px-5 py-3">
          <Button variant="outline" onClick={close} disabled={busy}>
            Hủy
          </Button>
          <Button onClick={submit} disabled={busy}>
            Tạo nhánh
          </Button>
        </div>
      </div>
    </div>
  );
}
