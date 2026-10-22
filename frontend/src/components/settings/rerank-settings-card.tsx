"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";
import { ModelCatalogCard } from "./model-catalog-card";

type TestResult = { success: boolean; latency_ms: number; message?: string; results?: { index: number; score: number; text: string }[] };

export function RerankSettingsCard() {
  return <ModelCatalogCard title="Rerank tìm kiếm Wiki" icon="sort" kind="rerank"
    description="Xếp hạng lại nội dung tìm được bằng model riêng, rồi lọc theo ngưỡng điểm. Không đổi model LLM đang dùng."
    catalogUrl="/api/settings/rerank/catalog" switchUrl="/api/settings/rerank/switch"
    renderMeta={(spec) => <span>{spec.protocol === "rerank" || spec.id === "legacy/http" ? "Rerank API chuyên dụng" : "LLM chấm mức liên quan 0–1"}</span>}
    renderControls={(selected) => <Controls selectedId={selected?.id ?? null} />} />;
}

function Controls({ selectedId }: { selectedId: string | null }) {
  const [form, setForm] = useState<{ enabled: boolean; threshold: string } | null>(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [testing, setTesting] = useState(false);
  const [tested, setTested] = useState<{ id: string; result: TestResult } | null>(null);
  const test = tested?.id === selectedId ? tested.result : null;

  useEffect(() => {
    let cancelled = false;
    api<Record<string, string | null>>("/api/settings").then((s) => {
      if (!cancelled) setForm({ enabled: s.wiki_rerank_enabled !== "false", threshold: s.wiki_rerank_threshold ?? "0.3" });
    }).catch((e: unknown) => { if (!cancelled) setError(e instanceof Error ? e.message : "Không tải được cấu hình tìm kiếm"); });
    return () => { cancelled = true; };
  }, []);

  async function save() {
    if (!form || !form.threshold.trim() || !Number.isFinite(Number(form.threshold))) return;
    setSaving(true); setError(""); setSaved(false);
    try {
      await api("/api/settings", { method: "PUT", body: { settings: {
        wiki_rerank_enabled: String(form.enabled), wiki_rerank_threshold: form.threshold,
      } } });
      setSaved(true);
    } catch (e) { setError(e instanceof Error ? e.message : "Không lưu được ngưỡng"); }
    finally { setSaving(false); }
  }

  async function runTest() {
    if (!selectedId) return;
    setTesting(true); setError("");
    const id = selectedId;
    try {
      const result = await api<TestResult>("/api/settings/rerank/test", { method: "POST", body: { model_spec_id: id } });
      setTested({ id, result });
    } catch (e) { setError(e instanceof Error ? e.message : "Không gọi được model"); }
    finally { setTesting(false); }
  }

  return <div className="space-y-4 border-t pt-4">
    {form && <>
      <label className="flex items-center justify-between gap-3 text-sm font-medium">
        Áp dụng rerank khi tìm Wiki
        <Switch checked={form.enabled} onCheckedChange={(enabled) => { setForm({ ...form, enabled }); setSaved(false); }} />
      </label>
      <div className="flex flex-wrap items-end gap-3">
        <label className="space-y-1.5 text-xs font-medium">Ngưỡng điểm tối thiểu
          <Input type="number" step="0.05" value={form.threshold} className="mt-1.5 w-40"
            onChange={(e) => { setForm({ ...form, threshold: e.target.value }); setSaved(false); }} />
        </label>
        <Button size="sm" variant="outline" disabled={saving || !form.threshold.trim() || !Number.isFinite(Number(form.threshold))} onClick={() => void save()}>{saving ? "Đang lưu…" : "Lưu cấu hình tìm kiếm"}</Button>
        {saved && <span role="status" className="text-xs text-emerald-700 dark:text-emerald-400">Đã lưu</span>}
      </div>
      <p className="text-xs leading-relaxed text-muted-foreground">Chỉ trả điểm lớn hơn ngưỡng, không tự hạ ngưỡng. Điểm dùng thang của model; cần thử lại ngưỡng khi đổi model. Nếu model lỗi, trả hybrid kèm cảnh báo “Chưa rerank”.</p>
    </>}
    <div className="space-y-3">
      <Button size="sm" variant="outline" disabled={!selectedId || testing} onClick={() => void runTest()}>{testing ? "Đang chấm điểm…" : "Thử model đang chọn"}</Button>
      {test && <div aria-live="polite" className="space-y-2 text-xs">
        <p className={test.success ? "text-emerald-700 dark:text-emerald-400" : "text-destructive"}>{test.success ? `Đã chấm điểm · ${test.latency_ms} ms · Truy vấn: Thủ tục đăng ký xe` : test.message}</p>
        {test.results?.map((r) => <div key={r.index} className="flex gap-3 border-b py-2"><span className="w-16 shrink-0 font-mono tabular-nums">{r.score.toFixed(4)}</span><span>{r.text}</span></div>)}
      </div>}
    </div>
    {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
  </div>;
}
