"use client";

import { Suspense, useEffect, useRef, useState, type FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api, apiUrl } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { isEmbedded, postToHost, useIsEmbedded } from "@/lib/embed";
import { MAX_LOGIN_HOPS, clearLoginRound, readLoginRound, saveLoginRound } from "@/lib/login-round";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type SsoConfig = {
  enabled: boolean;
  chatbot_login?: boolean;
  provider_name?: string;
  auto_redirect?: boolean;
  allow_password_login: boolean;
};

const ERROR_TEXT: Record<string, string> = {
  sso_disabled: "Đăng nhập dùng chung chưa được cấu hình trên Kho tri thức.",
  sso_misconfigured: "Cấu hình đăng nhập dùng chung giữa Trợ lý ảo AI và Kho tri thức chưa khớp, liên hệ quản trị.",
  sso_unavailable: "Không kết nối được máy chủ đăng nhập tập trung (Keycloak).",
  sso_denied: "Đăng nhập đã bị hủy hoặc bị từ chối.",
  sso_login_required: "Bạn chưa đăng nhập Trợ lý ảo AI.",
  sso_state: "Phiên đăng nhập đã hết hạn, vui lòng thử lại.",
  sso_token: "Không xác thực được tài khoản, vui lòng thử lại.",
  sso_inactive: "Tài khoản đã bị khóa trên Kho tri thức, liên hệ quản trị.",
  sso_email_conflict: "Email này đã gắn với một tài khoản SSO khác, liên hệ quản trị.",
  sso_email_unverified:
    "Email này đã có tài khoản Kho tri thức nhưng chưa được xác minh trên Keycloak, liên hệ quản trị.",
};
const GENERIC_ERROR = "Đăng nhập không thành công.";
const errorText = (code: string) => ERROR_TEXT[code] ?? GENERIC_ERROR;

/** Accept only same-site absolute paths, and never loop back into /login. */
function sanitizeNext(raw: string | null): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//") || raw.includes("\\")) return "/";
  if (raw === "/login" || raw.startsWith("/login/") || raw.startsWith("/login?")) return "/";
  return raw;
}

function chatbotUrl(next: string, silent: boolean): string {
  return apiUrl(`/api/auth/sso/chatbot/login?next=${encodeURIComponent(next)}${silent ? "&prompt=none" : ""}`);
}

function keycloakUrl(next: string, silent: boolean): string {
  return apiUrl(`/api/auth/sso/login?next=${encodeURIComponent(next)}${silent ? "&prompt=none" : ""}`);
}

type ViewState =
  | { kind: "redirecting" }
  | { kind: "message"; tone: "error" | "info"; text: string }
  | { kind: "form" };

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

function PasswordForm({ next }: { next: string }) {
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
    <form onSubmit={submit} className="flex flex-col gap-4 rounded-xl border bg-card p-6">
      <h1 className="text-sm font-medium">Tài khoản cục bộ (dự phòng)</h1>
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
  );
}

function LoginOrchestrator() {
  const params = useSearchParams();
  const router = useRouter();
  const { user, loading, error: sessionError, refresh } = useAuth();
  const embedded = useIsEmbedded();
  const [view, setView] = useState<ViewState>({ kind: "redirecting" });
  const leaving = useRef(false);

  const next = sanitizeNext(params.get("next"));
  const error = params.get("error");
  const loggedOut = params.has("logged_out");
  const wantForm = params.has("form");

  // Step A: already signed in.
  useEffect(() => {
    if (loading || !user || leaving.current) return;
    leaving.current = true;
    clearLoginRound();
    router.replace(next);
  }, [loading, user, next, router]);

  // Step B: not signed in, decide where to go.
  useEffect(() => {
    if (loading || user) return;
    let cancelled = false;

    const go = (url: string) => {
      leaving.current = true;
      window.location.replace(url);
    };

    api<SsoConfig>("/api/auth/sso/config")
      .then((cfg) => {
        if (cancelled) return;
        const chatbot = cfg.chatbot_login === true;
        const keycloak = !!cfg.enabled;
        const allowPassword = !!cfg.allow_password_login;

        if (isEmbedded()) {
          if ((chatbot || keycloak) && !error && !loggedOut && !wantForm) {
            go(chatbot ? chatbotUrl(next, true) : keycloakUrl(next, true));
            return;
          }
          postToHost({ type: "auth-required", path: next });
          setView({ kind: "message", tone: "info", text: errorText("sso_login_required") });
          return;
        }

        if (loggedOut) clearLoginRound();
        const round = readLoginRound();

        if ((!chatbot && !keycloak) || (wantForm && allowPassword)) {
          setView(allowPassword ? { kind: "form" } : { kind: "message", tone: "error", text: errorText("sso_disabled") });
          return;
        }
        if (loggedOut) {
          setView({ kind: "message", tone: "info", text: "Bạn đã đăng xuất khỏi Kho tri thức." });
          return;
        }
        if (error && (chatbot || error !== "sso_login_required")) {
          setView({ kind: "message", tone: "error", text: errorText(error) });
          return;
        }
        if (round.hops >= MAX_LOGIN_HOPS) {
          setView({
            kind: "message",
            tone: "error",
            text: "Không hoàn tất được đăng nhập dùng chung. Vui lòng thử lại.",
          });
          return;
        }

        saveLoginRound({ at: round.at, hops: round.hops + 1 });
        if (chatbot) go(chatbotUrl(next, false));
        else go(keycloakUrl(next, error !== "sso_login_required"));
      })
      .catch(() => {
        if (cancelled) return;
        if (isEmbedded()) postToHost({ type: "auth-required", path: next });
        setView({ kind: "message", tone: "error", text: "Không kết nối được máy chủ Kho tri thức." });
      });

    return () => {
      cancelled = true;
    };
  }, [loading, user, next, error, loggedOut, wantForm]);

  const retry = () => {
    clearLoginRound();
    // A full reload is intended: it starts a brand-new login round from a clean state.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.href = `/login?next=${encodeURIComponent(next)}`;
  };

  let body;
  if (sessionError && !user) {
    body = (
      <div role="alert" className="flex flex-col gap-4 rounded-xl border bg-card p-6 text-center">
        <p className="text-sm text-muted-foreground">{sessionError}</p>
        <Button onClick={() => void refresh()}>Thử lại</Button>
      </div>
    );
  } else if (view.kind === "form") {
    body = <PasswordForm next={next} />;
  } else if (view.kind === "message") {
    body = (
      <div className="flex flex-col gap-4 rounded-xl border bg-card p-6 text-center">
        <p
          className={
            view.tone === "error"
              ? "rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive"
              : "text-sm text-foreground"
          }
        >
          {view.text}
        </p>
        {embedded ? (
          <a
            href={`/login?next=${encodeURIComponent(next)}`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm font-medium text-primary underline"
          >
            Mở Kho tri thức trong tab mới để đăng nhập
          </a>
        ) : (
          <Button className="w-full" onClick={retry}>
            {loggedOut ? "Đăng nhập lại" : "Thử lại"}
          </Button>
        )}
      </div>
    );
  } else {
    body = <Spinner text="Đang chuyển tới trang đăng nhập…" />;
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
