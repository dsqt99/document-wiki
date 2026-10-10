"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";

export type CustomModelKind = "llm" | "vision" | "embedding" | "ocr";

/** Provider groups shown in Settings; "custom" = own base URL + API key. */
export type ProviderGroup = "anthropic" | "openai" | "google" | "custom";

export const PROVIDER_LABELS: Record<ProviderGroup, string> = {
  anthropic: "Anthropic",
  openai: "OpenAI",
  google: "Gemini",
  custom: "Custom",
};

const EMBEDDING_DIMENSIONS = [768, 1024, 1536, 3072];

type SavedModel = { id: string };

type Suggestion = { id: string; dim?: number; hint?: string };

/** Well-known embedding models per provider (dim = native output size). */
const EMBEDDING_SUGGESTIONS: Record<ProviderGroup, Suggestion[]> = {
  anthropic: [],
  openai: [
    { id: "text-embedding-3-small", dim: 1536 },
    { id: "text-embedding-3-large", dim: 3072 },
    { id: "text-embedding-ada-002", dim: 1536, hint: "thế hệ cũ" },
  ],
  google: [
    { id: "gemini-embedding-001", dim: 3072 },
    { id: "gemini-embedding-2", dim: 3072 },
    { id: "text-embedding-004", dim: 768 },
  ],
  // Common models served by vLLM / TEI / Ollama.
  custom: [
    { id: "BAAI/bge-m3", dim: 1024, hint: "đa ngôn ngữ, tốt cho tiếng Việt" },
    { id: "Qwen/Qwen3-Embedding-0.6B", dim: 1024 },
    { id: "intfloat/multilingual-e5-large", dim: 1024 },
    { id: "intfloat/multilingual-e5-base", dim: 768 },
    { id: "AITeamVN/Vietnamese_Embedding", dim: 1024, hint: "tiếng Việt" },
    { id: "dangvantuan/vietnamese-embedding", dim: 768, hint: "tiếng Việt" },
    { id: "nomic-embed-text", dim: 768, hint: "Ollama" },
  ],
};

const MANUAL = "__manual__";

/**
 * "Thêm model" form shared by the LLM, Vision, Embedding and OCR cards.
 * Under a known provider only the model name is needed (endpoint and API key
 * come from that provider); "custom" also asks for base URL and API key.
 */
