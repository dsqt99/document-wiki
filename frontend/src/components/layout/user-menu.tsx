"use client";

import type { ReactNode } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { useI18n, type Language } from "@/lib/i18n";
import { useTheme, type Theme } from "@/lib/theme";
import { cn } from "@/lib/utils";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

function Segmented({ children }: { children: ReactNode }) {
  return <div className="flex items-center gap-0.5 rounded-lg border bg-muted p-0.5">{children}</div>;
}

function SegmentButton({
  active,
  title,
  onClick,
  children,
}: {
  active: boolean;
  title: string;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      title={title}
      aria-label={title}
      aria-pressed={active}
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
      className={cn(
        "flex h-6 min-w-7 items-center justify-center gap-1 rounded-md px-1.5 text-[11px] font-semibold text-muted-foreground transition-colors hover:text-foreground",
        active && "bg-popover text-primary ring-1 ring-primary/30",
      )}
    >
      {children}
    </button>
  );
}

function FlagVN() {
  return (
    <svg viewBox="0 0 30 20" className="h-2.5 w-3.5 rounded-[2px]" aria-hidden>
      <rect width="30" height="20" fill="#da251d" />
      <polygon
        fill="#ffff00"
        points="15,4 16.18,7.63 20,7.63 16.91,9.87 18.09,13.5 15,11.26 11.91,13.5 13.09,9.87 10,7.63 13.82,7.63"
      />
    </svg>
  );
}

function FlagUK() {
  return (
    <svg viewBox="0 0 60 30" className="h-2.5 w-3.5 rounded-[2px]" aria-hidden>
      <clipPath id="uk-clip">
        <path d="M0,0 v30 h60 v-30 z" />
      </clipPath>
      <g clipPath="url(#uk-clip)">
        <path d="M0,0 v30 h60 v-30 z" fill="#012169" />
        <path d="M0,0 L60,30 M60,0 L0,30" stroke="#fff" strokeWidth="6" />
        <path d="M0,0 L60,30 M60,0 L0,30" stroke="#C8102E" strokeWidth="2" />
        <path d="M30,0 v30 M0,15 h60" stroke="#fff" strokeWidth="10" />
        <path d="M30,0 v30 M0,15 h60" stroke="#C8102E" strokeWidth="6" />
      </g>
    </svg>
  );
}

/** Account dropdown opened from the logo / name block at the top of the sidebar. */
export function UserMenu({ triggerClassName, children }: { triggerClassName?: string; children: ReactNode }) {
  const { user, logout } = useAuth();
  const { t, lang, setLang } = useI18n();
  const { theme, setTheme } = useTheme();
  const router = useRouter();

  const themes: { value: Theme; icon: string; label: string }[] = [
    { value: "light", icon: "light_mode", label: t("theme.light") },
    { value: "dark", icon: "dark_mode", label: t("theme.dark") },
    { value: "system", icon: "desktop_windows", label: t("theme.system") },
  ];
  const langs: { value: Language; label: string; title: string; flag: ReactNode }[] = [
    { value: "vi", label: "VI", title: "Tiếng Việt", flag: <FlagVN /> },
    { value: "en", label: "EN", title: "English", flag: <FlagUK /> },
  ];

  const role = user?.role ?? "";

  return (
    <DropdownMenu>
      <DropdownMenuTrigger className={triggerClassName}>{children}</DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-56 rounded-xl p-1.5 shadow-xl select-none">
        <div className="px-2 py-1.5">
          <p className="truncate text-sm font-semibold">{user?.name}</p>
          <p className="truncate text-[11px] text-muted-foreground">
            {role ? role.charAt(0).toUpperCase() + role.slice(1) : ""}
          </p>
        </div>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={() => router.push("/profile")}>
          <span className="material-symbols-outlined text-muted-foreground" style={{ fontSize: 18 }}>
            person
          </span>
          {t("user.profile")}
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <div className="flex items-center justify-between gap-2 px-2 py-1.5 text-sm">
          <span>{t("theme.title")}</span>
          <Segmented>
            {themes.map((opt) => (
              <SegmentButton key={opt.value} active={theme === opt.value} title={opt.label} onClick={() => setTheme(opt.value)}>
                <span className="material-symbols-outlined" style={{ fontSize: 15 }}>
                  {opt.icon}
                </span>
              </SegmentButton>
            ))}
          </Segmented>
        </div>
        <div className="flex items-center justify-between gap-2 px-2 py-1.5 text-sm">
          <span>{t("language.title")}</span>
          <Segmented>
            {langs.map((opt) => (
              <SegmentButton key={opt.value} active={lang === opt.value} title={opt.title} onClick={() => setLang(opt.value)}>
                {opt.flag}
                {opt.label}
              </SegmentButton>
            ))}
          </Segmented>
        </div>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          variant="destructive"
          onClick={() => {
            if (!logout()) router.push("/login?logged_out=1");
          }}
        >
          <span className="material-symbols-outlined" style={{ fontSize: 18 }}>
            logout
          </span>
          {t("user.signOut")}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
