"use client";

import React, { createContext, useContext, useEffect, useState, useSyncExternalStore } from "react";

export type Theme = "light" | "dark" | "system";

type ThemeContextType = {
  theme: Theme;
  resolvedTheme: "light" | "dark";
  setTheme: (theme: Theme) => void;
};

// Lựa chọn của người dùng đọc từ localStorage như một store ngoài, để không phải
// setState trong effect lúc mount.
const THEME_KEY = "dw-theme";
const themeListeners = new Set<() => void>();

const asTheme = (value: unknown): Theme | null =>
  value === "light" || value === "dark" || value === "system" ? value : null;

function readSavedTheme(): Theme {
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
  try {
    localStorage.setItem(THEME_KEY, value);
  } catch {
    // localStorage bị chặn: lựa chọn chỉ áp dụng cho lần xem này.
  }
  themeListeners.forEach((listener) => listener());
}

const ThemeContext = createContext<ThemeContextType>({
  theme: "system",
  resolvedTheme: "light",
  setTheme: () => {},
});

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const activeTheme = useSyncExternalStore(subscribeSavedTheme, readSavedTheme, () => "system" as Theme);
  const [resolvedTheme, setResolvedTheme] = useState<"light" | "dark">("light");

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
