"use client";

import { useSyncExternalStore } from "react";

/**
 * Chế độ nhúng: Kho tri thức chạy trong iframe ở trang "Cấu hình hệ thống" của chatbot.
 * Wiki báo trạng thái cho trang cha bằng postMessage; không bao giờ gửi token hay dữ liệu.
 */

export type HostMessage =
  | { type: "ready"; path: string }
  | { type: "navigate"; path: string }
  | { type: "auth-required"; path: string };

const subscribe = () => () => {};

function detectEmbedded(): boolean {
  try {
    return window.self !== window.top;
  } catch {
    // Truy cập window.top bị chặn nghĩa là đang nằm trong khung khác origin.
    return true;
  }
}

/** true khi trang đang chạy trong iframe. Phía server luôn là false. */
export function useIsEmbedded(): boolean {
  return useSyncExternalStore(subscribe, detectEmbedded, () => false);
}

export function isEmbedded(): boolean {
  return typeof window !== "undefined" && detectEmbedded();
}

/** Đường dẫn hiện tại, bỏ các tham số chỉ dùng cho chế độ nhúng. */
export function currentPathForHost(): string {
  const url = new URL(window.location.href);
  url.searchParams.delete("embed");
  url.searchParams.delete("theme");
  const search = url.searchParams.toString();
  return url.pathname + (search ? `?${search}` : "");
}

// ── Giao diện sáng/tối theo trang cha ─────────────────────────────────────
// Lần đầu lấy từ ?theme= (trang cha đặt khi tạo iframe), sau đó theo tin nhắn
// 'cahy-host:theme'. Lưu vào sessionStorage để giữ qua các lần tải lại trong luồng SSO.

export type HostTheme = "light" | "dark";

const HOST_THEME_KEY = "dw-embed-theme";
let cachedHostTheme: HostTheme | null | undefined;

const asHostTheme = (value: unknown): HostTheme | null =>
  value === "light" || value === "dark" ? value : null;

function storeHostTheme(value: HostTheme) {
  try {
    sessionStorage.setItem(HOST_THEME_KEY, value);
  } catch {
    // sessionStorage có thể bị chặn; khi đó chỉ giữ trong bộ nhớ.
  }
}

function readHostTheme(): HostTheme | null {
  if (!detectEmbedded()) return null;
  if (cachedHostTheme === undefined) {
    const fromUrl = asHostTheme(new URLSearchParams(window.location.search).get("theme"));
    let stored: HostTheme | null = null;
    try {
      stored = asHostTheme(sessionStorage.getItem(HOST_THEME_KEY));
    } catch {
      stored = null;
    }
    cachedHostTheme = fromUrl ?? stored;
    if (fromUrl) storeHostTheme(fromUrl);
  }
  return cachedHostTheme;
}

function subscribeHostTheme(onChange: () => void) {
  const onMessage = (event: MessageEvent) => {
    if (event.source !== window.parent || window.parent === window) return;
    const data = event.data;
    if (!data || typeof data !== "object" || data.type !== "cahy-host:theme") return;
    const next = asHostTheme(data.theme);
    if (!next) return;
    cachedHostTheme = next;
    storeHostTheme(next);
    onChange();
  };
  window.addEventListener("message", onMessage);
  return () => window.removeEventListener("message", onMessage);
}

/** Giao diện trang cha khi đang nhúng; null khi mở wiki trực tiếp. */
export function useHostTheme(): HostTheme | null {
  return useSyncExternalStore(subscribeHostTheme, readHostTheme, () => null);
}

// ── Danh tính người dùng ở trang cha ──────────────────────────────────────
// Phiên wiki nằm trong localStorage riêng, không mất khi chatbot đăng xuất. Trang cha báo
// email đang đăng nhập ('cahy-host:identity'); lệch thì phiên wiki là của người trước.

/** Gọi onIdentity(email) mỗi khi trang cha báo người dùng đang đăng nhập. */
export function subscribeHostIdentity(onIdentity: (email: string) => void): () => void {
  const onMessage = (event: MessageEvent) => {
    if (event.source !== window.parent || window.parent === window) return;
    const data = event.data;
    if (!data || typeof data !== "object" || data.type !== "cahy-host:identity") return;
    if (typeof data.email === "string" && data.email) onIdentity(data.email);
  };
  window.addEventListener("message", onMessage);
  return () => window.removeEventListener("message", onMessage);
}

export function postToHost(message: HostMessage): void {
  if (!isEmbedded()) return;
  // Chỉ gửi trạng thái điều hướng, không chứa bí mật, nên không cần giới hạn origin đích.
  window.parent.postMessage({ source: "cahy-wiki", ...message }, "*");
}
