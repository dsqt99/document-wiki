"use client";

/* Markdown editor plus an optional change note, with Save / Cancel actions. */
import { useState } from "react";
import { MarkdownEditor } from "@/components/wiki/markdown-editor";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

const DEFAULT_NOTE_PLACEHOLDER = "Optional — describe what you changed";

export interface WikiEditorProps {
  /** Markdown shown when the editor first mounts. */
  initialContent: string;
  /** Persist the edit; a rejected promise surfaces its message inline. */
  onSave: (content: string, note: string) => Promise<void>;
  onCancel: () => void;
  saveLabel: string;
  noteLabel: string;
  notePlaceholder?: string;
}

export function WikiEditor(props: WikiEditorProps) {
  const { initialContent, onSave, onCancel, saveLabel, noteLabel } = props;
  const notePlaceholder = props.notePlaceholder ?? DEFAULT_NOTE_PLACEHOLDER;
  const [content, setContent] = useState(initialContent);
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    if (!content.trim() || saving) return;
    setSaving(true);
    setError(null);
    try {
      await onSave(content, note);
    } catch (e) {
      setError(e instanceof Error && e.message ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <MarkdownEditor value={content} onChange={setContent} />
      <div className="flex flex-col gap-1.5">
        <label htmlFor="wiki-editor-note" className="text-sm font-medium">
          {noteLabel}
        </label>
        <Input
          id="wiki-editor-note"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder={notePlaceholder}
        />
      </div>
      {error && <p className="text-sm text-destructive">{error}</p>}
      <div className="flex items-center justify-end gap-2">
        <Button variant="outline" onClick={onCancel} disabled={saving}>
          Cancel
        </Button>
        <Button onClick={save} disabled={!content.trim() || saving}>
          {saving ? (
            <>
              <span className="material-symbols-outlined animate-spin" style={{ fontSize: 16 }}>
                progress_activity
              </span>
              Saving…
            </>
          ) : (
            <>
              <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
                save
              </span>
              {saveLabel}
            </>
          )}
        </Button>
      </div>
    </div>
  );
}
