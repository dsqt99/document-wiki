"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import type { CustomModelKind } from "./custom-model-form";
import { ActiveModelChip, ProviderModelPicker } from "./provider-model-picker";

/** One entry of the LLM / Vision catalogs. */
export type ModelSpec = {
  id: string;
  provider: string;
  group: string;
  model_id: string;
  label: string;
  notes: string | null;
  api_key_configured: boolean;
  api_key_config_key: string | null;
  custom: boolean;
  base_url: string | null;
  protocol: string | null;
  // LLM
  context_window_tokens?: number;
  max_output_tokens?: number;
  supports_tools?: boolean;
  supports_vision?: boolean;
  cost_per_1m_input_tokens?: number | null;
  cost_per_1m_output_tokens?: number | null;
  // Vision
  max_image_size_mb?: number;
  cost_per_image?: number | null;
};

type Catalog = { active_spec_id: string | null; specs: ModelSpec[] };

/**
 * Custom endpoints may run without a key, so they are always eligible; provider
 * presets need their shared key saved first.
 */
export function canActivate(spec: { group: string; api_key_configured: boolean } | null): boolean {
  return !!spec && (spec.group === "custom" || spec.api_key_configured);
}

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
  children?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-center gap-3 border-t border-border/60 pt-3">
      <Button
        type="button"
        size="sm"
        className="h-9 text-sm"
        onClick={onActivate}
        disabled={!willSwitch || !ready || busy || disabled}
      >
        {busy ? "Đang chuyển…" : actionText}
      </Button>
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
        <span className="inline-flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400">
          <span className="material-symbols-outlined text-sm">check_circle</span>
          Đã chuyển model
        </span>
      )}
      {error && <span className="text-xs text-destructive">{error}</span>}
    </div>
  );
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
  renderMeta?: (spec: ModelSpec) => ReactNode;
}) {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [settings, setSettings] = useState<Record<string, unknown>>({});
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const savedTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  async function load() {
    try {
      const [cat, s] = await Promise.all([
        api<Catalog>(catalogUrl),
        api<Record<string, unknown>>("/api/settings"),
      ]);
      setCatalog(cat);
      setSettings(s);
      setSelectedId((prev) =>
        prev && cat.specs.some((x) => x.id === prev) ? prev : (cat.active_spec_id ?? cat.specs[0]?.id ?? null),
      );
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : `Failed to load ${title}`);
    }
  }

  useEffect(() => {
    // load() only sets state after awaiting the network, so no cascading render.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
    return () => {
      if (savedTimer.current) clearTimeout(savedTimer.current);
    };
    // Load once per catalog endpoint.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [catalogUrl]);

  const selected = catalog?.specs.find((s) => s.id === selectedId) ?? null;
  const active = catalog?.specs.find((s) => s.id === catalog.active_spec_id) ?? null;
  const willSwitch = !!selected && selected.id !== catalog?.active_spec_id;

  async function activate() {
    if (!selected) return;
    setBusy(true);
    setSaved(false);
    setError("");
    try {
      await api(switchUrl, { method: "POST", body: { model_spec_id: selected.id } });
      await load();
      setSaved(true);
      if (savedTimer.current) clearTimeout(savedTimer.current);
      savedTimer.current = setTimeout(() => setSaved(false), 2500);
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : "Switch failed");
    } finally {
      setBusy(false);
    }
  }

  if (!catalog) {
    return (
      <div className="flex flex-col gap-1 rounded-2xl border border-border/80 bg-card p-6 shadow-lift">
        <p className="text-sm text-muted-foreground">Loading {title}…</p>
        {error && <p className="text-xs text-destructive">{error}</p>}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5 rounded-2xl border border-border/80 bg-card p-6 shadow-lift">
      <div className="flex flex-wrap items-start gap-3">
        <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
          <span className="material-symbols-outlined text-[20px]">{icon}</span>
        </div>
        <div className="min-w-0 flex-1">
          <h2 className="text-base font-semibold tracking-tight text-foreground">{title}</h2>
          <p className="text-xs text-muted-foreground">{description}</p>
        </div>
        <ActiveModelChip spec={active} />
      </div>

      <ProviderModelPicker
        kind={kind}
        specs={catalog.specs}
        activeId={catalog.active_spec_id}
        selectedId={selectedId}
        onSelect={setSelectedId}
        settings={settings}
        onChanged={load}
        renderMeta={renderMeta}
      />

      <ActivateBar
        willSwitch={willSwitch}
        ready={canActivate(selected)}
        busy={busy}
        saved={saved}
        error={error}
        label={selected?.label}
        onActivate={() => void activate()}
      />
    </div>
  );
}
