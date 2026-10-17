"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  CustomModelForm,
  PROVIDER_LABELS,
  deleteCustomModel,
  saveCustomModelKey,
  type CustomModelKind,
  type ProviderGroup,
} from "./custom-model-form";

/** Fields every model catalog (LLM, Vision, Embedding, OCR) returns. */
export type PickerSpec = {
  id: string;
  label: string;
  model_id: string;
  group: string;
  custom: boolean;
  api_key_configured: boolean;
  base_url?: string | null;
  protocol?: string | null;
  dimension?: number;
  notes?: string | null;
};

const GROUP_ORDER: ProviderGroup[] = ["anthropic", "openai", "google", "custom"];

const GROUP_STYLE: Record<ProviderGroup, { chip: string; dot: string }> = {
  anthropic: {
    chip: "bg-orange-700/12 text-orange-800 dark:bg-orange-400/15 dark:text-orange-300",
    dot: "bg-orange-700 dark:bg-orange-400",
  },
  openai: {
    chip: "bg-emerald-600/12 text-emerald-700 dark:bg-emerald-400/15 dark:text-emerald-300",
    dot: "bg-emerald-600 dark:bg-emerald-400",
  },
  google: {
    chip: "bg-blue-600/12 text-blue-700 dark:bg-blue-400/15 dark:text-blue-300",
    dot: "bg-blue-600 dark:bg-blue-400",
  },
  custom: {
    chip: "bg-slate-500/12 text-slate-700 dark:bg-slate-400/15 dark:text-slate-300",
    dot: "bg-slate-600 dark:bg-slate-400",
  },
};

/** Map any catalog group onto one of the four tabs (unknown → custom). */
function normalizeGroup(group: string): ProviderGroup {
  return (GROUP_ORDER as string[]).includes(group) ? (group as ProviderGroup) : "custom";
}

const MASK_CHAR = "•";

/* ------------------------------------------------------------------ */
/* Small display pieces                                                */
/* ------------------------------------------------------------------ */

export function ProviderMark({ group, className = "" }: { group: string; className?: string }) {
  const g = normalizeGroup(group);
  return (
    <span
      className={cn(
        "inline-flex size-5 shrink-0 items-center justify-center rounded-[5px] text-[10px] leading-none font-bold",
        GROUP_STYLE[g].chip,
        className,
      )}
      aria-hidden
    >
      {g === "custom" ? (
        <span className="material-symbols-outlined text-[12px]">dns</span>
      ) : (
        PROVIDER_LABELS[g].charAt(0)
      )}
    </span>
  );
}

export function ActiveModelChip({ spec }: { spec: PickerSpec | null }) {
  if (!spec) {
    return <span className="text-xs text-amber-600 dark:text-amber-400">Chưa chọn model</span>;
  }
  return (
    <span className="inline-flex max-w-full min-w-0 items-center gap-1.5 rounded-full border border-border/70 bg-muted/50 py-0.5 pr-2.5 pl-1 text-xs">
      <ProviderMark group={spec.group} className="size-4 text-[9px]" />
      <span className="truncate font-medium text-foreground">{spec.label}</span>
      <span className="shrink-0 text-muted-foreground">· {PROVIDER_LABELS[normalizeGroup(spec.group)]}</span>
    </span>
  );
}

/* ------------------------------------------------------------------ */
/* KeyInput: shows the stored mask until focused, then a password box  */
/* ------------------------------------------------------------------ */

function KeyInput({
  value,
  onChange,
  mask,
  placeholder,
  disabled,
}: {
  value: string;
  onChange: (value: string) => void;
  mask: string | null;
  placeholder: string;
  disabled?: boolean;
}) {
  const [focused, setFocused] = useState(false);
  const [reveal, setReveal] = useState(false);

  const shown = !focused && value === "" && mask ? mask : value;
  const masked = shown.includes(MASK_CHAR);
  const typing = !masked && value !== "";

  return (
    <div className="relative min-w-0 flex-1">
      <input
        type={masked ? "text" : reveal ? "text" : "password"}
        value={shown}
        placeholder={placeholder}
        disabled={disabled}
        autoComplete="off"
        spellCheck={false}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        onChange={(e) => onChange(e.target.value)}
        className={cn(
          "h-8 w-full rounded-lg border border-input bg-background px-2.5 font-mono text-xs outline-none placeholder:font-sans placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50",
          typing && "pr-8",
        )}
      />
      {typing && (
        <button
          type="button"
          tabIndex={-1}
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => setReveal((v) => !v)}
          title={reveal ? "Ẩn key" : "Hiện key"}
          aria-label={reveal ? "Ẩn key" : "Hiện key"}
          className="absolute inset-y-0 right-1.5 flex items-center text-muted-foreground hover:text-foreground"
        >
          <span className="material-symbols-outlined text-base">{reveal ? "visibility_off" : "visibility"}</span>
        </button>
      )}
    </div>
  );
}

