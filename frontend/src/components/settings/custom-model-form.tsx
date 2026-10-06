"use client";

import { useState } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";

export type CustomModelKind = "llm" | "vision" | "embedding" | "ocr";

const EMBEDDING_DIMENSIONS = [768, 1024, 1536, 3072];

type SavedModel = { id: string };

/**
 * "Thêm model" form shared by the LLM, Vision, Embedding and OCR cards:
 * base URL + model name (+ optional label / API key), saved server-side as a
 * custom model of the given kind.
 */
export function CustomModelForm({
  kind,
  onSaved,
  onCancel,
}: {
  kind: CustomModelKind;
  onSaved: (id: string) => void;
  onCancel: () => void;
}) {
  const [label, setLabel] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [modelId, setModelId] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [protocol, setProtocol] = useState("openai");
  const [dimension, setDimension] = useState(1024);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const canSave = baseUrl.trim().length > 0 && modelId.trim().length > 0;

  async function handleSave() {
    setSaving(true);
    setError("");
    try {
      const saved = await api<SavedModel>("/api/settings/custom-models", {
        method: "POST",
        body: {
          kind,
          label: label.trim() || undefined,
          base_url: baseUrl.trim(),
          model_id: modelId.trim(),
          api_key: apiKey.trim() || undefined,
          protocol,
          dimension: kind === "embedding" ? dimension : undefined,
        },
      });
      onSaved(saved.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Lưu model thất bại");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mb-4 rounded-lg border border-dashed border-primary/40 bg-primary/5 p-3 flex flex-col gap-3">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="flex flex-col gap-1.5 sm:col-span-2">
          <Label className="text-xs">Base URL *</Label>
          <Input
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder={protocol === "anthropic" ? "https://api.anthropic.com" : "https://api.example.com/v1"}
            className="bg-background font-mono text-xs"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label className="text-xs">Model name *</Label>
          <Input
            value={modelId}
            onChange={(e) => setModelId(e.target.value)}
            placeholder="vd: qwen3-32b"
            maxLength={100}
            className="bg-background font-mono text-xs"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label className="text-xs">Tên hiển thị</Label>
          <Input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="Mặc định = model name"
            className="bg-background text-xs"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label className="text-xs">API key</Label>
          <Input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="Bỏ trống nếu endpoint không cần key"
            className="bg-background text-xs"
          />
        </div>
        {kind === "llm" && (
          <div className="flex flex-col gap-1.5">
            <Label className="text-xs">Giao thức</Label>
            <select
              value={protocol}
              onChange={(e) => setProtocol(e.target.value)}
              className="h-9 rounded-md border border-input bg-background px-2 text-xs"
            >
              <option value="openai">OpenAI-compatible</option>
              <option value="anthropic">Anthropic Messages</option>
            </select>
          </div>
        )}
        {kind === "embedding" && (
          <div className="flex flex-col gap-1.5">
            <Label className="text-xs">Số chiều vector *</Label>
            <select
              value={dimension}
              onChange={(e) => setDimension(Number(e.target.value))}
              className="h-9 rounded-md border border-input bg-background px-2 text-xs"
            >
              {EMBEDDING_DIMENSIONS.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>
      {kind !== "llm" && (
        <p className="text-[11px] text-muted-foreground">
          Endpoint phải tương thích OpenAI API
          {kind === "embedding" && " và trả về vector đúng số chiều đã chọn"}.
        </p>
      )}
      <div className="flex items-center gap-2">
        <button
          disabled={!canSave || saving}
          onClick={handleSave}
          className="bg-primary text-primary-foreground px-3 py-1.5 rounded-lg text-xs font-medium hover:bg-primary/90 disabled:opacity-50"
        >
          {saving ? "Đang lưu…" : "Lưu model"}
        </button>
        <button
          onClick={onCancel}
          className="border border-border px-3 py-1.5 rounded-lg text-xs font-medium hover:bg-muted"
        >
          Hủy
        </button>
        {error && <p className="text-xs text-destructive">{error}</p>}
      </div>
    </div>
  );
}

export async function deleteCustomModel(kind: CustomModelKind, id: string) {
  const qs = new URLSearchParams({ kind, id });
  await api(`/api/settings/custom-models?${qs}`, { method: "DELETE" });
}

/** Replace the API key of an existing custom model (other fields unchanged). */
export async function saveCustomModelKey(
  kind: CustomModelKind,
  spec: { model_id: string; label: string; base_url?: string | null; protocol?: string | null; dimension?: number },
  apiKey: string,
) {
  await api("/api/settings/custom-models", {
    method: "POST",
    body: {
      kind,
      model_id: spec.model_id,
      label: spec.label,
      base_url: spec.base_url,
      protocol: spec.protocol ?? "openai",
      dimension: kind === "embedding" ? spec.dimension : undefined,
      api_key: apiKey,
    },
  });
}
