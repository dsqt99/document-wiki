"use client";

import React, { createContext, useContext, useEffect, useState, useSyncExternalStore } from "react";
import { isEmbedded, useHostTheme } from "@/lib/embed";

export type Theme = "light" | "dark" | "system";

type ThemeContextType = {
  theme: Theme;
  resolvedTheme: "light" | "dark";
  setTheme: (theme: Theme) => void;
};

// Lựa chọn của người dùng đọc từ localStorage như một store ngoài, để không phải
// setState trong effect lúc mount. Khi nhúng trong chatbot chỉ giữ trong phiên.
const THEME_KEY = "dw-theme";
const themeListeners = new Set<() => void>();
let embeddedTheme: Theme | null = null;

const asTheme = (value: unknown): Theme | null =>
  value === "light" || value === "dark" || value === "system" ? value : null;

function readSavedTheme(): Theme {
  if (embeddedTheme) return embeddedTheme;
  try {
    return asTheme(localStorage.getItem(THEME_KEY)) ?? "system";
  } catch {
    return "system";
  }
}

function subscribeSavedTheme(onChange: () => void) {
  themeListeners.add(onChange);
  const onStorage = (event: StorageEvent) => {
    if (event.key === THEME_KEY) onChange();
  };
  window.addEventListener("storage", onStorage);
  return () => {
    themeListeners.delete(onChange);
    window.removeEventListener("storage", onStorage);
  };
}

function saveTheme(value: Theme) {
  if (isEmbedded()) {
    embeddedTheme = value;
  } else {
    try {
      localStorage.setItem(THEME_KEY, value);
    } catch {
      embeddedTheme = value;
    }
  }
  themeListeners.forEach((listener) => listener());
}

const ThemeContext = createContext<ThemeContextType>({
  theme: "system",
  resolvedTheme: "light",
  setTheme: () => {},
});

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const theme = useSyncExternalStore(subscribeSavedTheme, readSavedTheme, () => "system" as Theme);
  const [resolvedTheme, setResolvedTheme] = useState<"light" | "dark">("light");

  // Nhúng trong chatbot: theo giao diện trang cha, không ghi đè lựa chọn khi mở wiki trực tiếp.
  const hostTheme = useHostTheme();
  const activeTheme: Theme = hostTheme ?? theme;

  useEffect(() => {
    if (isEmbedded()) document.documentElement.dataset.embed = "1";
  }, []);

  // Apply theme class to documentElement
  useEffect(() => {
    const root = document.documentElement;
    const media = window.matchMedia("(prefers-color-scheme: dark)");

    const apply = () => {
      let isDark = false;
      if (activeTheme === "dark") {
        isDark = true;
      } else if (activeTheme === "light") {
        isDark = false;
      } else {
        isDark = media.matches;
      }

      setResolvedTheme(isDark ? "dark" : "light");
      if (isDark) {
        root.classList.add("dark");
      } else {
        root.classList.remove("dark");
      }
    };

    apply();

    const listener = () => {
      if (activeTheme === "system") {
        apply();
      }
    };
    media.addEventListener("change", listener);
    return () => media.removeEventListener("change", listener);
  }, [activeTheme]);

  const setTheme = (newTheme: Theme) => saveTheme(newTheme);

  return (
    <ThemeContext.Provider value={{ theme: activeTheme, resolvedTheme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  return useContext(ThemeContext);
}
