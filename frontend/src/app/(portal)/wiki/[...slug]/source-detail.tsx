"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScopeBadge } from "@/components/shared/scope-badge";
import { WikiContent } from "@/components/wiki/wiki-content";
import { DeleteSourcesDialog } from "@/components/knowledge/delete-sources-dialog";
import { EditSourceDialog } from "@/components/knowledge/knowledge-table/edit-source-dialog";
import { ExtractionReviewDialog } from "@/components/knowledge/knowledge-table/extraction-review-dialog";
import { PlanReviewDialog } from "@/components/knowledge/knowledge-table/plan-review-dialog";
import { StatusDot } from "@/components/knowledge/knowledge-table/status-dot";
import { errorText, type SourceDetail, type KnowledgeType, type Department } from "@/components/knowledge/types";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { needsSourcePolling } from "@/lib/source-workflow";
import { wikiPageQuery } from "@/lib/wiki-navigation";
import { formatViDate } from "@/lib/legal-doc";
import { normalizeExtractedHeadings } from "@/lib/extracted-headings";
import type { WikiPageSummary } from "@/types/wiki";
import { SourceView, formatMb } from "./source-view";

const TAB_VALUES = new Set(["file", "extracted", "wiki", "info"]);

export function SourceDetailView({ sourceId, initialTab, goTo }: { sourceId: string; initialTab?: string | null; goTo: (href: string) => void }) {
  const { canAccess } = useAuth();
  const canEdit = canAccess("doc", "edit");
  const canDelete = canAccess("doc", "delete");
  const [source, setSource] = useState<SourceDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [tab, setTab] = useState(TAB_VALUES.has(initialTab || "") ? initialTab! : "file");
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [reviewing, setReviewing] = useState(false);
  const [types, setTypes] = useState<KnowledgeType[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [metaError, setMetaError] = useState<string | null>(null);
  const [pages, setPages] = useState<WikiPageSummary[] | null>(null);
  const [pagesError, setPagesError] = useState<string | null>(null);
  const [wikiSearch, setWikiSearch] = useState("");
  const [rawText, setRawText] = useState(false);
  const [pageTick, setPageTick] = useState(0);
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    try {
      const updated = await api<SourceDetail>(`/api/sources/${sourceId}`);
      setSource(updated);
      setError(null);
    } catch (err) { setError(errorText(err, "Không tải được tài liệu")); }
  }, [sourceId]);
  useEffect(() => {
    let active = true;
    api<SourceDetail>(`/api/sources/${sourceId}`)
      .then((updated) => { if (active) { setSource(updated); setError(null); } })
      .catch((err) => { if (active) setError(errorText(err, "Không tải được tài liệu")); });
    return () => { active = false; };
  }, [sourceId]);
  const running = source ? needsSourcePolling(source) : false;
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => { void load(); }, 4000);
    return () => clearInterval(timer);
  }, [running, load]);
  useEffect(() => {
    if (!canEdit) return;
    let active = true;
    Promise.all([api<KnowledgeType[]>("/api/knowledge-types"), api<Department[]>("/api/departments")])
      .then(([nextTypes, nextDepts]) => { if (active) { setTypes(nextTypes); setDepartments(nextDepts); } })
      .catch((err) => { if (active) setMetaError(errorText(err, "Chưa tải được danh mục chỉnh sửa")); });
    return () => { active = false; };
  }, [canEdit]);
  useEffect(() => {
    if (tab !== "wiki") return;
    let active = true;
    api<WikiPageSummary[]>(`/api/wiki/pages?source_id=${encodeURIComponent(sourceId)}&limit=1000`)
      .then((result) => { if (active) { setPages(Array.isArray(result) ? result : []); setPagesError(null); } })
      .catch((err) => { if (active) setPagesError(errorText(err, "Không tải được trang Wiki")); });
    return () => { active = false; };
  }, [tab, sourceId, pageTick, source?.wiki_page_count]);

  const changeTab = (value: string) => {
    setTab(value);
    const url = new URL(window.location.href);
    url.searchParams.set("tab", value);
    window.history.replaceState(null, "", url.pathname + url.search);
  };
  const retry = async () => {
    setBusy(true);
    setActionError(null);
    try { await api(`/api/sources/${sourceId}/retry`, { method: "POST" }); await load(); }
    catch (err) { setActionError(errorText(err, "Không chạy lại được")); }
    finally { setBusy(false); }
  };
  const saved = () => { setEditing(false); setReviewing(false); void load(); setPageTick((n) => n + 1); };
  const manualReview = source?.upload_review_status === "awaiting";
  const visiblePages = (pages ?? []).filter((page) => `${page.title} ${page.summary}`.toLocaleLowerCase("vi").includes(wikiSearch.trim().toLocaleLowerCase("vi")));
  if (!source) return <div className="mx-auto max-w-6xl py-8"><Button variant="ghost" onClick={() => goTo("/knowledge")}>← Tài liệu</Button><p className="mt-6 text-sm text-muted-foreground" role={error ? "alert" : "status"}>{error || "Đang tải tài liệu…"}</p>{error && <Button className="mt-3" variant="outline" onClick={() => void load()}>Thử lại</Button>}</div>;

  const info = [
    ["Tên tệp", source.file_name], ["Tiêu đề hiển thị", source.title], ["Phân loại văn bản", source.knowledge_type_name],
    ["Số hiệu", source.doc_meta?.doc_number], ["Loại văn bản", source.doc_meta?.doc_type],
    ["Cơ quan ban hành", source.doc_meta?.issuing_authority], ["Trích yếu / tên chính thức", source.doc_meta?.official_title],
    ["Lĩnh vực", source.doc_meta?.field], ["Ngày ban hành", formatViDate(source.doc_meta?.issued_date)],
    ["Ngày hiệu lực", formatViDate(source.doc_meta?.effective_date)], ["Hết hiệu lực", formatViDate(source.doc_meta?.expiry_date)],
    ["Người tải lên", source.contributed_by_name], ["Dung lượng", source.file_size ? formatMb(source.file_size) : null],
    ["Phòng ban quản lý", source.managing_department_name], ["Phòng ban được xem", source.department_names?.join(", ")],
  ];
  return (
    <div className="mx-auto w-full max-w-6xl space-y-5 pb-8">
      <nav className="flex items-center gap-2 text-sm text-muted-foreground" aria-label="Điều hướng tài liệu"><Link href="/knowledge" className="inline-flex items-center gap-1 hover:text-foreground"><span className="material-symbols-outlined text-[17px]" aria-hidden>arrow_back</span>Tài liệu</Link><span>/</span><span className="truncate">Chi tiết tài liệu</span></nav>
      <header className="space-y-4">
        <div className="flex flex-wrap items-center gap-3"><StatusDot source={source} /><ScopeBadge scopeType={source.scope_type || "global"} scopeId={source.scope_id} />{source.knowledge_type_name && <span className="text-xs text-muted-foreground">{source.knowledge_type_name}</span>}</div>
        <h1 className="max-w-4xl text-2xl font-semibold leading-snug tracking-tight sm:text-3xl">{source.title || source.file_name}</h1>
        <div className="flex flex-wrap items-center gap-2">
          {canEdit && <Button variant="outline" size="sm" disabled={!!metaError} onClick={() => setEditing(true)}><span className="material-symbols-outlined text-[16px]" aria-hidden>edit</span>Sửa thông tin</Button>}
          {source.download_url && <Button variant="outline" size="sm" nativeButton={false} render={<a href={source.download_url} target="_blank" rel="noopener noreferrer" />}>Tải tệp gốc</Button>}
          {canEdit && ["error", "partial"].includes(source.status) && <Button variant="outline" size="sm" disabled={busy} onClick={() => void retry()}>Chạy lại phần lỗi</Button>}
          {canDelete && <Button variant="ghost" size="sm" className="ml-auto text-destructive hover:text-destructive" onClick={() => setDeleting(true)}><span className="material-symbols-outlined text-[16px]" aria-hidden>delete</span>Xóa tài liệu</Button>}
        </div>
      </header>
      {(error || actionError || metaError) && <p role="alert" className="text-sm text-destructive">{error || actionError || metaError}</p>}
      {canEdit && (manualReview || source.status === "awaiting_approval" || source.status === "plan_ready") && <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-blue-200 bg-blue-50/50 p-4 dark:border-blue-500/30 dark:bg-blue-500/10"><div><p className="text-sm font-medium">{manualReview ? "Thông tin đã trích xuất — chờ bạn kiểm tra" : source.status === "plan_ready" ? "Kế hoạch biên soạn đang chờ duyệt" : "Dung lượng trích xuất đang chờ duyệt"}</p><p className="mt-1 text-xs text-muted-foreground">{manualReview ? "Đối chiếu tệp gốc hoặc nội dung trích xuất trước khi xác nhận tiếp tục." : "Xem kết quả và xác nhận để tiếp tục xử lý tài liệu."}</p></div><Button size="sm" disabled={manualReview && !!metaError} onClick={() => manualReview ? setEditing(true) : setReviewing(true)}>{manualReview ? "Duyệt thông tin" : "Xem và duyệt"}</Button></div>}
      <Tabs value={tab} onValueChange={(value) => changeTab(String(value))} className="flex-col gap-5">
        <div className="overflow-x-auto border-b"><TabsList variant="line" className="h-11 min-w-max gap-4"><TabsTrigger value="file">Tệp gốc</TabsTrigger><TabsTrigger value="extracted">Nội dung trích xuất</TabsTrigger><TabsTrigger value="wiki">Trang Wiki{source.wiki_page_count ? ` (${source.wiki_page_count})` : ""}</TabsTrigger><TabsTrigger value="info">Thông tin</TabsTrigger></TabsList></div>
        <TabsContent value="file"><SourceView source={{ ...source, updated_at: source.updated_at ?? undefined }} compact /></TabsContent>
        <TabsContent value="extracted">
          <div className="mb-4 flex flex-wrap items-center gap-2 text-xs text-muted-foreground"><span>{source.page_count ?? 0} trang</span><span>·</span><span>{source.image_count ?? 0} ảnh</span><span>·</span><span>{(source.extracted_token_count ?? 0).toLocaleString("vi-VN")} token</span></div>
          {source.full_text?.trim() ? <><div className="mb-4 flex flex-wrap items-center justify-between gap-3"><p className="text-xs text-muted-foreground">Nội dung nhận diện từ tệp gốc để đối chiếu. Chỉnh sửa nội dung đã biên soạn trong tab Trang Wiki.</p><div className="flex gap-1"><Button variant={rawText ? "ghost" : "secondary"} size="sm" aria-pressed={!rawText} onClick={() => setRawText(false)}>Dễ đọc</Button><Button variant={rawText ? "secondary" : "ghost"} size="sm" aria-pressed={rawText} onClick={() => setRawText(true)}>Văn bản trích xuất gốc</Button></div></div>{rawText ? <pre className="max-h-[70vh] overflow-y-auto rounded-lg border bg-background p-4 font-mono text-sm leading-7 whitespace-pre-wrap break-words sm:p-6">{source.full_text}</pre> : <div className="max-h-[70vh] overflow-y-auto rounded-lg border bg-background p-4 sm:p-6"><WikiContent markdown={normalizeExtractedHeadings(source.full_text)} /></div>}</> : <Empty title={running ? "Đang trích xuất nội dung" : "Chưa có nội dung trích xuất"} hint={running ? "Kết quả sẽ tự cập nhật khi xử lý xong." : "Kiểm tra trạng thái tài liệu hoặc chạy lại phần lỗi."} />}
        </TabsContent>
        <TabsContent value="wiki">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-sm font-semibold">Các trang được tạo từ tài liệu</h2><p className="mt-1 text-xs text-muted-foreground">Mở để đọc hoặc sửa nội dung từng trang.</p></div><Input aria-label="Tìm trang Wiki trong tài liệu" placeholder="Tìm trang Wiki…" value={wikiSearch} onChange={(e) => setWikiSearch(e.target.value)} className="w-full sm:w-72" /></div>
          {pagesError ? <div role="alert" className="text-sm text-destructive">{pagesError}<Button variant="outline" size="sm" className="ml-2" onClick={() => setPageTick((n) => n + 1)}>Thử lại</Button></div> : pages === null ? <p className="text-sm text-muted-foreground">Đang tải trang Wiki…</p> : visiblePages.length ? <ul className="divide-y rounded-lg border">{visiblePages.map((page) => {
            const href = `/wiki/${page.slug.split("/").map(encodeURIComponent).join("/")}`;
            const query = wikiPageQuery(page.scope_type, page.scope_id, "/wiki/law?view=wiki");
            return <li key={`${page.scope_type}:${page.scope_id}:${page.slug}`} className="flex items-start gap-3 px-4 py-4"><div className="min-w-0 flex-1"><Link href={href + query} className="text-sm font-medium hover:text-primary">{page.title}</Link>{page.summary && <p className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">{page.summary}</p>}</div>{canEdit && <Button size="sm" variant="outline" nativeButton={false} render={<Link href={href + wikiPageQuery(page.scope_type, page.scope_id, "/wiki/law?view=wiki", true)} />}>Sửa trang Wiki</Button>}</li>;
          })}</ul> : <Empty title={wikiSearch ? "Không tìm thấy trang phù hợp" : "Chưa có trang Wiki"} hint={manualReview ? "Duyệt thông tin tài liệu để bắt đầu tạo trang Wiki." : "Các trang sẽ xuất hiện sau khi biên soạn hoàn tất."} />}
        </TabsContent>
        <TabsContent value="info"><h2 className="mb-4 text-sm font-semibold">Thông tin tài liệu</h2><dl className="grid gap-x-8 sm:grid-cols-2">{info.map(([label, value]) => <div key={label} className="border-b py-3"><dt className="text-xs text-muted-foreground">{label}</dt><dd className="mt-1 break-words text-sm">{value || "Chưa xác định"}</dd></div>)}</dl></TabsContent>
      </Tabs>
      {editing && <EditSourceDialog source={source} types={types} departments={departments} reviewUpload={manualReview} onClose={() => setEditing(false)} onSaved={saved} />}
      {reviewing && (source.status === "plan_ready" ? <PlanReviewDialog source={source} onClose={() => setReviewing(false)} onDone={saved} /> : <ExtractionReviewDialog source={source} onClose={() => setReviewing(false)} onDone={saved} />)}
      {deleting && <DeleteSourcesDialog sources={[source]} onClose={() => setDeleting(false)} onDeleted={() => goTo("/knowledge")} />}
    </div>
  );
}

function Empty({ title, hint }: { title: string; hint: string }) { return <div className="rounded-lg border border-dashed px-6 py-14 text-center"><p className="text-sm font-medium">{title}</p><p className="mt-2 text-xs text-muted-foreground">{hint}</p></div>; }
