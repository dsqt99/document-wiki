"use client";

import { useState } from "react";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import {
  CustomModelForm,
  PROVIDER_LABELS,
  deleteCustomModel,
  saveCustomModelKey,
  type CustomModelKind,
  type ProviderGroup,
} from "./custom-model-form";

/** Fields every catalog (LLM, Vision, Embedding, OCR) returns per model. */
export type PickerSpec = {
  id: string;
  label: string;
  model_id: string;
  // Provider group: "anthropic" | "openai" | "google" | "custom".
  group: string;
  custom: boolean;
  api_key_configured: boolean;
  base_url?: string | null;
  protocol?: string | null;
  dimension?: number;
  notes?: string | null;
};

const GROUPS: ProviderGroup[] = ["anthropic", "openai", "google", "custom"];

const GROUP_STYLE: Record<ProviderGroup, { dot: string; mark: string }> = {
  anthropic: { dot: "bg-[#d97757]", mark: "bg-[#d97757]/15 text-[#c4623f] dark:text-[#e8a08a]" },
  openai: { dot: "bg-emerald-500", mark: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400" },
  google: { dot: "bg-blue-500", mark: "bg-blue-500/15 text-blue-700 dark:text-blue-400" },
  custom: { dot: "bg-slate-500", mark: "bg-slate-500/15 text-slate-700 dark:text-slate-300" },
};

function asGroup(g: string | undefined): ProviderGroup {
  return GROUPS.includes(g as ProviderGroup) ? (g as ProviderGroup) : "custom";
}

export function ProviderMark({ group, className = "" }: { group: string; className?: string }) {
  const g = asGroup(group);
  return (
    <span
      className={`inline-flex h-5 min-w-5 items-center justify-center rounded px-1 text-[10px] font-bold ${GROUP_STYLE[g].mark} ${className}`}
    >
      {g === "custom" ? (
        <span className="material-symbols-outlined text-[13px]">dns</span>
      ) : (
        PROVIDER_LABELS[g][0]
      )}
    </span>
  );
}

/** Masked-key input: "••••" = saved server-side; focusing it clears it for typing. */
function KeyInput({
  value,
  onChange,
  maskedValue,
  placeholder,
  disabled,
}: {
  value: string;
  onChange: (v: string) => void;
  maskedValue: string;
  placeholder: string;
  disabled?: boolean;
}) {
  const [show, setShow] = useState(false);
  const isMasked = value.includes("•");
  return (
    <div className="relative flex-1 min-w-0">
      <Input
        type={show || isMasked ? "text" : "password"}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        onFocus={() => {
          if (isMasked) onChange("");
        }}
        onBlur={() => {
          if (!value) onChange(maskedValue);
        }}
        placeholder={placeholder}
        className="h-8 bg-background pr-8 font-mono text-xs"
      />
      {!isMasked && value && (
        <button
          type="button"
          onClick={() => setShow((s) => !s)}
          className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
          title={show ? "Ẩn key" : "Hiện key"}
        >
          <span className="material-symbols-outlined text-sm">{show ? "visibility_off" : "visibility"}</span>
        </button>
      )}
    </div>
  );
}

/**
 * Model picker grouped by provider (tabs Anthropic / OpenAI / Gemini / Custom).
 *
 * - Provider tabs: one shared API key per provider (`{keyKind}_api_key__{group}`)
 *   and "Thêm model" that only asks for the model name.
 * - Custom tab: own base URL + API key per model.
 *
 * Keys are saved here; activating the selected model is the card's job, since
 * each kind switches differently (embedding starts a re-embed job, OCR writes
 * the flat ocr_* keys).
 */
export function ProviderModelPicker<S extends PickerSpec>({
  kind,
  keyKind = kind,
  specs,
  activeId,
  selectedId,
  onSelect,
  settings,
  onChanged,
  onProviderKeySaved,
  renderMeta,
  disabled = false,
  keyFallbackHint,
}: {
  kind: CustomModelKind;
  /** Prefix of the provider key config keys (defaults to kind). */
  keyKind?: string;
  specs: S[];
  activeId: string | null;
  selectedId: string | null;
  onSelect: (id: string) => void;
  /** GET /api/settings payload (masked keys). */
  settings: Record<string, unknown>;
  onChanged: () => Promise<void>;
  onProviderKeySaved?: (group: ProviderGroup) => Promise<void>;
  renderMeta?: (spec: S) => React.ReactNode;
  disabled?: boolean;
  /** Shown when a provider has no key of its own (e.g. OCR reuses Vision's). */
  keyFallbackHint?: string;
}) {
  const activeSpec = specs.find((s) => s.id === activeId) ?? null;
  const [tab, setTab] = useState<ProviderGroup>(() =>
    asGroup((activeSpec ?? specs.find((s) => s.id === selectedId) ?? specs[0])?.group),
  );
  const [adding, setAdding] = useState(false);
  const [providerKey, setProviderKey] = useState<{ group: ProviderGroup | null; value: string }>({
    group: null,
    value: "",
  });
  const [modelKey, setModelKey] = useState<{ id: string | null; value: string }>({ id: null, value: "" });
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const tabSpecs = specs.filter((s) => asGroup(s.group) === tab);
  const noEmbeddingModels = kind === "embedding" && tab === "anthropic";

  // Provider-level key (not used by the Custom tab).
  const providerConfigKey = `${keyKind}_api_key__${tab}`;
  const storedMask = settings[providerConfigKey];
  const providerMasked = typeof storedMask === "string" && storedMask ? storedMask : "";
  const providerHasKey =
    !!providerMasked || specs.some((s) => asGroup(s.group) === tab && !s.custom && s.api_key_configured);
  const providerKeyValue = providerKey.group === tab ? providerKey.value : providerMasked;
  const providerKeyIsNew = !!providerKeyValue.trim() && !providerKeyValue.includes("•");

  // Per-model key for the selected model of the Custom tab.
  const selectedSpec = specs.find((s) => s.id === selectedId) ?? null;
  const selectedCustom = tab === "custom" && selectedSpec && asGroup(selectedSpec.group) === "custom" ? selectedSpec : null;
  const modelMasked = selectedCustom?.api_key_configured ? "••••••••" : "";
  const modelKeyValue = modelKey.id === selectedCustom?.id ? modelKey.value : modelMasked;
  const modelKeyIsNew = !!modelKeyValue.trim() && !modelKeyValue.includes("•");

  function flash(ok: boolean, text: string) {
    setMessage({ ok, text });
    if (ok) setTimeout(() => setMessage(null), 2500);
  }

  async function run(action: () => Promise<void>, okText: string) {
    setBusy(true);
    setMessage(null);
    try {
      await action();
      flash(true, okText);
    } catch (e) {
      flash(false, e instanceof Error ? e.message : "Thao tác thất bại");
    } finally {
      setBusy(false);
    }
  }

  const saveProviderKey = () =>
    run(async () => {
      await api("/api/settings", {
        method: "PUT",
        body: { settings: { [providerConfigKey]: providerKeyValue.trim() } },
      });
      setProviderKey({ group: null, value: "" });
      await onProviderKeySaved?.(tab);
      await onChanged();
    }, `Đã lưu API key ${PROVIDER_LABELS[tab]}`);

  const saveModelKey = () =>
    run(async () => {
      if (!selectedCustom) return;
      await saveCustomModelKey(kind, selectedCustom, modelKeyValue.trim());
      setModelKey({ id: null, value: "" });
      await onChanged();
    }, "Đã lưu API key của model");

  const removeModel = (spec: S) => {
    if (!confirm(`Xóa model "${spec.label}"?`)) return;
    void run(async () => {
      await deleteCustomModel(kind, spec.id);
      await onChanged();
    }, "Đã xóa model");
  };

  function switchTab(g: ProviderGroup) {
    setTab(g);
    setAdding(false);
    setMessage(null);
  }

  return (
    <div className="flex flex-col gap-3">
      {/* Provider tabs */}
      <div role="tablist" className="grid grid-cols-4 gap-1 rounded-lg border border-border bg-muted/30 p-1">
        {GROUPS.map((g) => {
          const count = specs.filter((s) => asGroup(s.group) === g).length;
          const hasActive = !!activeSpec && asGroup(activeSpec.group) === g;
          const selected = tab === g;
          return (
            <button
              key={g}
              role="tab"
              type="button"
              aria-selected={selected}
              onClick={() => switchTab(g)}
              className={`relative flex items-center justify-center gap-1.5 rounded-md px-2 py-1.5 text-xs font-medium transition-colors ${
                selected
                  ? "bg-background text-foreground shadow-xs"
                  : "text-muted-foreground hover:text-foreground hover:bg-background/60"
              }`}
            >
              <ProviderMark group={g} />
              <span className="truncate">{PROVIDER_LABELS[g]}</span>
              <span className="hidden sm:inline text-[10px] text-muted-foreground tabular-nums">{count}</span>
              {hasActive && (
                <span
                  className={`absolute right-1 top-1 h-1.5 w-1.5 rounded-full ${GROUP_STYLE[g].dot}`}
                  title="Model đang dùng thuộc nhóm này"
                />
              )}
            </button>
          );
        })}
      </div>

      {noEmbeddingModels ? (
        <div className="rounded-lg border border-dashed border-border p-4 text-xs text-muted-foreground flex items-start gap-2">
          <span className="material-symbols-outlined text-base">info</span>
          <span>
            Anthropic không cung cấp model embedding. Dùng OpenAI, Gemini, hoặc thêm endpoint
            embedding riêng (vd: Voyage AI) ở tab <strong>Custom</strong>.
          </span>
        </div>
      ) : (
        <>
          {/* Shared provider key */}
          {tab !== "custom" && (
            <div className="rounded-lg border border-border bg-muted/20 p-3 flex flex-col gap-2">
              <div className="flex items-center justify-between gap-2 text-xs">
                <span className="font-medium text-foreground">API key {PROVIDER_LABELS[tab]}</span>
                {providerMasked ? (
                  <span className="text-green-600 dark:text-green-400 flex items-center gap-0.5">
                    <span className="material-symbols-outlined text-sm">check_circle</span>
                    Đã lưu
                  </span>
                ) : providerHasKey && keyFallbackHint ? (
                  <span className="text-muted-foreground">{keyFallbackHint}</span>
                ) : (
                  <span className="text-amber-600 dark:text-amber-400">Chưa có key</span>
                )}
              </div>
              <div className="flex items-center gap-2">
                <KeyInput
                  value={providerKeyValue}
                  maskedValue={providerMasked}
                  onChange={(v) => setProviderKey({ group: tab, value: v })}
                  placeholder={`Dán API key ${PROVIDER_LABELS[tab]}`}
                  disabled={disabled}
                />
                <button
                  type="button"
                  disabled={!providerKeyIsNew || busy || disabled}
                  onClick={() => void saveProviderKey()}
                  className="h-8 shrink-0 rounded-md border border-border bg-background px-3 text-xs font-medium hover:bg-muted disabled:opacity-50"
                >
                  Lưu key
                </button>
              </div>
              <p className="text-[11px] text-muted-foreground">
                Dùng chung cho mọi model {PROVIDER_LABELS[tab]} ở mục này.
              </p>
            </div>
          )}

          {/* Model list */}
          <div className="flex flex-col gap-1.5">
            {tabSpecs.length === 0 && !adding && (
              <p className="rounded-lg border border-dashed border-border p-4 text-center text-xs text-muted-foreground">
                {tab === "custom"
                  ? "Chưa có model custom. Thêm endpoint OpenAI-compatible (vLLM, Ollama, LiteLLM…) bên dưới."
                  : `Chưa có model ${PROVIDER_LABELS[tab]}.`}
              </p>
            )}
            {tabSpecs.map((spec) => {
              const isActive = spec.id === activeId;
              const isChecked = spec.id === selectedId;
              return (
                <label
                  key={spec.id}
                  className={`flex items-start gap-3 rounded-lg border p-2.5 transition-colors ${
                    disabled ? "cursor-not-allowed opacity-70" : "cursor-pointer"
                  } ${isChecked ? "border-primary bg-primary/5" : "border-border hover:bg-accent/30"}`}
                >
                  <input
                    type="radio"
                    name={`${kind}-model`}
                    value={spec.id}
                    checked={isChecked}
                    disabled={disabled}
                    onChange={() => onSelect(spec.id)}
                    className="mt-1"
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className="text-sm font-medium">{spec.label}</span>
                      {spec.custom && (
                        <span className="text-[10px] uppercase tracking-wide text-muted-foreground bg-secondary/40 px-1.5 py-0.5 rounded">
                          Tự thêm
                        </span>
                      )}
                      {isActive && (
                        <span className="text-[10px] uppercase tracking-wide bg-green-500/15 text-green-700 dark:text-green-400 px-1.5 py-0.5 rounded">
                          Đang dùng
                        </span>
                      )}
                      {!spec.api_key_configured && tab === "custom" && (
                        <span className="text-[10px] text-muted-foreground">không key</span>
                      )}
                    </div>
                    <p className="text-[11px] text-muted-foreground mt-0.5 font-mono break-all">
                      {spec.model_id}
                      {tab === "custom" && spec.base_url ? ` · ${spec.base_url}` : ""}
                      {kind === "embedding" && spec.dimension ? ` · ${spec.dimension}d` : ""}
                    </p>
                    {!spec.custom && renderMeta && (
                      <div className="text-[11px] text-muted-foreground mt-0.5">{renderMeta(spec)}</div>
                    )}
                    {spec.notes && <p className="text-[11px] text-muted-foreground/80 mt-0.5 italic">{spec.notes}</p>}
                  </div>
                  {spec.custom && !isActive && (
                    <button
                      type="button"
                      disabled={disabled || busy}
                      onClick={(e) => {
                        e.preventDefault();
                        removeModel(spec);
                      }}
                      title="Xóa model"
                      className="text-muted-foreground hover:text-destructive disabled:opacity-50"
                    >
                      <span className="material-symbols-outlined text-base">delete</span>
                    </button>
                  )}
                </label>
              );
            })}
          </div>

          {/* Per-model key (Custom tab) */}
          {selectedCustom && (
            <div className="flex flex-col gap-1.5">
              <span className="text-xs font-medium">API key · {selectedCustom.label}</span>
              <div className="flex items-center gap-2">
                <KeyInput
                  value={modelKeyValue}
                  maskedValue={modelMasked}
                  onChange={(v) => setModelKey({ id: selectedCustom.id, value: v })}
                  placeholder="Bỏ trống nếu endpoint không cần key"
                  disabled={disabled}
                />
                <button
                  type="button"
                  disabled={!modelKeyIsNew || busy || disabled}
                  onClick={() => void saveModelKey()}
                  className="h-8 shrink-0 rounded-md border border-border bg-background px-3 text-xs font-medium hover:bg-muted disabled:opacity-50"
                >
                  Lưu key
                </button>
              </div>
            </div>
          )}

          {adding ? (
            <CustomModelForm
              kind={kind}
              provider={tab}
              existingModelIds={tabSpecs.map((s) => s.model_id)}
              onCancel={() => setAdding(false)}
              onSaved={async (id) => {
                setAdding(false);
                onSelect(id);
                await onChanged();
              }}
            />
          ) : (
            <button
              type="button"
              disabled={disabled}
              onClick={() => setAdding(true)}
              className="self-start flex items-center gap-1 text-xs font-medium text-primary hover:underline disabled:opacity-50"
            >
              <span className="material-symbols-outlined text-sm">add</span>
              {tab === "custom" ? "Thêm model custom (base URL + API key)" : `Thêm model ${PROVIDER_LABELS[tab]}`}
            </button>
          )}
        </>
      )}

      {message && (
        <p className={`text-xs ${message.ok ? "text-green-600 dark:text-green-400" : "text-destructive"}`}>
          {message.text}
        </p>
      )}
    </div>
  );
}

/** "Đang dùng: X · Provider" chip for card headers. */
export function ActiveModelChip({ spec }: { spec: PickerSpec | null }) {
  if (!spec) {
    return <span className="text-xs text-amber-600 dark:text-amber-400">Chưa chọn model</span>;
  }
  const g = asGroup(spec.group);
  return (
    <span className="inline-flex max-w-full items-center gap-1.5 rounded-full border border-border bg-muted/40 px-2 py-0.5 text-xs">
      <ProviderMark group={g} className="h-4 min-w-4" />
      <span className="truncate font-medium">{spec.label}</span>
      <span className="text-muted-foreground">· {PROVIDER_LABELS[g]}</span>
    </span>
  );
}
