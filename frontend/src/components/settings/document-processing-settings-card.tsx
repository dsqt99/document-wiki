"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";
import { PreviewStudio, Stat, TestFileDropzone } from "./test-lab";

type SettingsMap = Record<string, string | null | undefined>;

type PageItem = {
  page_number: number;
  content: string;
  is_ocr: boolean;
  char_count: number;
  word_count: number;
};

type ExtractionStats = {
  total_pages: number;
  preview_pages_count: number;
  ocr_pages_count: number;
  total_words: number;
  total_chars: number;
  latency_ms: number;
};

type ExtractionResponse = {
  success: boolean;
  file_name: string;
  file_type: string;
  stats?: ExtractionStats;
  pages: PageItem[];
  error?: string | null;
};

type Config = {
  pdfEngine: string;
  excelEngine: string;
  ocrMode: string;
  strip: boolean;
  enhance: boolean;
};

type Option = { value: string; label: string; hint: string };

const PDF_ENGINES: Option[] = [
  { value: "pymupdf4llm", label: "PyMuPDF4LLM", hint: "Giữ bảng biểu, đề mục" },
  { value: "pymupdf_plain", label: "PDF2text", hint: "Text thuần, nhanh nhất" },
  { value: "markitdown", label: "MarkItDown", hint: "Bộ chuyển Markdown của Microsoft" },
];

const EXCEL_ENGINES: Option[] = [
  { value: "openpyxl", label: "OpenPyXL", hint: "Tách từng sheet & bảng" },
  { value: "markitdown", label: "MarkItDown", hint: "Markdown tổng hợp" },
];

const OCR_MODES: Option[] = [
  { value: "auto", label: "Tự động", hint: "OCR trang không có lớp text" },
  { value: "force_ocr", label: "Luôn OCR", hint: "OCR mọi trang PDF" },
  { value: "disabled", label: "Tắt", hint: "Chỉ lấy lớp text" },
];

const MAX_PAGES = [1, 3, 5, 10];

const DEFAULT_CONFIG: Config = {
  pdfEngine: "pymupdf4llm",
  excelEngine: "openpyxl",
  ocrMode: "auto",
  strip: true,
  enhance: true,
};

function fileKind(name: string): "pdf" | "excel" | "other" {
  const ext = name.split(".").pop()?.toLowerCase();
  if (ext === "pdf") return "pdf";
  if (ext === "xlsx" || ext === "xls" || ext === "csv") return "excel";
  return "other";
}

