"use client";

import { useState, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api } from "@/lib/api";
import { WikiContent } from "@/components/wiki/wiki-content";

type OCRResponse = {
  success: boolean;
  text: string;
  model: string;
  latency_ms: number;
  chars_count: number;
  words_count: number;
  error?: string | null;
};

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

export function ExtractionPlaygroundCard() {
  // --- Tab 1: OCR Test state ---
  const [ocrFile, setOcrFile] = useState<File | null>(null);
  const [ocrPreviewUrl, setOcrPreviewUrl] = useState<string | null>(null);
  const [ocrLoading, setOcrLoading] = useState(false);
  const [ocrResult, setOcrResult] = useState<OCRResponse | null>(null);
  const [ocrViewMode, setOcrViewMode] = useState<"rendered" | "raw">("rendered");
  const [ocrCopied, setOcrCopied] = useState(false);

  // --- Tab 2: Document Extraction state ---
  const [docFile, setDocFile] = useState<File | null>(null);
  const [maxPages, setMaxPages] = useState<string>("3");
  const [docEngine, setDocEngine] = useState<string>("default");
  const [docOcrMode, setDocOcrMode] = useState<string>("default");
  const [docLoading, setDocLoading] = useState(false);
  const [docResult, setDocResult] = useState<ExtractionResponse | null>(null);
  const [selectedPageIndex, setSelectedPageIndex] = useState<number>(0);
  const [docViewMode, setDocViewMode] = useState<"rendered" | "raw">("rendered");
  const [docCopied, setDocCopied] = useState(false);

  const ocrInputRef = useRef<HTMLInputElement | null>(null);
  const docInputRef = useRef<HTMLInputElement | null>(null);

  // --- Handlers for OCR ---
  function handleOcrFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setOcrFile(file);
    setOcrResult(null);

    if (file.type.startsWith("image/")) {
      const url = URL.createObjectURL(file);
      setOcrPreviewUrl(url);
    } else {
      setOcrPreviewUrl(null);
    }
  }

  async function runOcrTest() {
    if (!ocrFile) return;
    setOcrLoading(true);
    setOcrResult(null);

    const formData = new FormData();
    formData.append("file", ocrFile);

    try {
      const res = await api<OCRResponse>("/api/settings/test-ocr", {
        method: "POST",
        body: formData,
        timeoutMs: 180_000,
      });
      setOcrResult(res);
    } catch (err) {
      setOcrResult({
        success: false,
        text: "",
        model: "",
        latency_ms: 0,
        chars_count: 0,
        words_count: 0,
        error: err instanceof Error ? err.message : "Yêu cầu OCR thất bại",
      });
    } finally {
      setOcrLoading(false);
    }
  }

  function copyOcrText() {
    if (!ocrResult?.text) return;
    void navigator.clipboard.writeText(ocrResult.text);
    setOcrCopied(true);
    setTimeout(() => setOcrCopied(false), 2000);
  }

  // --- Handlers for Document Extraction ---
  function handleDocFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setDocFile(file);
    setDocResult(null);
    setSelectedPageIndex(0);
  }

  async function runDocExtractionTest() {
    if (!docFile) return;
    setDocLoading(true);
    setDocResult(null);

    const formData = new FormData();
    formData.append("file", docFile);
    formData.append("max_pages", maxPages);
    if (docEngine !== "default") formData.append("engine", docEngine);
    if (docOcrMode !== "default") formData.append("ocr_mode", docOcrMode);

    try {
      const res = await api<ExtractionResponse>("/api/settings/test-extraction", {
        method: "POST",
        body: formData,
        timeoutMs: 300_000,
      });
      setDocResult(res);
      setSelectedPageIndex(0);
    } catch (err) {
      setDocResult({
        success: false,
        file_name: docFile.name,
        file_type: docFile.name.split(".").pop() || "",
        pages: [],
        error: err instanceof Error ? err.message : "Trích xuất thất bại",
      });
    } finally {
      setDocLoading(false);
    }
  }

  function copyPageText(text: string) {
    void navigator.clipboard.writeText(text);
    setDocCopied(true);
    setTimeout(() => setDocCopied(false), 2000);
  }

  const activePage = docResult?.pages?.[selectedPageIndex];

  return (
    <div className="rounded-xl border border-border bg-card p-6 shadow-sm">
      <div className="flex flex-col gap-1 mb-6 pb-4 border-b border-border">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
            <span className="material-symbols-outlined text-2xl">preview</span>
          </div>
          <div>
            <h2 className="text-lg font-semibold tracking-tight">
              Khu vực Thử nghiệm & Xem trước (Extraction Playground)
            </h2>
            <p className="text-sm text-muted-foreground">
              Kiểm tra nhanh chất lượng bóc tách tài liệu và tốc độ mô hình OCR trực tiếp trên giao diện.
            </p>
          </div>
        </div>
      </div>

      <Tabs defaultValue="doc" className="space-y-6">
        <TabsList className="grid w-full grid-cols-2 max-w-md h-10">
          <TabsTrigger value="doc" className="text-xs font-medium gap-2">
            <span className="material-symbols-outlined text-base">description</span>
            Trích xuất Tài liệu (Document Preview)
          </TabsTrigger>
          <TabsTrigger value="ocr" className="text-xs font-medium gap-2">
            <span className="material-symbols-outlined text-base">image</span>
            Test OCR Nhanh (Ảnh / PDF 1 trang)
          </TabsTrigger>
        </TabsList>

        {/* TAB 1: DOCUMENT PREVIEW */}
        <TabsContent value="doc" className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* Left Upload & Options */}
            <div className="space-y-4">
              <div
                onClick={() => docInputRef.current?.click()}
                className="border-2 border-dashed border-border hover:border-primary/50 transition-colors rounded-xl p-6 flex flex-col items-center justify-center text-center cursor-pointer bg-muted/20 hover:bg-muted/30"
              >
                <input
                  ref={docInputRef}
                  type="file"
                  accept=".pdf,.docx,.xlsx,.csv,.txt,.md"
                  className="hidden"
                  onChange={handleDocFileSelect}
                />
                <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary mb-3">
                  <span className="material-symbols-outlined text-2xl">upload_file</span>
                </div>
                {docFile ? (
                  <div className="space-y-1">
                    <p className="text-xs font-semibold text-foreground truncate max-w-[200px]">
                      {docFile.name}
                    </p>
                    <p className="text-[11px] text-muted-foreground">
                      {(docFile.size / 1024).toFixed(1)} KB • Nhấn để đổi file
                    </p>
                  </div>
                ) : (
                  <div className="space-y-1">
                    <p className="text-xs font-semibold text-foreground">
                      Kéo thả hoặc nhấn để chọn file
                    </p>
                    <p className="text-[11px] text-muted-foreground">
                      PDF, Word (.docx), Excel (.xlsx), CSV, TXT
                    </p>
                  </div>
                )}
              </div>

              <div className="space-y-3 p-4 rounded-xl border border-border bg-card">
                <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Tùy chọn Thử nghiệm
                </h4>

                <div className="space-y-1.5">
                  <Label htmlFor="max-pages-select" className="text-xs font-medium">
                    Giới hạn số trang xem trước
                  </Label>
                  <Select value={maxPages} onValueChange={setMaxPages}>
                    <SelectTrigger id="max-pages-select" className="text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="1">1 trang đầu (Rất nhanh)</SelectItem>
                      <SelectItem value="3">3 trang đầu (Khuyên dùng)</SelectItem>
                      <SelectItem value="5">5 trang đầu</SelectItem>
                      <SelectItem value="0">Toàn bộ tài liệu</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor="doc-engine-select" className="text-xs font-medium">
                    Ghi đè Bộ phân tích PDF
                  </Label>
                  <Select value={docEngine} onValueChange={setDocEngine}>
                    <SelectTrigger id="doc-engine-select" className="text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="default">Theo cấu hình đã lưu</SelectItem>
                      <SelectItem value="pymupdf4llm">PyMuPDF4LLM</SelectItem>
                      <SelectItem value="pymupdf_plain">PyMuPDF Plain Text</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor="doc-ocr-mode-select" className="text-xs font-medium">
                    Ghi đè Chế độ OCR
                  </Label>
                  <Select value={docOcrMode} onValueChange={setDocOcrMode}>
                    <SelectTrigger id="doc-ocr-mode-select" className="text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="default">Theo cấu hình đã lưu</SelectItem>
                      <SelectItem value="auto">Tự động (chỉ trang scan)</SelectItem>
                      <SelectItem value="force_ocr">Ép OCR toàn bộ</SelectItem>
                      <SelectItem value="disabled">Tắt OCR</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <Button
                  onClick={runDocExtractionTest}
                  disabled={!docFile || docLoading}
                  className="w-full gap-2 text-xs font-medium mt-2"
                >
                  {docLoading ? (
                    <>
                      <span className="material-symbols-outlined animate-spin text-sm">progress_activity</span>
                      Đang bóc tách...
                    </>
                  ) : (
                    <>
                      <span className="material-symbols-outlined text-sm">play_arrow</span>
                      Bóc tách & Xem trước
                    </>
                  )}
                </Button>
              </div>
            </div>

            {/* Right Results & Preview */}
            <div className="md:col-span-2 space-y-4">
              {docResult?.error && (
                <div className="p-4 rounded-xl border border-destructive/20 bg-destructive/10 text-destructive text-xs">
                  <div className="flex items-center gap-2 font-semibold">
                    <span className="material-symbols-outlined text-base">error</span>
                    Bóc tách thất bại:
                  </div>
                  <p className="mt-1 font-mono">{docResult.error}</p>
                </div>
              )}

              {docResult?.success && docResult.stats && (
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div className="p-3 rounded-lg border border-border bg-muted/20">
                    <span className="text-[11px] text-muted-foreground block">Tổng số trang</span>
                    <span className="text-lg font-semibold text-foreground">
                      {docResult.stats.total_pages}
                    </span>
                  </div>
                  <div className="p-3 rounded-lg border border-border bg-muted/20">
                    <span className="text-[11px] text-muted-foreground block">Trang đã preview</span>
                    <span className="text-lg font-semibold text-foreground">
                      {docResult.stats.preview_pages_count}
                    </span>
                  </div>
                  <div className="p-3 rounded-lg border border-border bg-muted/20">
                    <span className="text-[11px] text-muted-foreground block">Trang kích hoạt OCR</span>
                    <div className="flex items-center gap-1.5 mt-0.5">
                      <span className="text-lg font-semibold text-foreground">
                        {docResult.stats.ocr_pages_count}
                      </span>
                      {docResult.stats.ocr_pages_count > 0 && (
                        <Badge variant="secondary" className="text-[10px] bg-blue-500/10 text-blue-600 dark:text-blue-400 border-0">
                          Scan
                        </Badge>
                      )}
                    </div>
                  </div>
                  <div className="p-3 rounded-lg border border-border bg-muted/20">
                    <span className="text-[11px] text-muted-foreground block">Thời gian xử lý</span>
                    <span className="text-lg font-semibold font-mono text-foreground">
                      {(docResult.stats.latency_ms / 1000).toFixed(2)}s
                    </span>
                  </div>
                </div>
              )}

              {docResult?.success && docResult.pages && docResult.pages.length > 0 ? (
                <div className="rounded-xl border border-border bg-card overflow-hidden">
                  {/* Page Navigator Tabs */}
                  <div className="flex items-center justify-between p-3 border-b border-border bg-muted/30">
                    <div className="flex items-center gap-2 overflow-x-auto py-1 max-w-[70%]">
                      {docResult.pages.map((p, idx) => (
                        <button
                          key={p.page_number}
                          onClick={() => setSelectedPageIndex(idx)}
                          className={`px-3 py-1 rounded-md text-xs font-medium flex items-center gap-1.5 transition-colors whitespace-nowrap ${
                            selectedPageIndex === idx
                              ? "bg-primary text-primary-foreground shadow-sm"
                              : "bg-muted/50 hover:bg-muted text-muted-foreground"
                          }`}
                        >
                          <span>Trang {p.page_number}</span>
                          {p.is_ocr && (
                            <span className="h-1.5 w-1.5 rounded-full bg-blue-400" title="Trang scan đã OCR" />
                          )}
                        </button>
                      ))}
                    </div>

                    <div className="flex items-center gap-2">
                      <div className="flex rounded-lg border border-border p-0.5 bg-background">
                        <button
                          onClick={() => setDocViewMode("rendered")}
                          className={`px-2 py-0.5 rounded text-[11px] font-medium transition-colors ${
                            docViewMode === "rendered" ? "bg-muted text-foreground" : "text-muted-foreground"
                          }`}
                        >
                          Rendered
                        </button>
                        <button
                          onClick={() => setDocViewMode("raw")}
                          className={`px-2 py-0.5 rounded text-[11px] font-medium transition-colors ${
                            docViewMode === "raw" ? "bg-muted text-foreground" : "text-muted-foreground"
                          }`}
                        >
                          Raw
                        </button>
                      </div>

                      {activePage && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => copyPageText(activePage.content)}
                          className="h-7 text-xs gap-1"
                        >
                          <span className="material-symbols-outlined text-sm">
                            {docCopied ? "check" : "content_copy"}
                          </span>
                          {docCopied ? "Đã copy" : "Copy"}
                        </Button>
                      )}
                    </div>
                  </div>

                  {/* Active Page Header & Content */}
                  {activePage && (
                    <div className="p-4 space-y-4">
                      <div className="flex items-center justify-between text-xs pb-3 border-b border-border/50">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-foreground">
                            Trang {activePage.page_number} / {docResult.stats?.total_pages || docResult.pages.length}
                          </span>
                          {activePage.is_ocr ? (
                            <Badge variant="outline" className="border-blue-500/30 bg-blue-500/10 text-blue-600 dark:text-blue-400 gap-1 text-[11px]">
                              <span className="material-symbols-outlined text-xs">document_scanner</span>
                              Trang scan - Đã OCR
                            </Badge>
                          ) : (
                            <Badge variant="outline" className="border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 gap-1 text-[11px]">
                              <span className="material-symbols-outlined text-xs">text_fields</span>
                              Văn bản số hóa gốc
                            </Badge>
                          )}
                        </div>

                        <div className="text-muted-foreground text-[11px] flex gap-3">
                          <span>{activePage.word_count} từ</span>
                          <span>{activePage.char_count} ký tự</span>
                        </div>
                      </div>

                      <div className="max-h-[500px] overflow-y-auto pr-2">
                        {docViewMode === "rendered" ? (
                          <div className="prose prose-sm dark:prose-invert max-w-none">
                            <WikiContent markdown={activePage.content} />
                          </div>
                        ) : (
                          <pre className="p-4 rounded-lg bg-muted/30 border border-border font-mono text-xs whitespace-pre-wrap break-words">
                            {activePage.content}
                          </pre>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              ) : !docLoading && !docResult ? (
                <div className="h-[300px] rounded-xl border border-dashed border-border flex flex-col items-center justify-center text-center p-6 text-muted-foreground">
                  <span className="material-symbols-outlined text-4xl mb-2 text-muted-foreground/50">
                    find_in_page
                  </span>
                  <p className="text-xs font-medium">Chưa có kết quả thử nghiệm</p>
                  <p className="text-[11px] mt-1">Chọn file tài liệu và nhấn &quot;Bóc tách &amp; Xem trước&quot; để hiển thị.</p>
                </div>
              ) : null}
            </div>
          </div>
        </TabsContent>

        {/* TAB 2: QUICK OCR TEST */}
        <TabsContent value="ocr" className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* Left Upload */}
            <div className="space-y-4">
              <div
                onClick={() => ocrInputRef.current?.click()}
                className="border-2 border-dashed border-border hover:border-primary/50 transition-colors rounded-xl p-6 flex flex-col items-center justify-center text-center cursor-pointer bg-muted/20 hover:bg-muted/30 min-h-[180px]"
              >
                <input
                  ref={ocrInputRef}
                  type="file"
                  accept="image/png,image/jpeg,image/webp,.pdf"
                  className="hidden"
                  onChange={handleOcrFileSelect}
                />
                <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary mb-3">
                  <span className="material-symbols-outlined text-2xl">photo_camera</span>
                </div>
                {ocrFile ? (
                  <div className="space-y-1">
                    <p className="text-xs font-semibold text-foreground truncate max-w-[200px]">
                      {ocrFile.name}
                    </p>
                    <p className="text-[11px] text-muted-foreground">
                      {(ocrFile.size / 1024).toFixed(1)} KB • Nhấn để đổi file
                    </p>
                  </div>
                ) : (
                  <div className="space-y-1">
                    <p className="text-xs font-semibold text-foreground">
                      Kéo thả ảnh hoặc PDF 1 trang
                    </p>
                    <p className="text-[11px] text-muted-foreground">
                      PNG, JPG, WEBP, PDF
                    </p>
                  </div>
                )}
              </div>

              {ocrPreviewUrl && (
                <div className="rounded-xl border border-border overflow-hidden max-h-[220px] bg-muted/20">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={ocrPreviewUrl}
                    alt="Preview"
                    className="w-full h-full object-contain max-h-[220px]"
                  />
                </div>
              )}

              <Button
                onClick={runOcrTest}
                disabled={!ocrFile || ocrLoading}
                className="w-full gap-2 text-xs font-medium"
              >
                {ocrLoading ? (
                  <>
                    <span className="material-symbols-outlined animate-spin text-sm">progress_activity</span>
                    Đang quét OCR...
                  </>
                ) : (
                  <>
                    <span className="material-symbols-outlined text-sm">document_scanner</span>
                    Bắt đầu Test OCR
                  </>
                )}
              </Button>
            </div>

            {/* Right Output */}
            <div className="md:col-span-2 space-y-4">
              {ocrResult?.error && (
                <div className="p-4 rounded-xl border border-destructive/20 bg-destructive/10 text-destructive text-xs">
                  <div className="flex items-center gap-2 font-semibold">
                    <span className="material-symbols-outlined text-base">error</span>
                    Lỗi OCR:
                  </div>
                  <p className="mt-1 font-mono">{ocrResult.error}</p>
                </div>
              )}

              {ocrResult?.success ? (
                <div className="rounded-xl border border-border bg-card overflow-hidden">
                  <div className="flex items-center justify-between p-3 border-b border-border bg-muted/30">
                    <div className="flex items-center gap-2 flex-wrap">
                      <Badge variant="outline" className="border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 gap-1 text-[11px]">
                        <span className="material-symbols-outlined text-xs">check_circle</span>
                        Thành công
                      </Badge>
                      <span className="text-xs font-mono text-muted-foreground">
                        {ocrResult.model}
                      </span>
                      <span className="text-xs font-medium text-foreground">
                        {ocrResult.latency_ms} ms
                      </span>
                      <span className="text-xs text-muted-foreground">
                        ({ocrResult.words_count} từ, {ocrResult.chars_count} ký tự)
                      </span>
                    </div>

                    <div className="flex items-center gap-2">
                      <div className="flex rounded-lg border border-border p-0.5 bg-background">
                        <button
                          onClick={() => setOcrViewMode("rendered")}
                          className={`px-2 py-0.5 rounded text-[11px] font-medium transition-colors ${
                            ocrViewMode === "rendered" ? "bg-muted text-foreground" : "text-muted-foreground"
                          }`}
                        >
                          Rendered
                        </button>
                        <button
                          onClick={() => setOcrViewMode("raw")}
                          className={`px-2 py-0.5 rounded text-[11px] font-medium transition-colors ${
                            ocrViewMode === "raw" ? "bg-muted text-foreground" : "text-muted-foreground"
                          }`}
                        >
                          Raw
                        </button>
                      </div>

                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={copyOcrText}
                        className="h-7 text-xs gap-1"
                      >
                        <span className="material-symbols-outlined text-sm">
                          {ocrCopied ? "check" : "content_copy"}
                        </span>
                        {ocrCopied ? "Đã copy" : "Copy"}
                      </Button>
                    </div>
                  </div>

                  <div className="p-4 max-h-[500px] overflow-y-auto">
                    {ocrViewMode === "rendered" ? (
                      <div className="prose prose-sm dark:prose-invert max-w-none">
                        <WikiContent markdown={ocrResult.text} />
                      </div>
                    ) : (
                      <pre className="p-4 rounded-lg bg-muted/30 border border-border font-mono text-xs whitespace-pre-wrap break-words">
                        {ocrResult.text}
                      </pre>
                    )}
                  </div>
                </div>
              ) : !ocrLoading && !ocrResult ? (
                <div className="h-[300px] rounded-xl border border-dashed border-border flex flex-col items-center justify-center text-center p-6 text-muted-foreground">
                  <span className="material-symbols-outlined text-4xl mb-2 text-muted-foreground/50">
                    document_scanner
                  </span>
                  <p className="text-xs font-medium">Chưa có kết quả OCR</p>
                  <p className="text-[11px] mt-1">Chọn ảnh hoặc 1 trang PDF rồi nhấn &quot;Bắt đầu Test OCR&quot; để xem trước.</p>
                </div>
              ) : null}
            </div>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