function canSaveKey(draft: string, busy: boolean, disabled: boolean): boolean {
  const v = draft.trim();
  return v.length > 0 && !v.includes(MASK_CHAR) && !busy && !disabled;
}

/* ------------------------------------------------------------------ */
/* ProviderModelPicker                                                 */
/* ------------------------------------------------------------------ */

type Notice = { ok: boolean; text: string } | null;

function errorText(err: unknown): string {
  return err instanceof Error && err.message ? err.message : "Thao tác thất bại";
}

export function ProviderModelPicker<S extends PickerSpec>({
  kind,
  keyKind,
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
  keyKind?: string;
  specs: S[];
  activeId: string | null;
  selectedId: string | null;
  onSelect: (id: string) => void;
  settings: Record<string, unknown>;
  onChanged: () => Promise<unknown>;
  onProviderKeySaved?: (group: ProviderGroup) => Promise<unknown>;
  renderMeta?: (spec: S) => ReactNode;
  disabled?: boolean;
  keyFallbackHint?: string;
}) {
  const [tab, setTab] = useState<ProviderGroup>(() => {
    const active = specs.find((s) => s.id === activeId);
    if (active) return normalizeGroup(active.group);
    const selected = specs.find((s) => s.id === selectedId);
    if (selected) return normalizeGroup(selected.group);
    if (specs[0]) return normalizeGroup(specs[0].group);
    return "custom";
  });
  const [adding, setAdding] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [providerKey, setProviderKey] = useState("");
  // Draft key for a custom model, bound to the model it was typed for.
  const [modelKey, setModelKey] = useState<{ id: string; value: string }>({ id: "", value: "" });
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);
  const noticeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (noticeTimer.current) clearTimeout(noticeTimer.current);
    };
  }, []);

  function showNotice(next: Notice) {
    if (noticeTimer.current) clearTimeout(noticeTimer.current);
    noticeTimer.current = null;
    setNotice(next);
    if (next?.ok) noticeTimer.current = setTimeout(() => setNotice(null), 2500);
  }

  function switchTab(next: ProviderGroup) {
    if (next === tab) return;
    setTab(next);
    setAdding(false);
    setEditingId(null);
    setProviderKey("");
    showNotice(null);
  }

  async function run(action: () => Promise<string>) {
    setBusy(true);
    try {
      const msg = await action();
      showNotice({ ok: true, text: msg });
    } catch (err) {
      showNotice({ ok: false, text: errorText(err) });
    } finally {
      setBusy(false);
    }
  }

  const providerLabel = PROVIDER_LABELS[tab];
  const tabSpecs = specs.filter((s) => normalizeGroup(s.group) === tab);
  const activeSpec = specs.find((s) => s.id === activeId) ?? null;
  const activeGroup = activeSpec ? normalizeGroup(activeSpec.group) : null;
  const selectedSpec = specs.find((s) => s.id === selectedId) ?? null;

  const configKey = `${keyKind ?? kind}_api_key__${tab}`;
  const rawMask = settings[configKey];
  const mask = typeof rawMask === "string" && rawMask.length > 0 ? rawMask : null;
  const hasSharedKey = tabSpecs.some((s) => !s.custom && s.api_key_configured);

  async function saveProviderKey() {
    const value = providerKey.trim();
    const group = tab;
    await run(async () => {
      await api("/api/settings", { method: "PUT", body: { settings: { [configKey]: value } } });
      setProviderKey("");
      if (onProviderKeySaved) await onProviderKeySaved(group);
      await onChanged();
      return `Đã lưu API key ${PROVIDER_LABELS[group]}`;
    });
  }

  async function saveModelKey(spec: S) {
    const value = modelKey.value.trim();
    await run(async () => {
      await saveCustomModelKey(kind, spec, value);
      setModelKey({ id: "", value: "" });
      await onChanged();
      return "Đã lưu API key của model";
    });
  }

  async function removeModel(spec: S) {
    if (!window.confirm(`Xóa model "${spec.label}"?`)) return;
    await run(async () => {
      await deleteCustomModel(kind, spec.id);
      await onChanged();
      return "Đã xóa model";
    });
  }

  function handleEdited(spec: S, newId: string) {
    setEditingId(null);
    if (spec.id === selectedId) onSelect(newId);
    void run(async () => {
      await onChanged();
      return "Đã lưu thay đổi";
    });
  }

  function handleAdded(newId: string) {
    setAdding(false);
    onSelect(newId);
    setBusy(true);
    onChanged()
      .catch((err: unknown) => showNotice({ ok: false, text: errorText(err) }))
      .finally(() => setBusy(false));
  }

  const locked = disabled || busy;

  /* ---------- tab bar ---------- */
  const tabBar = (
    <div role="tablist" className="grid grid-cols-4 gap-1 rounded-xl border border-border/70 bg-muted/40 p-1">
      {GROUP_ORDER.map((g) => {
        const on = g === tab;
        const count = specs.filter((s) => normalizeGroup(s.group) === g).length;
        return (
          <button
            key={g}
            type="button"
            role="tab"
            aria-selected={on}
            onClick={() => switchTab(g)}
            className={cn(
              "relative flex min-w-0 items-center justify-center gap-1.5 rounded-lg px-2 py-1.5 text-xs font-medium transition-colors",
              on ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
            )}
          >
            <ProviderMark group={g} />
            <span className="truncate">{PROVIDER_LABELS[g]}</span>
            <span className="hidden font-mono text-[10px] text-muted-foreground sm:inline">{count}</span>
            {activeGroup === g && (
              <span
                title="Model đang dùng thuộc nhóm này"
                className={cn("absolute top-1 right-1 size-1.5 rounded-full", GROUP_STYLE[g].dot)}
              />
            )}
          </button>
        );
      })}
    </div>
  );

  if (kind === "embedding" && tab === "anthropic") {
    return (
      <div className="flex flex-col gap-3">
        {tabBar}
        <div className="flex items-start gap-2 rounded-lg border border-dashed border-border p-4 text-xs text-muted-foreground">
          <span className="material-symbols-outlined text-base">info</span>
          <p>
            Anthropic không cung cấp model embedding. Dùng OpenAI, Gemini, hoặc thêm endpoint embedding riêng (vd: Voyage
            AI) ở tab <strong className="text-foreground">Custom</strong>.
          </p>
        </div>
      </div>
    );
  }

  const otherIdsInTab = (exceptId?: string) =>
    tabSpecs.filter((s) => s.id !== exceptId).map((s) => s.model_id);

  const customSelected =
    tab === "custom" && selectedSpec && normalizeGroup(selectedSpec.group) === "custom" ? selectedSpec : null;
  const modelKeyDraft = customSelected && modelKey.id === customSelected.id ? modelKey.value : "";

  return (
    <div className={cn("flex flex-col gap-3", disabled && "opacity-70")}>
      {tabBar}

      {/* Shared provider key */}
      {tab !== "custom" && (
        <div className="flex flex-col gap-1.5 rounded-lg border border-border/70 bg-background p-3">
          <div className="flex items-center justify-between gap-2 text-xs">
            <span className="font-medium text-foreground">API key {providerLabel}</span>
            {mask ? (
              <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
                <span className="material-symbols-outlined text-sm">check_circle</span>
                Đã lưu
              </span>
            ) : hasSharedKey && keyFallbackHint ? (
              <span className="text-muted-foreground">{keyFallbackHint}</span>
            ) : (
              <span className="text-amber-600 dark:text-amber-400">Chưa có key</span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <KeyInput
              value={providerKey}
              onChange={setProviderKey}
              mask={mask}
              placeholder={`Dán API key ${providerLabel}`}
              disabled={disabled}
            />
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-8"
              disabled={!canSaveKey(providerKey, busy, disabled)}
              onClick={() => void saveProviderKey()}
            >
              Lưu key
            </Button>
          </div>
          <p className="text-[11px] text-muted-foreground">Dùng chung cho mọi model {providerLabel} ở mục này.</p>
        </div>
      )}

      {/* Model list */}
      {tabSpecs.length === 0 && !adding ? (
        <div className="rounded-lg border border-dashed border-border p-4 text-center text-xs text-muted-foreground">
          {tab === "custom"
            ? "Chưa có model custom. Thêm endpoint OpenAI-compatible (vLLM, Ollama, LiteLLM…) bên dưới."
            : `Chưa có model ${providerLabel}.`}
        </div>
      ) : (
        <div className="flex flex-col gap-1.5">
          {tabSpecs.map((spec) => {
            if (editingId === spec.id) {
              return (
                <CustomModelForm
                  key={spec.id}
                  kind={kind}
                  provider={tab}
                  existingModelIds={otherIdsInTab(spec.id)}
                  initial={{
                    id: spec.id,
                    model_id: spec.model_id,
                    label: spec.label,
                    base_url: spec.base_url,
                    protocol: spec.protocol,
                    dimension: spec.dimension,
                  }}
                  onSaved={(newId) => handleEdited(spec, newId)}
                  onCancel={() => setEditingId(null)}
                />
              );
            }
            const checked = spec.id === selectedId;
            const isActive = spec.id === activeId;
            return (
              <div
                key={spec.id}
                className={cn(
                  "flex items-start gap-2 rounded-lg border px-3 py-2.5 transition-colors",
                  checked ? "border-primary bg-primary/5" : "border-border hover:bg-muted/30",
                  disabled && "cursor-not-allowed",
                )}
              >
                <label className={cn("flex min-w-0 flex-1 items-start gap-2.5", disabled ? "cursor-not-allowed" : "cursor-pointer")}>
                  <input
                    type="radio"
                    name={`${kind}-model`}
                    checked={checked}
                    disabled={disabled}
                    onChange={() => onSelect(spec.id)}
                    className="mt-1 accent-primary"
                  />
                  <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                    <span className="flex flex-wrap items-center gap-1.5">
                      <span className="text-sm font-medium text-foreground">{spec.label}</span>
                      {spec.custom && (
                        <span className="rounded-full border border-border px-1.5 text-[10px] text-muted-foreground">
                          Tự thêm
                        </span>
                      )}
                      {isActive && (
                        <span className="rounded-full bg-emerald-500/12 px-1.5 text-[10px] font-medium text-emerald-700 dark:text-emerald-300">
                          Đang dùng
                        </span>
                      )}
                      {tab === "custom" && !spec.api_key_configured && (
                        <span className="text-[10px] text-muted-foreground">không key</span>
                      )}
                    </span>
                    <span className="truncate font-mono text-[11px] text-muted-foreground">
                      {spec.model_id}
                      {tab === "custom" && spec.base_url ? ` · ${spec.base_url}` : ""}
                      {kind === "embedding" && spec.dimension ? ` · ${spec.dimension}d` : ""}
                    </span>
                    {!spec.custom && renderMeta && (
                      <span className="text-[11px] text-muted-foreground">{renderMeta(spec)}</span>
                    )}
                    {spec.notes && <span className="text-[11px] text-muted-foreground/80 italic">{spec.notes}</span>}
                  </span>
                </label>
                {spec.custom && (
                  <div className="flex shrink-0 items-center gap-0.5">
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-xs"
                      title="Sửa model"
                      aria-label="Sửa model"
                      disabled={locked}
                      onClick={() => {
                        setAdding(false);
                        setEditingId(spec.id);
                      }}
                    >
                      <span className="material-symbols-outlined text-[15px]">edit</span>
                    </Button>
                    <span title={isActive ? "Model đang dùng — chuyển sang model khác trước khi xóa" : "Xóa model"}>
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon-xs"
                        aria-label="Xóa model"
                        disabled={locked || isActive}
                        onClick={() => void removeModel(spec)}
                        className="hover:text-destructive"
                      >
                        <span className="material-symbols-outlined text-[15px]">delete</span>
                      </Button>
                    </span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Per-model key of the selected custom model */}
      {customSelected && editingId !== customSelected.id && (
        <div className="flex flex-col gap-1.5 rounded-lg border border-border/70 bg-background p-3">
          <span className="truncate text-xs font-medium text-foreground">API key · {customSelected.label}</span>
          <div className="flex items-center gap-2">
            <KeyInput
              value={modelKeyDraft}
              onChange={(v) => setModelKey({ id: customSelected.id, value: v })}
              mask={customSelected.api_key_configured ? "••••••••" : null}
              placeholder="Bỏ trống nếu endpoint không cần key"
              disabled={disabled}
            />
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-8"
              disabled={!canSaveKey(modelKeyDraft, busy, disabled)}
              onClick={() => void saveModelKey(customSelected)}
            >
              Lưu key
            </Button>
          </div>
        </div>
      )}

      {/* Add model */}
      {adding ? (
        <CustomModelForm
          kind={kind}
          provider={tab}
          existingModelIds={otherIdsInTab()}
          onSaved={handleAdded}
          onCancel={() => setAdding(false)}
        />
      ) : (
        <button
          type="button"
          disabled={locked}
          onClick={() => {
            setEditingId(null);
            setAdding(true);
          }}
          className="inline-flex items-center gap-1 self-start text-xs font-medium text-primary hover:underline disabled:cursor-not-allowed disabled:opacity-50 disabled:no-underline"
        >
          <span className="material-symbols-outlined text-sm">add</span>
          {tab === "custom" ? "Thêm model custom (base URL + API key)" : `Thêm model ${providerLabel}`}
        </button>
      )}

      {notice && (
        <p
          className={cn(
            "text-xs",
            notice.ok ? "text-emerald-600 dark:text-emerald-400" : "text-destructive",
          )}
        >
          {notice.text}
        </p>
      )}
    </div>
  );
}