function OptionGroup({
  label,
  scope,
  options,
  value,
  onChange,
}: {
  label: string;
  scope: string;
  options: Option[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-xs">
        <span className="font-medium text-foreground">{label}</span>
        <span className="font-mono text-[11px] text-muted-foreground">{scope}</span>
      </div>
      <div className="grid gap-1.5" style={{ gridTemplateColumns: `repeat(${options.length}, minmax(0, 1fr))` }}>
        {options.map((o) => {
          const on = o.value === value;
          return (
            <button
              key={o.value}
              type="button"
              onClick={() => onChange(o.value)}
              aria-pressed={on}
              className={`rounded-lg border px-2.5 py-2 text-left transition-colors ${
                on
                  ? "border-primary bg-primary/10 ring-1 ring-primary/30"
                  : "border-border bg-background hover:border-primary/40 hover:bg-muted/40"
              }`}
            >
              <span className={`block text-xs font-semibold ${on ? "text-primary" : "text-foreground"}`}>
                {o.label}
              </span>
              <span className="mt-0.5 block text-[10px] leading-tight text-muted-foreground">{o.hint}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function SwitchRow({
  label,
  hint,
  checked,
  onChange,
}: {
  label: string;
  hint: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex cursor-pointer items-center justify-between gap-3 rounded-lg border border-border bg-background px-3 py-2">
      <span className="min-w-0">
        <span className="block text-xs font-medium text-foreground">{label}</span>
        <span className="block text-[10px] text-muted-foreground">{hint}</span>
      </span>
      <Switch checked={checked} onCheckedChange={(v) => onChange(!!v)} />
    </label>
  );
}

export function DocumentProcessingSettingsCard() {
  const [config, setConfig] = useState<Config>(DEFAULT_CONFIG);
  const [savedConfig, setSavedConfig] = useState<Config>(DEFAULT_CONFIG);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [saveError, setSaveError] = useState("");

  const [testFile, setTestFile] = useState<File | null>(null);
  const [maxPages, setMaxPages] = useState(3);
  const [testLoading, setTestLoading] = useState(false);
  const [testResult, setTestResult] = useState<ExtractionResponse | null>(null);
  const [testedWith, setTestedWith] = useState<Config | null>(null);
  const [pageIndex, setPageIndex] = useState(0);

  useEffect(() => {
    async function load() {
      try {
        const data = await api<SettingsMap>("/api/settings");
        const next: Config = {
          pdfEngine: data.pdf_parser_engine || DEFAULT_CONFIG.pdfEngine,
          excelEngine: data.excel_parser_engine || DEFAULT_CONFIG.excelEngine,
          ocrMode: data.ocr_mode || DEFAULT_CONFIG.ocrMode,
          strip: data.pdf_strip_headers_footers !== "false",
          enhance: data.pdf_enhance_headings !== "false",
        };
        setConfig(next);
        setSavedConfig(next);
      } catch (err) {
        setSaveError(err instanceof Error ? err.message : "Không thể tải cấu hình");
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, []);

  const dirty = JSON.stringify(config) !== JSON.stringify(savedConfig);

  function patch(p: Partial<Config>) {
    setConfig((c) => ({ ...c, ...p }));
    setSaveSuccess(false);
  }

  async function handleSave() {
    setSaving(true);
    setSaveSuccess(false);
    setSaveError("");
    try {
      await api("/api/settings", {
        method: "PUT",
        body: {
          settings: {
            pdf_parser_engine: config.pdfEngine,
            excel_parser_engine: config.excelEngine,
            ocr_mode: config.ocrMode,
            pdf_strip_headers_footers: String(config.strip),
            pdf_enhance_headings: String(config.enhance),
          },
        },
      });
      setSavedConfig(config);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 2500);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Lỗi khi lưu cấu hình");
    } finally {
      setSaving(false);
    }
  }

  async function handleRun() {
    if (!testFile) return;
    setTestLoading(true);
    setTestResult(null);
    const used = config;

    const formData = new FormData();
    formData.append("file", testFile);
    formData.append("max_pages", String(maxPages));
    formData.append("pdf_parser_engine", used.pdfEngine);
    formData.append("excel_parser_engine", used.excelEngine);
    formData.append("ocr_mode", used.ocrMode);
    formData.append("strip_headers_footers", String(used.strip));
    formData.append("enhance_headings", String(used.enhance));

    try {
      const res = await api<ExtractionResponse>("/api/settings/test-extraction", {
        method: "POST",
        body: formData,
        timeoutMs: 180_000,
      });
      setTestResult(res);
    } catch (err) {
      setTestResult({
        success: false,
        file_name: testFile.name,
        file_type: testFile.name.split(".").pop() || "",
        pages: [],
        error: err instanceof Error ? err.message : "Bóc tách thất bại",
      });
    } finally {
      setTestedWith(used);
      setPageIndex(0);
      setTestLoading(false);
    }
  }

  const activePage = testResult?.success ? testResult.pages[pageIndex] : undefined;
  const kind = testFile ? fileKind(testFile.name) : "other";
  const resultKind = testResult ? fileKind(testResult.file_name) : "other";
  const engineLabel =
    testedWith &&
    (resultKind === "pdf"
      ? PDF_ENGINES.find((e) => e.value === testedWith.pdfEngine)?.label
      : resultKind === "excel"
        ? EXCEL_ENGINES.find((e) => e.value === testedWith.excelEngine)?.label
        : "Mặc định");
  const stats = testResult?.success ? testResult.stats : undefined;

  return (
    <div className="rounded-2xl border border-border/80 bg-card p-6 shadow-sahara flex flex-col gap-5">
      {/* Header */}
      <div className="flex flex-wrap items-start gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-blue-500/20 bg-blue-500/10 text-blue-600 dark:text-blue-400">
          <span className="material-symbols-outlined text-[22px]">document_scanner</span>
        </div>
        <div className="min-w-0 flex-1">
          <h2 className="text-base font-semibold tracking-tight text-foreground">Bóc tách tài liệu</h2>
          <p className="text-xs text-muted-foreground">
            Engine chuyển PDF / Excel sang Markdown và cách xử lý trang scan khi upload.
          </p>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center gap-2.5 py-10 text-muted-foreground">
          <span className="material-symbols-outlined animate-spin text-xl text-primary">progress_activity</span>
          <span className="text-xs font-medium">Đang tải thiết lập...</span>
        </div>
      ) : (
        <>
          {/* Config */}
          <div className="rounded-xl border border-border/70 bg-muted/20 p-4 space-y-4">
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <OptionGroup
                label="Engine PDF"
                scope=".pdf"
                options={PDF_ENGINES}
                value={config.pdfEngine}
                onChange={(v) => patch({ pdfEngine: v })}
              />
              <OptionGroup
                label="Engine bảng tính"
                scope=".xlsx .xls .csv"
                options={EXCEL_ENGINES}
                value={config.excelEngine}
                onChange={(v) => patch({ excelEngine: v })}
              />
              <OptionGroup
                label="OCR trang scan"
                scope="PDF"
                options={OCR_MODES}
                value={config.ocrMode}
                onChange={(v) => patch({ ocrMode: v })}
              />
              <div className="space-y-1.5">
                <span className="block text-xs font-medium text-foreground">Hậu xử lý PDF</span>
                <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
                  <SwitchRow
                    label="Bỏ header / footer"
                    hint="Lọc dòng lặp lại đầu/cuối trang"
                    checked={config.strip}
                    onChange={(v) => patch({ strip: v })}
                  />
                  <SwitchRow
                    label="Nhận diện đề mục"
                    hint="Chương, Điều, Mục → heading"
                    checked={config.enhance}
                    onChange={(v) => patch({ enhance: v })}
                  />
                </div>
              </div>
            </div>

            <div className="flex flex-wrap items-center justify-end gap-3 border-t border-border/60 pt-3">
              {saveError && <span className="mr-auto text-xs text-destructive">{saveError}</span>}
              {saveSuccess && (
                <span className="flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400">
                  <span className="material-symbols-outlined text-sm">check_circle</span>
                  Đã lưu
                </span>
              )}
              {dirty && !saveSuccess && (
                <span className="text-[11px] text-amber-600 dark:text-amber-400">Có thay đổi chưa lưu</span>
              )}
              {dirty && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setConfig(savedConfig)}
                  className="h-8 text-xs"
                >
                  Hoàn tác
                </Button>
              )}
              <Button size="sm" onClick={handleSave} disabled={saving || !dirty} className="h-8 gap-1.5 text-xs">
                <span className={`material-symbols-outlined text-sm ${saving ? "animate-spin" : ""}`}>
                  {saving ? "progress_activity" : "save"}
                </span>
                Lưu thiết lập
              </Button>
            </div>
          </div>

          {/* Test lab */}
          <div className="rounded-xl border border-border/70 bg-muted/10 p-4">
            <div className="mb-3 flex items-center justify-between gap-2">
              <span className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                <span className="material-symbols-outlined text-sm text-primary">science</span>
                Thử bóc tách
              </span>
              <span className="text-[11px] text-muted-foreground">Dùng thiết lập đang chọn ở trên (kể cả chưa lưu)</span>
            </div>
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
              <div className="flex flex-col gap-3 lg:col-span-4">
                <TestFileDropzone
                  file={testFile}
                  onFile={(f) => {
                    setTestFile(f);
                    setTestResult(null);
                  }}
                  onClear={() => {
                    setTestFile(null);
                    setTestResult(null);
                  }}
                  accept=".pdf,.docx,.xlsx,.xls,.csv,.txt,.md"
                  hint="PDF, Word, Excel/CSV, TXT, Markdown"
                />

                <div className="flex items-center justify-between rounded-lg border border-border bg-background p-2 text-xs">
                  <span className="font-medium text-muted-foreground">Số trang xem trước</span>
                  <div className="flex rounded-md border border-border/80 p-0.5">
                    {MAX_PAGES.map((n) => (
                      <button
                        key={n}
                        type="button"
                        onClick={() => setMaxPages(n)}
                        className={`min-w-7 rounded px-2 py-0.5 font-mono text-[11px] font-medium transition-colors ${
                          maxPages === n
                            ? "bg-primary text-primary-foreground"
                            : "text-muted-foreground hover:text-foreground"
                        }`}
                      >
                        {n}
                      </button>
                    ))}
                  </div>
                </div>

                {testFile && (
                  <p className="flex items-center gap-1 text-[11px] text-muted-foreground">
                    <span className="material-symbols-outlined text-sm">settings_suggest</span>
                    {kind === "pdf"
                      ? `${PDF_ENGINES.find((e) => e.value === config.pdfEngine)?.label} · OCR ${
                          OCR_MODES.find((m) => m.value === config.ocrMode)?.label.toLowerCase()
                        }`
                      : kind === "excel"
                        ? EXCEL_ENGINES.find((e) => e.value === config.excelEngine)?.label
                        : "Bộ đọc mặc định theo định dạng"}
                  </p>
                )}

                <Button
                  size="sm"
                  onClick={handleRun}
                  disabled={!testFile || testLoading}
                  className="h-9 w-full gap-2 text-xs font-medium"
                >
                  <span className={`material-symbols-outlined text-sm ${testLoading ? "animate-spin" : ""}`}>
                    {testLoading ? "progress_activity" : "play_arrow"}
                  </span>
                  {testLoading ? "Đang bóc tách..." : "Bóc tách & xem trước"}
                </Button>
              </div>

              <div className="lg:col-span-8">
                <PreviewStudio
                  title="Xem trước"
                  icon="preview"
                  loading={testLoading}
                  loadingTitle="Đang phân tích cấu trúc tài liệu..."
                  content={activePage ? activePage.content : testResult?.success ? "" : null}
                  error={testResult && !testResult.success ? testResult.error || "Bóc tách thất bại" : null}
                  successLabel={testResult?.success ? "Hoàn tất" : null}
                  telemetry={
                    stats ? (
                      <>
                        <Stat icon="timer">{(stats.latency_ms / 1000).toFixed(2)}s</Stat>
                        <Stat icon="article">
                          {stats.preview_pages_count}/{stats.total_pages} trang
                        </Stat>
                        {stats.ocr_pages_count > 0 && (
                          <Stat icon="photo_camera">{stats.ocr_pages_count} trang OCR</Stat>
                        )}
                        <Stat icon="format_quote">
                          {stats.total_words.toLocaleString()} từ · {stats.total_chars.toLocaleString()} ký tự
                        </Stat>
                        {engineLabel && (
                          <span className="ml-auto rounded border border-border/60 bg-background px-2 text-[10px] font-semibold text-foreground">
                            {engineLabel}
                          </span>
                        )}
                      </>
                    ) : null
                  }
                  tabs={testResult?.pages.map((p, i) => ({
                    key: String(i),
                    label: `Trang ${p.page_number}`,
                    badge: p.is_ocr ? "OCR" : undefined,
                  }))}
                  activeTab={String(pageIndex)}
                  onTab={(k) => setPageIndex(Number(k))}
                  downloadName={`${testFile?.name || "extracted"}_trang_${activePage?.page_number ?? 1}.md`}
                  emptyTitle="Chưa có dữ liệu xem trước"
                  emptyHint="Chọn file bên trái rồi bấm “Bóc tách & xem trước”."
                />
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
