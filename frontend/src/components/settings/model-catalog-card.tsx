"use client";

import { useEffect, useState } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import {
  CustomModelForm,
  deleteCustomModel,
  saveCustomModelKey,
  type CustomModelKind,
} from "./custom-model-form";

// Shape shared by LLMSpecOut and VisionSpecOut on the backend. Cards pick which
// fields to display via the `renderMeta` prop so this component stays generic.
export type ModelSpec = {
  id: string;
  provider: string;
  model_id: string;
  label: string;
  notes: string | null;
  api_key_configured: boolean;
  // app_config key for a preset's (per-provider) API key; null for custom models.
  api_key_config_key: string | null;
  custom: boolean;
  base_url: string | null;
  protocol: string | null;
  // LLM-specific
  context_window_tokens?: number;
  max_output_tokens?: number;
  supports_tools?: boolean;
  supports_vision?: boolean;
  cost_per_1m_input_tokens?: number | null;
  cost_per_1m_output_tokens?: number | null;
  // Vision-specific
  max_image_size_mb?: number;
  cost_per_image?: number | null;
};

type CatalogResp = {
  active_spec_id: string | null;
  specs: ModelSpec[];
};

export function ModelCatalogCard({
  title,
  description,
  icon,
  catalogUrl,
  switchUrl,
  kind,
  renderMeta,
}: {
  title: string;
  description: string;
  icon: string;
  catalogUrl: string;
  switchUrl: string;
  kind: CustomModelKind;
  renderMeta?: (spec: ModelSpec) => React.ReactNode;
}) {
  const [catalog, setCatalog] = useState<CatalogResp | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [settings, setSettings] = useState<Record<string, unknown>>({});
  const [adding, setAdding] = useState(false);
  // Key typed for one model; switching models shows that model's saved key.
  const [keyDraft, setKeyDraft] = useState<{ id: string | null; value: string }>({
    id: null,
    value: "",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function refresh() {
    try {
      const [c, settings] = await Promise.all([
        api<CatalogResp>(catalogUrl),
        api<Record<string, unknown>>("/api/settings"),
      ]);
      setCatalog(c);
      setSettings(settings);
      setSelected((prev) =>
        prev && c.specs.some((s) => s.id === prev) ? prev : c.active_spec_id ?? c.specs[0]?.id ?? null,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : `Failed to load ${title}`);
    }
  }

  const selectedSpec = catalog?.specs.find((s) => s.id === selected) ?? null;
  // Masked saved key of the selected model ("••••…" = saved server-side).
  const keyName = selectedSpec?.api_key_config_key;
  const maskedValue = keyName ? settings[keyName] : undefined;
  const maskedKey =
    typeof maskedValue === "string" && maskedValue
      ? maskedValue
      : selectedSpec?.api_key_configured
        ? "••••••••"
        : "";

  const apiKey = keyDraft.id === selected ? keyDraft.value : maskedKey;
  const setApiKey = (value: string) => setKeyDraft({ id: selected, value });

  const isActiveSelected = selectedSpec?.id === catalog?.active_spec_id;
  const willSwitch = !!selectedSpec && !isActiveSelected;
  const isMaskedKey = apiKey.includes("•");
  const hasNewKey = apiKey.trim().length > 0 && !isMaskedKey;
  const canSave =
    !!selectedSpec &&
    (hasNewKey || (willSwitch && (selectedSpec.custom || selectedSpec.api_key_configured)));

  async function handleDelete(spec: ModelSpec) {
    if (!confirm(`Xóa model "${spec.label}"?`)) return;
    setError("");
    try {
      await deleteCustomModel(kind, spec.id);
      if (selected === spec.id) setSelected(null);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    }
  }

  async function handleSave() {
    if (!selectedSpec) return;
    setSaving(true);
    setError("");
    setSaved(false);
    try {
      if (hasNewKey) {
        if (selectedSpec.custom) {
          await saveCustomModelKey(kind, selectedSpec, apiKey.trim());
        } else if (selectedSpec.api_key_config_key) {
          await api("/api/settings", {
            method: "PUT",
            body: { settings: { [selectedSpec.api_key_config_key]: apiKey.trim() } },
          });
        }
      }
      if (willSwitch) {
        await api(switchUrl, {
          method: "POST",
          body: { model_spec_id: selectedSpec.id },
        });
      }
      setKeyDraft({ id: null, value: "" });
      await refresh();
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  if (!catalog) {
    return (
      <div className="bg-card rounded-xl p-6 border border-border shadow-sahara">
        <p className="text-sm text-muted-foreground">Loading {title.toLowerCase()}…</p>
      </div>
    );
  }

  return (
    <div className="bg-card rounded-xl p-6 border border-border shadow-sahara">
      <div className="flex items-center gap-3 mb-4">
        <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center">
          <span className="material-symbols-outlined text-primary text-base">{icon}</span>
        </div>
        <div className="flex-1">
          <h3 className="text-base font-semibold text-foreground">{title}</h3>
          <p className="text-xs text-muted-foreground">{description}</p>
        </div>
        {!adding && (
          <button
            onClick={() => setAdding(true)}
            className="flex items-center gap-1 border border-border px-2.5 py-1.5 rounded-lg text-xs font-medium hover:bg-muted"
          >
            <span className="material-symbols-outlined text-sm">add</span>
            Thêm model
          </button>
        )}
      </div>

      {adding && (
        <CustomModelForm
          kind={kind}
          onCancel={() => setAdding(false)}
          onSaved={async (id) => {
            setAdding(false);
            setSelected(id);
            await refresh();
          }}
        />
      )}

      {/* Model list */}
      <div className="flex flex-col gap-2 mb-4">
        {catalog.specs.map((spec) => {
          const isActive = spec.id === catalog.active_spec_id;
          const isChecked = spec.id === selected;
          return (
            <label
              key={spec.id}
              className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                isChecked ? "border-primary bg-primary/5" : "border-border hover:bg-accent/30"
              }`}
            >
              <input
                type="radio"
                name={`${title}-spec`}
                value={spec.id}
                checked={isChecked}
                onChange={() => setSelected(spec.id)}
                className="mt-1"
              />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-medium">{spec.label}</span>
                  <span className="text-[10px] uppercase tracking-wide text-muted-foreground bg-secondary/40 px-1.5 py-0.5 rounded">
                    {spec.custom ? "Tự thêm" : spec.provider}
                  </span>
                  {isActive && (
                    <span className="text-[10px] uppercase tracking-wide bg-green-500/15 text-green-700 dark:text-green-400 px-1.5 py-0.5 rounded">
                      Active
                    </span>
                  )}
                </div>
                {spec.custom ? (
                  <p className="text-[11px] text-muted-foreground mt-1 font-mono break-all">
                    {spec.model_id} · {spec.base_url}
                  </p>
                ) : (
                  renderMeta && (
                    <div className="text-[11px] text-muted-foreground mt-1">{renderMeta(spec)}</div>
                  )
                )}
                {spec.notes && (
                  <p className="text-[11px] text-muted-foreground/80 mt-1 italic">{spec.notes}</p>
                )}
              </div>
              {spec.custom && !isActive && (
                <button
                  type="button"
                  onClick={(e) => {
                    e.preventDefault();
                    void handleDelete(spec);
                  }}
                  title="Xóa model"
                  className="text-muted-foreground hover:text-destructive"
                >
                  <span className="material-symbols-outlined text-base">delete</span>
                </button>
              )}
            </label>
          );
        })}
      </div>

      {/* API key — per provider for presets, per model for custom models */}
      {selectedSpec && (
        <div className="mb-4 flex flex-col gap-1.5">
          <Label className="text-xs">
            API key {selectedSpec.custom ? selectedSpec.label : selectedSpec.provider}
            {selectedSpec.api_key_configured && (
              <span className="ml-2 text-green-600 dark:text-green-400">✓ saved</span>
            )}
          </Label>
          <Input
            type={isMaskedKey ? "text" : "password"}
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            onFocus={() => {
              if (isMaskedKey) setApiKey("");
            }}
            onBlur={() => {
              if (!apiKey) setApiKey(maskedKey);
            }}
            placeholder={
              selectedSpec.api_key_configured ? "Replace existing key…" : "Paste API key"
            }
            className="bg-background"
          />
        </div>
      )}

      <div className="flex items-center gap-3">
        <button
          disabled={!canSave || saving}
          onClick={handleSave}
          className="bg-primary text-primary-foreground px-4 py-2 rounded-lg text-sm font-medium hover:bg-primary/90 disabled:opacity-50"
        >
          {saving ? "Saving…" : willSwitch ? "Switch & Save" : "Save"}
        </button>
        {saved && (
          <span className="text-xs text-green-600 dark:text-green-400 flex items-center gap-1">
            <span className="material-symbols-outlined text-sm">check_circle</span>
            Saved
          </span>
        )}
        {error && <p className="text-xs text-destructive">{error}</p>}
      </div>
    </div>
  );
}
