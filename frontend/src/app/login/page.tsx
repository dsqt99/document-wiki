"use client";

import { Suspense, useEffect, useRef, useState, type FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api, apiUrl } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type SsoConfig = {
  enabled: boolean;
  provider_name?: string;
  allow_password_login: boolean;
};

const ERROR_TEXT: Record<string, string> = {
  sso_disabled: "Đăng nhập Google chưa được cấu hình.",
  sso_misconfigured: "Cấu hình đăng nhập Google chưa đúng, liên hệ quản trị.",
  sso_unavailable: "Không kết nối được máy chủ đăng nhập Google.",
  sso_denied: "Đăng nhập đã bị hủy hoặc bị từ chối.",
  sso_login_required: "Vui lòng đăng nhập để tiếp tục.",
  sso_state: "Phiên đăng nhập đã hết hạn, vui lòng thử lại.",
  sso_token: "Không xác thực được tài khoản, vui lòng thử lại.",
  sso_inactive: "Tài khoản đã bị khóa, liên hệ quản trị.",
  sso_email_conflict: "Email này đã gắn với một tài khoản khác, liên hệ quản trị.",
  sso_email_unverified: "Email Google này chưa được xác minh, liên hệ quản trị.",
};
const GENERIC_ERROR = "Đăng nhập không thành công.";
const errorText = (code: string) => ERROR_TEXT[code] ?? GENERIC_ERROR;

/** Accept only same-site absolute paths, and never loop back into /login. */
function sanitizeNext(raw: string | null): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//") || raw.includes("\\")) return "/";
  if (raw === "/login" || raw.startsWith("/login/") || raw.startsWith("/login?")) return "/";
  return raw;
}

function googleUrl(next: string): string {
  return apiUrl(`/api/auth/sso/login?next=${encodeURIComponent(next)}`);
}

function Spinner({ text }: { text: string }) {
  return (
    <div className="flex flex-col items-center gap-3">
      <span className="material-symbols-outlined animate-spin text-primary" style={{ fontSize: 36 }}>
        progress_activity
      </span>
      <p className="text-sm text-muted-foreground">{text}</p>
    </div>
  );
}

function LoginCard({ next, sso }: { next: string; sso: SsoConfig }) {
  const { login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await login(email, password);
      router.push(next);
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : "Đăng nhập không thành công");
      setSubmitting(false);
    }
  };

  return (
    <div className="flex flex-col gap-4 rounded-xl border bg-card p-6">
      <h1 className="text-base font-semibold">Đăng nhập</h1>
      {sso.allow_password_login && (
        <form onSubmit={submit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="login-email">Email</Label>
            <Input
              id="login-email"
              type="email"
              required
              autoFocus
              autoComplete="username"
              className="bg-background"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="login-password">Mật khẩu</Label>
            <Input
              id="login-password"
              type="password"
              required
              autoComplete="current-password"
              className="bg-background"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          {error && <p className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>}
          <Button type="submit" className="w-full" disabled={submitting}>
            {submitting ? "Đang đăng nhập…" : "Đăng nhập"}
          </Button>
        </form>
      )}
      {sso.enabled && (
        <>
          {sso.allow_password_login && (
            <div className="flex items-center gap-3 text-xs text-muted-foreground">
              <span className="h-px flex-1 bg-border" />
              hoặc
              <span className="h-px flex-1 bg-border" />
            </div>
          )}
          <a href={googleUrl(next)} className="w-full">
            <Button type="button" variant="outline" className="w-full">
              {`Đăng nhập với ${sso.provider_name || "Google"}`}
            </Button>
          </a>
        </>
      )}
    </div>
  );
}

function LoginOrchestrator() {
  const params = useSearchParams();
  const router = useRouter();
  const { user, loading, error: sessionError, refresh } = useAuth();
  const [sso, setSso] = useState<SsoConfig | null>(null);
  const [failed, setFailed] = useState(false);
  const leaving = useRef(false);

  const next = sanitizeNext(params.get("next"));
  const error = params.get("error");
  const loggedOut = params.has("logged_out");

  // Already signed in: leave for the target page.
  useEffect(() => {
    if (loading || !user || leaving.current) return;
    leaving.current = true;
    router.replace(next);
  }, [loading, user, next, router]);

  useEffect(() => {
    if (loading || user) return;
    let cancelled = false;
    api<SsoConfig>("/api/auth/sso/config")
      .then((cfg) => {
        if (!cancelled) setSso(cfg);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [loading, user]);

  let body;
  if (sessionError && !user) {
    body = (
      <div role="alert" className="flex flex-col gap-4 rounded-xl border bg-card p-6 text-center">
        <p className="text-sm text-muted-foreground">{sessionError}</p>
        <Button onClick={() => void refresh()}>Thử lại</Button>
      </div>
    );
  } else if (failed) {
    body = (
      <div className="flex flex-col gap-4 rounded-xl border bg-card p-6 text-center">
        <p className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">
          Không kết nối được máy chủ Kho tri thức.
        </p>
        <Button className="w-full" onClick={() => window.location.reload()}>
          Thử lại
        </Button>
      </div>
    );
  } else if (loading || !sso) {
    body = <Spinner text="Đang tải…" />;
  } else {
    body = (
      <div className="flex flex-col gap-4">
        {loggedOut && <p className="text-center text-sm text-muted-foreground">Bạn đã đăng xuất.</p>}
        {error && (
          <p className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">{errorText(error)}</p>
        )}
        <LoginCard next={next} sso={sso} />
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm">{body}</div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginOrchestrator />
    </Suspense>
  );
}