export function CustomModelForm({
  kind,
  provider = "custom",
  existingModelIds = [],
  onSaved,
  onCancel,
}: {
  kind: CustomModelKind;
  provider?: ProviderGroup;
  /** Model ids already listed under this provider (hidden from the dropdown). */
  existingModelIds?: string[];
  onSaved: (id: string) => void;
  onCancel: () => void;
}) {
  const isCustom = provider === "custom";
  const [label, setLabel] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [modelId, setModelId] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [protocol, setProtocol] = useState("openai");
  const [dimension, setDimension] = useState(1024);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  // Models reported by the endpoint (GET /models); null = not loaded yet.
  const [discovered, setDiscovered] = useState<string[] | null>(null);
  const [discovering, setDiscovering] = useState(false);
  const [manual, setManual] = useState(false);
  const [probe, setProbe] = useState<{ busy: boolean; ok: boolean; text: string } | null>(null);

  const known = (kind === "embedding" ? EMBEDDING_SUGGESTIONS[provider] : []).filter(
    (o) => !existingModelIds.includes(o.id),
  );
  const fromEndpoint = (discovered ?? []).filter(
    (id) => !existingModelIds.includes(id) && !known.some((k) => k.id === id),
  );
  const showSelect = known.length + fromEndpoint.length > 0 && !manual;
  const canReachEndpoint = !isCustom || /^https?:\/\//.test(baseUrl.trim());

  function pickModel(id: string) {
    setProbe(null);
    if (id === MANUAL) {
      setManual(true);
      setModelId("");
      return;
    }
    setModelId(id);
    const dim = known.find((o) => o.id === id)?.dim;
    if (dim && EMBEDDING_DIMENSIONS.includes(dim)) setDimension(dim);
  }

  function endpointBody() {
    return {
      provider,
      base_url: isCustom ? baseUrl.trim() : undefined,
      api_key: (isCustom && apiKey.trim()) || undefined,
    };
  }

  async function handleDiscover() {
    setDiscovering(true);
    setError("");
    try {
      const res = await api<{ models: string[] }>("/api/settings/models/discover", {
        method: "POST",
        body: { kind, ...endpointBody() },
      });
      setDiscovered(res.models);
      setManual(false);
      if (res.models.length === 0) setError("Endpoint không trả về model nào.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Không lấy được danh sách model");
    } finally {
      setDiscovering(false);
    }
  }

  async function handleProbe() {
    setProbe({ busy: true, ok: true, text: "" });
    try {
      const res = await api<{ dimension: number; supported: boolean; latency_ms: number }>(
        "/api/settings/embeddings/probe-dimension",
        { method: "POST", body: { ...endpointBody(), model_id: modelId.trim() } },
      );
      if (res.supported) setDimension(res.dimension);
      setProbe({
        busy: false,
        ok: res.supported,
        text: res.supported
          ? `Model trả về vector ${res.dimension} chiều · ${res.latency_ms} ms`
          : `Model trả về ${res.dimension} chiều — hệ thống chỉ hỗ trợ ${EMBEDDING_DIMENSIONS.join(" / ")}.`,
      });
    } catch (e) {
      setProbe({ busy: false, ok: false, text: e instanceof Error ? e.message : "Không gọi được model" });
    }
  }

  const canSave = modelId.trim().length > 0 && (!isCustom || baseUrl.trim().length > 0);

  async function handleSave() {
    setSaving(true);
    setError("");
    try {
      const saved = await api<SavedModel>("/api/settings/custom-models", {
        method: "POST",
        body: {
          kind,
          provider,
          label: label.trim() || undefined,
          base_url: isCustom ? baseUrl.trim() : undefined,
          model_id: modelId.trim(),
          api_key: (isCustom && apiKey.trim()) || undefined,
          protocol: isCustom ? protocol : undefined,
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
    <div className="rounded-lg border border-dashed border-primary/40 bg-primary/5 p-3 flex flex-col gap-3">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {isCustom && (
          <div className="flex flex-col gap-1.5 sm:col-span-2">
            <Label className="text-xs">Base URL *</Label>
            <Input
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder={protocol === "anthropic" ? "https://api.anthropic.com" : "https://api.example.com/v1"}
              className="bg-background font-mono text-xs"
            />
          </div>
        )}
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center justify-between gap-2">
            <Label className="text-xs">Model name *</Label>
            <button
              type="button"
              onClick={handleDiscover}
              disabled={discovering || !canReachEndpoint}
              title={canReachEndpoint ? "Gọi GET /models của endpoint" : "Nhập Base URL trước"}
              className="text-[11px] text-primary hover:underline disabled:opacity-50 disabled:no-underline"
            >
              {discovering ? "Đang tải…" : discovered ? "Tải lại danh sách" : "Tải danh sách từ endpoint"}
            </button>
          </div>
          {showSelect ? (
            <select
              value={modelId || ""}
              onChange={(e) => pickModel(e.target.value)}
              className="h-9 rounded-md border border-input bg-background px-2 font-mono text-xs"
            >
              <option value="" disabled>
                — Chọn model —
              </option>
              {known.length > 0 && (
                <optgroup label="Gợi ý">
                  {known.map((o) => (
                    <option key={o.id} value={o.id}>
                      {o.id}
                      {o.dim ? ` · ${o.dim}d` : ""}
                      {o.hint ? ` · ${o.hint}` : ""}
                    </option>
                  ))}
                </optgroup>
              )}
              {fromEndpoint.length > 0 && (
                <optgroup label="Từ endpoint">
                  {fromEndpoint.map((id) => (
                    <option key={id} value={id}>
                      {id}
                    </option>
                  ))}
                </optgroup>
              )}
              <option value={MANUAL}>Khác — nhập tay…</option>
            </select>
          ) : (
            <>
              <Input
                value={modelId}
                onChange={(e) => {
                  setModelId(e.target.value);
                  setProbe(null);
                }}
                placeholder={isCustom ? "vd: BAAI/bge-m3" : `Model ID của ${PROVIDER_LABELS[provider]}`}
                maxLength={100}
                className="bg-background font-mono text-xs"
              />
              {manual && known.length + fromEndpoint.length > 0 && (
                <button
                  type="button"
                  onClick={() => setManual(false)}
                  className="self-start text-[11px] text-muted-foreground hover:text-foreground hover:underline"
                >
                  Chọn từ danh sách
                </button>
              )}
            </>
          )}
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
        {isCustom && (
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
        )}
        {isCustom && kind === "llm" && (
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
            <div className="flex gap-2">
              <select
                value={dimension}
                onChange={(e) => setDimension(Number(e.target.value))}
                className="h-9 flex-1 rounded-md border border-input bg-background px-2 text-xs"
              >
                {EMBEDDING_DIMENSIONS.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="h-9"
                onClick={handleProbe}
                disabled={!modelId.trim() || !canReachEndpoint || probe?.busy}
                title="Gọi thử model để đo số chiều thực tế"
              >
                {probe?.busy ? "Đang dò…" : "Dò"}
              </Button>
            </div>
            {probe && !probe.busy && (
              <p className={`text-[11px] ${probe.ok ? "text-emerald-600" : "text-destructive"}`}>
                {probe.text}
              </p>
            )}
          </div>
        )}
      </div>
      <p className="text-[11px] text-muted-foreground">
        {isCustom
          ? kind === "llm"
            ? "Endpoint OpenAI-compatible (vLLM, Ollama, LiteLLM…) hoặc Anthropic Messages."
            : "Endpoint phải tương thích OpenAI API"
          : `Dùng endpoint và API key chung của ${PROVIDER_LABELS[provider]}.`}
        {kind === "embedding" && " Vector trả về phải đúng số chiều đã chọn."}
      </p>
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
  spec: {
    model_id: string;
    label: string;
    group?: string;
    base_url?: string | null;
    protocol?: string | null;
    dimension?: number;
  },
  apiKey: string,
) {
  await api("/api/settings/custom-models", {
    method: "POST",
    body: {
      kind,
      provider: spec.group ?? "custom",
      model_id: spec.model_id,
      label: spec.label,
      base_url: spec.base_url,
      protocol: spec.protocol ?? "openai",
      dimension: kind === "embedding" ? spec.dimension : undefined,
      api_key: apiKey,
    },
  });
}
