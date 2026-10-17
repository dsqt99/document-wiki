"use client";

import { useRef, useState } from "react";
import { apiUpload } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { errMessage } from "./skill-utils";
import type { Skill } from "./types";

/** Replace every file of a skill with a new ZIP package (creates a new version). */
export function SkillReuploadDialog({
  skill,
  onClose,
  onUploaded,
}: {
  skill: Skill | null;
  onClose: () => void;
  onUploaded: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onFile = async (file: File | undefined) => {
    if (inputRef.current) inputRef.current.value = "";
    if (!file || !skill) return;
    if (!file.name.toLowerCase().endsWith(".zip")) {
      setError("Hãy chọn tệp .zip");
      return;
    }
    setError(null);
    setUploading(true);
    const fd = new FormData();
    fd.append("file", file);
    try {
      await apiUpload(`/api/skills/${encodeURIComponent(skill.slug)}/reupload`, fd);
      onUploaded();
      onClose();
    } catch (err) {
      setError(errMessage(err, "Tải lên thất bại"));
    } finally {
      setUploading(false);
    }
  };

  return (
    <Dialog
      open={!!skill}
      onOpenChange={(o) => {
        if (!o && !uploading) {
          setError(null);
          onClose();
        }
      }}
    >
      <DialogContent className="rounded-2xl sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="font-serif text-xl">Tải phiên bản mới</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col items-center gap-3 py-2 text-center">
          <div className="flex size-20 items-center justify-center rounded-full bg-primary/5 text-primary">
            <span className="material-symbols-outlined" style={{ fontSize: 40 }}>cloud_upload</span>
          </div>
          <p className="text-sm">
            Cập nhật <span className="font-bold text-primary">{skill?.name}</span>
          </p>
          <p className="text-xs text-muted-foreground">Tải gói ZIP mới để thay toàn bộ tệp hiện tại và tạo phiên bản mới.</p>
          {error && (
            <div className="flex w-full items-start gap-2 rounded-lg bg-destructive/10 px-3 py-2 text-left text-sm text-destructive">
              <span className="material-symbols-outlined" style={{ fontSize: 18 }}>error</span>
              <span>{error}</span>
            </div>
          )}
          <input
            ref={inputRef}
            type="file"
            accept=".zip"
            className="hidden"
            onChange={(e) => void onFile(e.target.files?.[0])}
          />
          <Button className="h-12 w-full" disabled={uploading} onClick={() => inputRef.current?.click()}>
            {uploading ? (
              <>
                <span className="material-symbols-outlined animate-spin" style={{ fontSize: 18 }}>progress_activity</span>
                Đang tải lên...
              </>
            ) : (
              <>
                <span className="material-symbols-outlined" style={{ fontSize: 18 }}>upload_file</span>
                Chọn gói ZIP
              </>
            )}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
