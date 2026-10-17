import { ApiError } from "@/lib/api";

/**
 * Turn free text into a skill/command identifier: Vietnamese "đ" becomes "d", accents are
 * dropped, everything is lowercased, every run of characters outside a-z/0-9 collapses to a
 * single "-", a leading "-" is removed and the result is capped at 80 characters.
 */
export function toSkillName(input: string): string {
  return input
    .replace(/đ/g, "d")
    .replace(/Đ/g, "D")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+/, "")
    .slice(0, 80);
}

/** Strip every trailing "-" (names are normalised while typing, so one may dangle). */
export function trimTrailingDash(s: string): string {
  return s.replace(/-+$/, "");
}

// Latin letters, digits, space, "-", "_" plus the precomposed Vietnamese letters.
const DISPLAY_NAME_CHARS =
  /^[A-Za-z0-9 _\-ÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚÝàáâãèéêìíòóôõùúýĂăĐđĨĩŨũƠơƯưẠ-ỹ]+$/;

/** Human-facing names (rename dialog, new-contribution title). Empty strings are invalid. */
export function isValidDisplayName(s: string): boolean {
  return s.length > 0 && DISPLAY_NAME_CHARS.test(s);
}

/** Message of an API error (its `detail`) or a fallback for anything else. */
export function errMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message || fallback;
  if (err instanceof Error && err.message) return err.message;
  return fallback;
}

/** `detail` string inside an API error body, if the server sent one. */
export function errDetail(err: unknown): string | null {
  if (err instanceof ApiError && err.data && typeof err.data === "object" && "detail" in err.data) {
    const d = (err.data as { detail: unknown }).detail;
    if (typeof d === "string" && d) return d;
  }
  return null;
}

export function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const pad = (n: number) => String(n).padStart(2, "0");

/** dd/mm/yy HH:MM */
export function fmtShortDateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${String(d.getFullYear()).slice(-2)} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** dd/mm/yyyy HH:mm (24h, Vietnamese convention) */
export function fmtViDateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** Folder slug used when a proposal has no files yet (title without the "Upload: " prefix). */
export function titleSlug(title: string): string {
  return title
    .replace(/^Upload:\s*/, "")
    .toLowerCase()
    .trim()
    .replace(/\s+/g, "-")
    .replace(/[^\p{L}\p{N}_-]/gu, "")
    .replace(/-{2,}/g, "-");
}

/** Shared tones for small status pills. */
export const TONE = {
  amber: "bg-amber-500/10 text-amber-700 dark:text-amber-300",
  blue: "bg-blue-500/10 text-blue-700 dark:text-blue-300",
  red: "bg-destructive/10 text-destructive",
  green: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  muted: "bg-muted text-muted-foreground",
  violet: "bg-violet-500/10 text-violet-700 dark:text-violet-300",
} as const;
