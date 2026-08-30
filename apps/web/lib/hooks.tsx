"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { Branding, ModelInfo, UiSettings, User } from "./types";
import { api, getToken, setToken } from "./api";
import { type Locale, translate } from "./i18n";

type Theme = "light" | "dark" | "system";
const THEME_KEY = "aether_theme";
const LOCALE_KEY = "aether_locale";

interface AppState {
  user: User | null;
  setUser: (user: User | null) => void;
  authReady: boolean;
  branding: Branding | null;
  uiSettings: UiSettings | null;
  theme: Theme;
  setTheme: (theme: Theme) => void;
  isDark: boolean;
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: string, fallback?: string) => string;
  logout: () => void;
}

const AppContext = createContext<AppState | null>(null);

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const [branding, setBranding] = useState<Branding | null>(null);
  const [uiSettings, setUiSettings] = useState<UiSettings | null>(null);
  const [theme, setThemeState] = useState<Theme>("system");
  const [systemDark, setSystemDark] = useState(false);
  const [locale, setLocaleState] = useState<Locale>("zh-CN");

  useEffect(() => {
    api.branding().then(setBranding).catch(() => setBranding(null));
    const stored = window.localStorage.getItem(THEME_KEY) as Theme | null;
    if (stored) setThemeState(stored);
    const storedLocale = window.localStorage.getItem(LOCALE_KEY) as Locale | null;
    if (storedLocale === "zh-CN" || storedLocale === "en") setLocaleState(storedLocale);
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    setSystemDark(mq.matches);
    const listener = (e: MediaQueryListEvent) => setSystemDark(e.matches);
    mq.addEventListener("change", listener);
    return () => mq.removeEventListener("change", listener);
  }, []);

  useEffect(() => {
    if (!user) { setUiSettings(null); return; }
    api.uiSettings().then(setUiSettings).catch(() => setUiSettings(null));
  }, [user]);

  useEffect(() => {
    if (!getToken()) {
      setAuthReady(true);
      return;
    }
    api.me()
      .then(setUser)
      .catch(() => {
        setToken(null);
        setUser(null);
      })
      .finally(() => setAuthReady(true));
  }, []);

  const isDark = theme === "dark" || (theme === "system" && systemDark);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", isDark);
  }, [isDark]);

  useEffect(() => {
    if (!branding) return;
    document.title = branding.product_name;
    const hex = branding.accent_color?.trim();
    const match = /^#([0-9a-f]{6})$/i.exec(hex || "");
    if (match) {
      const value = match[1];
      document.documentElement.style.setProperty("--accent", `${parseInt(value.slice(0, 2), 16)} ${parseInt(value.slice(2, 4), 16)} ${parseInt(value.slice(4, 6), 16)}`);
    }
  }, [branding]);

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const setTheme = useCallback((next: Theme) => {
    setThemeState(next);
    window.localStorage.setItem(THEME_KEY, next);
  }, []);

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    window.localStorage.setItem(LOCALE_KEY, next);
  }, []);

  const t = useCallback((key: string, fallback?: string) => translate(locale, key, fallback), [locale]);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
    window.location.href = "/login";
  }, []);

  const value = useMemo(
    () => ({ user, setUser, authReady, branding, uiSettings, theme, setTheme, isDark, locale, setLocale, t, logout }),
    [user, authReady, branding, uiSettings, theme, isDark, locale, setTheme, setLocale, t, logout],
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): AppState {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used within AppProvider");
  return ctx;
}

export function useModelCatalog() {
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const load = useCallback(async () => {
    setLoading(true);
    try {
      setModels(await api.catalogModels());
    } catch {
      setModels([]);
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    if (getToken()) load();
  }, [load]);
  return { models, loading, reload: load };
}
