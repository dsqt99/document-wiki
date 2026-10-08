"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { CustomModelKind } from "./custom-model-form";
import { ActiveModelChip, ProviderModelPicker } from "./provider-model-picker";

// Shape shared by LLMSpecOut and VisionSpecOut on the backend. Cards pick which
// fields to display via the `renderMeta` prop so this component stays generic.
export type ModelSpec = {
  id: string;
  provider: string;
  // Provider group shown as a tab: "anthropic" | "openai" | "google" | "custom".
  group: string;
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

/** Selected model can be activated: provider models need their provider key. */
export function canActivate(spec: { group: string; api_key_configured: boolean } | null) {
  return !!spec && (spec.group === "custom" || spec.api_key_configured);
}

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
  const [switching, setSwitching] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function refresh() {
    try {
      const [c, s] = await Promise.all([
        api<CatalogResp>(catalogUrl),
        api<Record<string, unknown>>("/api/settings"),
      ]);
      setCatalog(c);
      setSettings(s);
      setSelected((prev) =>
        prev && c.specs.some((x) => x.id === prev) ? prev : c.active_spec_id ?? c.specs[0]?.id ?? null,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : `Failed to load ${title}`);
    }
  }

  const selectedSpec = catalog?.specs.find((s) => s.id === selected) ?? null;
  const activeSpec = catalog?.specs.find((s) => s.id === catalog.active_spec_id) ?? null;
  const willSwitch = !!selectedSpec && selectedSpec.id !== catalog?.active_spec_id;

  async function handleActivate() {
    if (!selectedSpec) return;
    setSwitching(true);
    setError("");
    setSaved(false);
    try {
      await api(switchUrl, { method: "POST", body: { model_spec_id: selectedSpec.id } });
      await refresh();
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Switch failed");
    } finally {
      setSwitching(false);
    }
  }

  if (!catalog) {
    return (
      <div className="bg-card rounded-xl p-6 border border-border shadow-sahara">
        <p className="text-sm text-muted-foreground">Loading {title.toLowerCase()}…</p>
        {error && <p className="text-xs text-destructive mt-2">{error}</p>}
      </div>
    );
  }

  return (
    <div className="bg-card rounded-xl p-6 border border-border shadow-sahara flex flex-col gap-4">
      <div className="flex items-start gap-3">
        <div className="w-9 h-9 shrink-0 rounded-lg bg-primary/10 flex items-center justify-center">
          <span className="material-symbols-outlined text-primary text-base">{icon}</span>
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-base font-semibold text-foreground">{title}</h3>
          <p className="text-xs text-muted-foreground">{description}</p>
        </div>
        <ActiveModelChip spec={activeSpec} />
      </div>

      <ProviderModelPicker
        kind={kind}
        specs={catalog.specs}
        activeId={catalog.active_spec_id}
        selectedId={selected}
        onSelect={setSelected}
        settings={settings}
        onChanged={refresh}
        renderMeta={renderMeta}
      />

      <ActivateBar
        willSwitch={willSwitch}
        ready={canActivate(selectedSpec)}
        busy={switching}
        saved={saved}
        error={error}
        label={selectedSpec?.label}
        onActivate={handleActivate}
      />
    </div>
  );
}

/** Footer of the model cards: "Dùng model này" for the selected model. */
export function ActivateBar({
  willSwitch,
  ready,
  busy,
  saved,
  error,
  label,
  onActivate,
  actionText = "Dùng model này",
  disabled = false,
  children,
}: {
  willSwitch: boolean;
  ready: boolean;
  busy: boolean;
  saved: boolean;
  error: string;
  label?: string;
  onActivate: () => void;
  actionText?: string;
  disabled?: boolean;
  children?: React.ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-center gap-3 border-t border-border/60 pt-3">
      <button
        disabled={!willSwitch || !ready || busy || disabled}
        onClick={onActivate}
        className="bg-primary text-primary-foreground px-4 py-2 rounded-lg text-sm font-medium hover:bg-primary/90 disabled:opacity-50"
      >
        {busy ? "Đang chuyển…" : actionText}
      </button>
      {children}
      {willSwitch && !ready && (
        <span className="text-xs text-amber-600 dark:text-amber-400">
          Lưu API key của nhà cung cấp trước khi dùng {label}.
        </span>
      )}
      {!willSwitch && !saved && !error && (
        <span className="text-xs text-muted-foreground">Model đang chọn là model đang dùng.</span>
      )}
      {saved && (
        <span className="text-xs text-green-600 dark:text-green-400 flex items-center gap-1">
          <span className="material-symbols-outlined text-sm">check_circle</span>
          Đã chuyển model
        </span>
      )}
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}
