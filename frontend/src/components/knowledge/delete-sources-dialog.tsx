"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { deletionImpact, type ImpactPage } from "@/lib/source-workflow";
import { errorText, type Source } from "./types";

export function DeleteSourcesDialog({ sources, onClose, onDeleted }: {
  sources: Source[];
  onClose: () => void;
  onDeleted: () => void;
}) {
  const [pages, setPages] = useState<ImpactPage[] | null>(null);
  const [deleted, setDeleted] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    let active = true;
    Promise.all(sources.map((source) => api<{ pages: ImpactPage[] }>(`/api/sources/${source.id}/delete-impact`)))
      .then((results) => { if (active) { setPages(results.flatMap((result) => result.pages)); setError(null); } })
      .catch((err) => { if (active) setError(errorText(err, "Không kiểm tra được ảnh hưởng khi xóa")); });
    return () => { active = false; };
  }, [sources, reload]);
  const impact = deletionImpact(pages ?? [], sources.map((source) => source.id));

  const remove = async () => {
    setBusy(true);
    setError(null);
    const failures: string[] = [];
    const completed = new Set(deleted);
    for (const source of sources) {
      if (completed.has(source.id)) continue;
      try {
        await api(`/api/sources/${source.id}`, { method: "DELETE" });
        completed.add(source.id);
      } catch (err) { failures.push(`${source.title}: ${errorText(err, "Không xóa được")}`); }
    }
    setDeleted(completed);
    setBusy(false);
    if (failures.length) setError(failures.join("\n"));
    else onDeleted();
  };
  const close = () => { if (deleted.size) onDeleted(); else onClose(); };
  return (
    <Dialog open onOpenChange={(open) => { if (!open && !busy) close(); }}>
      <DialogContent className="sm:max-w-xl">
        <DialogTitle>Xóa {sources.length === 1 ? "tài liệu" : `${sources.length} tài liệu`}</DialogTitle>
        <DialogDescription>Tệp gốc, nội dung trích xuất và chỉ mục của tài liệu sẽ bị xóa vĩnh viễn. Thao tác không thể hoàn tác.</DialogDescription>
        <ul className="max-h-28 overflow-y-auto rounded-lg border p-3 text-sm">
          {sources.map((source) => <li key={source.id} className="truncate py-1" title={source.file_name || source.title}>{deleted.has(source.id) ? "Đã xóa · " : ""}{source.title || source.file_name}</li>)}
        </ul>
        {pages ? (
          <div className="space-y-2 text-sm">
            <p><strong className="text-destructive">{impact.removed.length} trang Wiki bị xóa theo</strong> vì không còn nguồn tài liệu khác.</p>
            {impact.removed.length > 0 && <ul className="max-h-32 list-disc overflow-y-auto pl-5 text-xs text-muted-foreground">{impact.removed.map((page, i) => <li key={i}>{page.title}</li>)}</ul>}
            <p>{impact.retained.length} trang dùng chung được giữ lại và gỡ liên kết với tài liệu đã xóa.</p>
          </div>
        ) : !error ? <p className="text-sm text-muted-foreground" role="status">Đang kiểm tra các trang Wiki liên quan…</p> : null}
        {error && <div role="alert" className="whitespace-pre-wrap text-sm text-destructive">{error}{!pages && <Button variant="outline" size="sm" className="ml-2" onClick={() => setReload((n) => n + 1)}>Kiểm tra lại</Button>}</div>}
        <div className="flex justify-end gap-2">
          <Button variant="outline" disabled={busy} onClick={close}>Hủy</Button>
          <Button variant="destructive" disabled={busy || !pages} onClick={() => void remove()}>{busy ? "Đang xóa…" : deleted.size ? "Thử xóa các tệp còn lại" : "Xóa vĩnh viễn"}</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
