"use client";

import { useEffect, useState, useRef, useMemo } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api } from "@/lib/api";
import { WikiContent } from "@/components/wiki/wiki-content";

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

function getFileBadgeColor(fileName: string) {
  const ext = fileName.split(".").pop()?.toLowerCase();
  switch (ext) {
    case "pdf":
      return "bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/20";
    case "xlsx":
    case "xls":
    case "csv":
      return "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20";
    case "docx":
    case "doc":
      return "bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20";
    default:
      return "bg-slate-500/10 text-slate-600 dark:text-slate-400 border-slate-500/20";
  }
}

export function DocumentProcessingSettingsCard() {
  // Config state
  const [pdfEngine, setPdfEngine] = useState<string>("pymupdf4llm");
  const [excelEngine, setExcelEngine] = useState<string>("openpyxl");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [saveError, setSaveError] = useState("");

  // Test / Preview state
  const [testFile, setTestFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [testLoading, setTestLoading] = useState(false);
  const [testResult, setTestResult] = useState<ExtractionResponse | null>(null);
  const [selectedPageIndex, setSelectedPageIndex] = useState<number>(0);
  const [viewMode, setViewMode] = useState<"rendered" | "raw">("rendered");
  const [copied, setCopied] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");

  const fileInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    async function loadSettings() {
      setLoading(true);
      setSaveError("");
      try {
        const data = await api<SettingsMap>("/api/settings");
        if (data) {
          if (data.pdf_parser_engine) setPdfEngine(String(data.pdf_parser_engine));
          if (data.excel_parser_engine) setExcelEngine(String(data.excel_parser_engine));
        }
      } catch (err) {
        setSaveError(err instanceof Error ? err.message : "Không thể tải cấu hình");
      } finally {
        setLoading(false);
      }
    }
    void loadSettings();
  }, []);

  async function handleSave() {
    setSaving(true);
    setSaveSuccess(false);
    setSaveError("");

    try {
      await api("/api/settings", {
        method: "PUT",
        body: {
          settings: {
            pdf_parser_engine: pdfEngine,
            excel_parser_engine: excelEngine,
          },
        },
      });
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Lỗi khi lưu cấu hình");
    } finally {
      setSaving(false);
    }
  }

  function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setTestFile(file);
    setTestResult(null);
    setSelectedPageIndex(0);
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (!file) return;
    setTestFile(file);
    setTestResult(null);
    setSelectedPageIndex(0);
  }

  async function handleRunExtraction() {
    if (!testFile) return;
    setTestLoading(true);
    setTestResult(null);

    const formData = new FormData();
    formData.append("file", testFile);
    formData.append("max_pages", "5");
    formData.append("pdf_parser_engine", pdfEngine);
    formData.append("excel_parser_engine", excelEngine);

    try {
      const res = await api<ExtractionResponse>("/api/settings/test-extraction", {
        method: "POST",
        body: formData,
        timeoutMs: 180_000,
      });
      setTestResult(res);
      setSelectedPageIndex(0);
    } catch (err) {
      setTestResult({
        success: false,
        file_name: testFile.name,
        file_type: testFile.name.split(".").pop() || "",
        pages: [],
        error: err instanceof Error ? err.message : "Bóc tách thất bại",
      });
    } finally {
      setTestLoading(false);
    }
  }

  function handleCopy(text: string) {
    void navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  function handleDownloadMarkdown() {
    if (!activePage?.content) return;
    const blob = new Blob([activePage.content], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${testFile?.name || "extracted_page"}_trang_${activePage.page_number}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const activePage = testResult?.pages?.[selectedPageIndex];

  // Optional search highlighting / filtering
  const displayContent = useMemo(() => {
    return activePage?.content || "";
  }, [activePage]);

  return (
    <div className="rounded-2xl border border-border/80 bg-card p-6 shadow-[0_4px_24px_-4px_rgba(0,0,0,0.04)] dark:shadow-[0_4px_24px_-4px_rgba(0,0,0,0.25)] transition-all">
      {/* Header Bar */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between mb-6 pb-4 border-b border-border/60">
        <div className="flex items-center gap-3.5">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20 shadow-xs">
            <span className="material-symbols-outlined text-[26px]">document_scanner</span>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-semibold tracking-tight text-foreground">
                Cấu hình Bóc tách Document
              </h2>
              <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 text-muted-foreground border border-border">
                v2 Engine
              </span>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              Tùy chọn engine bóc tách PDF, Excel và phòng thử nghiệm xem trước trực tiếp.
            </p>
          </div>
        </div>

        {saveSuccess && (
          <Badge
            variant="outline"
            className="text-emerald-600 border-emerald-500/30 bg-emerald-500/10 gap-1.5 self-start sm:self-auto py-1 px-3"
          >
            <span className="material-symbols-outlined text-sm">check_circle</span>
            Đã cập nhật engine
          </Badge>
        )}
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12 text-muted-foreground gap-2.5">
          <span className="material-symbols-outlined animate-spin text-xl text-primary">progress_activity</span>
          <span className="text-xs font-medium">Đang tải thiết lập engine...</span>
        </div>
      ) : (
        /* Layout ngang 1 | 1 Cân đối */
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          {/* CỘT TRÁI (1): CẤU HÌNH & BÀN ĐIỀU KHIỂN (Col span 5/12) */}
          <div className="lg:col-span-5 space-y-5">
            {/* Box 1: Cấu hình Engine */}
            <div className="rounded-xl border border-border/70 bg-muted/20 p-4 space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                  <span className="material-symbols-outlined text-sm text-primary">tune</span>
                  Engine trích xuất mặc định
                </span>
                <Button
                  size="sm"
                  onClick={handleSave}
                  disabled={saving}
                  className="gap-1.5 text-xs font-medium h-7 px-3 shadow-xs active:scale-[0.98] transition-transform"
                >
                  {saving ? (
                    <span className="material-symbols-outlined animate-spin text-xs">progress_activity</span>
                  ) : (
                    <span className="material-symbols-outlined text-xs">save</span>
                  )}
                  Lưu thiết lập
                </Button>
              </div>

              <div className="space-y-3.5">
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between text-xs">
                    <Label htmlFor="pdf-engine-select" className="font-medium text-foreground">
                      Engine PDF
                    </Label>
                    <span className="text-[11px] text-muted-foreground font-mono">.pdf</span>
                  </div>
                  <Select value={pdfEngine} onValueChange={(val) => { if (val) setPdfEngine(val); }}>
                    <SelectTrigger id="pdf-engine-select" className="text-xs h-9 bg-background">
                      <SelectValue placeholder="Chọn engine PDF" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="pymupdf4llm">
                        <div className="flex items-center gap-2">
                          <span className="font-medium">PyMuPDF4LLM</span>
                          <span className="text-[10px] text-muted-foreground">(Bảng biểu, đề mục)</span>
                        </div>
                      </SelectItem>
                      <SelectItem value="pymupdf_plain">
                        <div className="flex items-center gap-2">
                          <span className="font-medium">PDF2text</span>
                          <span className="text-[10px] text-muted-foreground">(PyMuPDF text siêu tốc)</span>
                        </div>
                      </SelectItem>
                      <SelectItem value="markitdown">
                        <div className="flex items-center gap-2">
                          <span className="font-medium">MarkItDown</span>
                          <span className="text-[10px] text-muted-foreground">(Microsoft MD converter)</span>
                        </div>
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-1.5">
                  <div className="flex items-center justify-between text-xs">
                    <Label htmlFor="excel-engine-select" className="font-medium text-foreground">
                      Engine Excel / Bảng tính
                    </Label>
                    <span className="text-[11px] text-muted-foreground font-mono">.xlsx, .xls</span>
                  </div>
                  <Select value={excelEngine} onValueChange={(val) => { if (val) setExcelEngine(val); }}>
                    <SelectTrigger id="excel-engine-select" className="text-xs h-9 bg-background">
                      <SelectValue placeholder="Chọn engine Excel" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="openpyxl">
                        <div className="flex items-center gap-2">
                          <span className="font-medium">OpenPyXL</span>
                          <span className="text-[10px] text-muted-foreground">(Tách từng Sheet & bảng)</span>
                        </div>
                      </SelectItem>
                      <SelectItem value="markitdown">
                        <div className="flex items-center gap-2">
                          <span className="font-medium">MarkItDown</span>
                          <span className="text-[10px] text-muted-foreground">(Markdown tổng hợp)</span>
                        </div>
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              {saveError && (
                <div className="p-2 rounded-lg bg-destructive/10 text-destructive text-[11px] font-medium border border-destructive/20">
                  {saveError}
                </div>
              )}
            </div>

            {/* Box 2: Test Studio Dropzone */}
            <div className="rounded-xl border border-border/70 bg-card p-4 space-y-3.5">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                  <span className="material-symbols-outlined text-sm text-primary">science</span>
                  Phòng thử nghiệm bóc tách
                </span>
                <span className="text-[10px] text-muted-foreground font-mono">Tối đa 5 trang</span>
              </div>

              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.docx,.xlsx,.xls,.csv,.txt,.md"
                className="hidden"
                onChange={handleFileSelect}
              />

              {/* Drag & Drop interactive zone */}
              <div
                onDragOver={(e) => {
                  e.preventDefault();
                  setIsDragging(true);
                }}
                onDragLeave={() => setIsDragging(false)}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                className={`relative group cursor-pointer rounded-xl border-2 border-dashed p-4 transition-all duration-200 text-center flex flex-col items-center justify-center ${
                  isDragging
                    ? "border-primary bg-primary/10 scale-[1.01]"
                    : testFile
                    ? "border-primary/40 bg-primary/5 hover:border-primary/60"
                    : "border-border/80 hover:border-primary/50 hover:bg-muted/30 bg-muted/15"
                }`}
              >
                {testFile ? (
                  <div className="w-full flex items-center justify-between gap-3 text-left">
                    <div className="flex items-center gap-3 overflow-hidden">
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-background border border-border/80 shadow-xs">
                        <span className="material-symbols-outlined text-xl text-primary">
                          description
                        </span>
                      </div>
                      <div className="min-w-0">
                        <div className="flex items-center gap-1.5">
                          <Badge
                            variant="outline"
                            className={`text-[9px] uppercase px-1.5 py-0 font-mono ${getFileBadgeColor(testFile.name)}`}
                          >
                            {testFile.name.split(".").pop()}
                          </Badge>
                          <p className="text-xs font-medium text-foreground truncate max-w-[170px]">
                            {testFile.name}
                          </p>
                        </div>
                        <p className="text-[11px] text-muted-foreground mt-0.5">
                          {(testFile.size / 1024).toFixed(1)} KB • Nhấn để đổi file
                        </p>
                      </div>
                    </div>

                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        setTestFile(null);
                        setTestResult(null);
                      }}
                      className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/80 transition-colors"
                      title="Gỡ file"
                    >
                      <span className="material-symbols-outlined text-base">close</span>
                    </button>
                  </div>
                ) : (
                  <div className="py-2 flex flex-col items-center">
                    <div className="flex h-9 w-9 items-center justify-center rounded-full bg-primary/10 text-primary mb-2 group-hover:scale-110 transition-transform">
                      <span className="material-symbols-outlined text-xl">upload_file</span>
                    </div>
                    <p className="text-xs font-semibold text-foreground">
                      Kéo thả file vào đây hoặc bấm để chọn
                    </p>
                    <p className="text-[11px] text-muted-foreground mt-1">
                      Hỗ trợ: PDF, Word (.docx), Excel (.xlsx, .csv), TXT, Markdown
                    </p>
                  </div>
                )}
              </div>

              {/* Action Button */}
              <Button
                size="sm"
                onClick={handleRunExtraction}
                disabled={!testFile || testLoading}
                className="w-full gap-2 text-xs font-medium h-9 shadow-xs active:scale-[0.98] transition-all"
              >
                {testLoading ? (
                  <>
                    <span className="material-symbols-outlined animate-spin text-sm">progress_activity</span>
                    Đang bóc tách dữ liệu...
                  </>
                ) : (
                  <>
                    <span className="material-symbols-outlined text-sm">play_arrow</span>
                    Bóc tách &amp; Xem trước ngay
                  </>
                )}
              </Button>

              {testResult?.error && (
                <div className="p-3 rounded-lg border border-destructive/20 bg-destructive/10 text-destructive text-xs flex items-start gap-2">
                  <span className="material-symbols-outlined text-base shrink-0 mt-0.5">error</span>
                  <div className="space-y-1">
                    <p className="font-semibold">Thử nghiệm thất bại</p>
                    <p className="font-mono text-[11px] opacity-90 break-all">{testResult.error}</p>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* CỘT PHẢI (2): STUDIO XEM TRƯỚC (Col span 7/12) */}
          <div className="lg:col-span-7 flex flex-col h-full space-y-3">
            {/* Workbench Frame */}
            <div
              className={`rounded-xl border border-border/80 bg-card overflow-hidden shadow-xs flex flex-col transition-all duration-200 ${
                isExpanded ? "fixed inset-4 z-50 shadow-2xl bg-background" : "min-h-[460px]"
              }`}
            >
              {/* Studio Header Toolbar */}
              <div className="flex flex-wrap items-center justify-between gap-2 px-3.5 py-2.5 bg-muted/40 border-b border-border/70 text-xs select-none">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-foreground flex items-center gap-1.5">
                    <span className="material-symbols-outlined text-base text-primary">preview</span>
                    Studio Xem trước
                  </span>

                  {testResult?.success && (
                    <Badge
                      variant="outline"
                      className="border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 gap-1 text-[10px] h-5 font-medium"
                    >
                      <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
                      Hoàn tất
                    </Badge>
                  )}
                </div>

                {/* Right controls */}
                <div className="flex items-center gap-1.5">
                  {/* Mode switcher */}
                  <div className="flex rounded-md border border-border/80 p-0.5 bg-background shadow-2xs">
                    <button
                      onClick={() => setViewMode("rendered")}
                      className={`px-2.5 py-0.5 rounded text-[11px] font-medium transition-all ${
                        viewMode === "rendered"
                          ? "bg-primary text-primary-foreground shadow-xs font-semibold"
                          : "text-muted-foreground hover:text-foreground"
                      }`}
                      title="Chế độ trực quan"
                    >
                      Rendered
                    </button>
                    <button
                      onClick={() => setViewMode("raw")}
                      className={`px-2.5 py-0.5 rounded text-[11px] font-medium transition-all ${
                        viewMode === "raw"
                          ? "bg-primary text-primary-foreground shadow-xs font-semibold"
                          : "text-muted-foreground hover:text-foreground"
                      }`}
                      title="Chế độ mã nguồn văn bản"
                    >
                      Raw
                    </button>
                  </div>

                  {activePage && (
                    <>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleCopy(activePage.content)}
                        className="h-7 text-xs px-2 gap-1 text-muted-foreground hover:text-foreground"
                        title="Sao chép nội dung trang này"
                      >
                        <span className="material-symbols-outlined text-sm">
                          {copied ? "check" : "content_copy"}
                        </span>
                        {copied ? "Đã chép" : "Copy"}
                      </Button>

                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={handleDownloadMarkdown}
                        className="h-7 text-xs px-2 gap-1 text-muted-foreground hover:text-foreground"
                        title="Tải về file Markdown (.md)"
                      >
                        <span className="material-symbols-outlined text-sm">download</span>
                        Tải .md
                      </Button>
                    </>
                  )}

                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setIsExpanded(!isExpanded)}
                    className="h-7 w-7 p-0 text-muted-foreground hover:text-foreground"
                    title={isExpanded ? "Thu nhỏ" : "Toàn màn hình"}
                  >
                    <span className="material-symbols-outlined text-sm">
                      {isExpanded ? "close_fullscreen" : "open_in_full"}
                    </span>
                  </Button>
                </div>
              </div>

              {/* Telemetry bar (Stats pills) */}
              {testResult?.success && testResult.stats && (
                <div className="flex flex-wrap items-center justify-between gap-2 px-3.5 py-1.5 bg-muted/20 border-b border-border/50 text-[11px] font-mono text-muted-foreground">
                  <div className="flex items-center gap-3">
                    <span className="flex items-center gap-1">
                      <span className="material-symbols-outlined text-[13px] text-muted-foreground">timer</span>
                      {(testResult.stats.latency_ms / 1000).toFixed(2)}s
                    </span>
                    <span>•</span>
                    <span className="flex items-center gap-1">
                      <span className="material-symbols-outlined text-[13px] text-muted-foreground">article</span>
                      {testResult.stats.preview_pages_count}/{testResult.stats.total_pages} trang
                    </span>
                    <span>•</span>
                    <span className="flex items-center gap-1">
                      <span className="material-symbols-outlined text-[13px] text-muted-foreground">format_quote</span>
                      {testResult.stats.total_words.toLocaleString()} từ ({testResult.stats.total_chars.toLocaleString()} ký tự)
                    </span>
                  </div>

                  <span className="px-2 py-0.2 rounded bg-background border border-border/60 text-[10px] text-foreground font-semibold">
                    Engine: {pdfEngine}
                  </span>
                </div>
              )}

              {/* Multi-page / multi-sheet tabs */}
              {testResult?.pages && testResult.pages.length > 1 && (
                <div className="flex items-center gap-1 px-3 py-1.5 bg-muted/10 border-b border-border/50 overflow-x-auto">
                  <span className="text-[10px] uppercase font-semibold text-muted-foreground mr-1.5 tracking-wider shrink-0">
                    Trang:
                  </span>
                  {testResult.pages.map((p, idx) => (
                    <button
                      key={p.page_number}
                      onClick={() => setSelectedPageIndex(idx)}
                      className={`px-2.5 py-1 rounded-md text-xs font-medium whitespace-nowrap transition-all flex items-center gap-1 ${
                        selectedPageIndex === idx
                          ? "bg-primary text-primary-foreground shadow-xs font-semibold"
                          : "bg-muted/40 hover:bg-muted text-muted-foreground hover:text-foreground"
                      }`}
                    >
                      <span>Trang {p.page_number}</span>
                      {p.is_ocr && (
                        <span className="text-[9px] px-1 py-0 rounded bg-blue-500/20 text-blue-300 font-mono">
                          OCR
                        </span>
                      )}
                    </button>
                  ))}
                </div>
              )}

              {/* Studio Canvas / Viewport */}
              <div
                className={`relative flex-1 p-4 overflow-y-auto transition-all ${
                  isExpanded ? "max-h-[calc(100vh-140px)]" : "max-h-[380px]"
                }`}
              >
                {testLoading ? (
                  /* Animated High-tech Scanning State */
                  <div className="h-full min-h-[300px] flex flex-col items-center justify-center p-6 text-center space-y-4">
                    <div className="relative w-20 h-20 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center overflow-hidden shadow-inner">
                      <span className="material-symbols-outlined text-4xl text-primary animate-pulse">
                        document_scanner
                      </span>
                      {/* Scanning laser beam */}
                      <div className="absolute inset-x-0 h-1 bg-gradient-to-r from-transparent via-cyan-400 to-transparent shadow-[0_0_12px_rgba(6,182,212,0.8)] animate-[scan_2s_ease-in-out_infinite]" />
                    </div>
                    <div className="space-y-1">
                      <p className="text-xs font-semibold text-foreground">
                        Đang phân tích cấu trúc tài liệu...
                      </p>
                      <p className="text-[11px] text-muted-foreground">
                        Trích xuất bảng biểu, đề mục pháp lý và văn bản Markdown
                      </p>
                    </div>
                  </div>
                ) : testResult?.success && activePage ? (
                  viewMode === "rendered" ? (
                    <div className="prose prose-sm dark:prose-invert max-w-none text-xs leading-relaxed">
                      <WikiContent markdown={displayContent} />
                    </div>
                  ) : (
                    <div className="rounded-lg bg-slate-950 p-4 font-mono text-[11px] leading-relaxed text-slate-200 overflow-x-auto border border-slate-800 shadow-inner">
                      <pre className="whitespace-pre-wrap break-words">{displayContent}</pre>
                    </div>
                  )
                ) : (
                  /* Empty State Workbench Canvas */
                  <div className="h-full min-h-[320px] flex flex-col items-center justify-center text-center p-6 text-muted-foreground">
                    <div className="w-14 h-14 rounded-2xl bg-muted/40 border border-border flex items-center justify-center mb-3 text-muted-foreground/60 shadow-xs">
                      <span className="material-symbols-outlined text-3xl">find_in_page</span>
                    </div>
                    <p className="text-xs font-semibold text-foreground">Chưa có dữ liệu xem trước</p>
                    <p className="text-[11px] text-muted-foreground mt-1 max-w-[280px]">
                      Chọn hoặc kéo thả file tài liệu ở cột bên trái và bấm &quot;Bóc tách &amp; Xem trước&quot; để hiển thị kết quả tại đây.
                    </p>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
