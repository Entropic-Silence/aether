"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Brain, Plus, Trash2 } from "lucide-react";
import { phase7Api } from "@/lib/api";
import type { MemoryInfo, UserPrefInfo } from "@/lib/types";
import { useApp } from "@/lib/hooks";
import { getToken } from "@/lib/api";
import { Button, IconBtn, Spinner, cn } from "@/components/ui";

const inputCls =
  "w-full rounded-lg border border-[var(--border)] bg-transparent px-3 py-2 text-sm outline-none focus:border-accent";

export default function SettingsPage() {
  const { theme, setTheme, user, branding, uiSettings, logout, locale, setLocale, t } = useApp();
  const [prefs, setPrefs] = useState<UserPrefInfo | null>(null);
  const [memories, setMemories] = useState<MemoryInfo[] | null>(null);
  const [newMemory, setNewMemory] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      window.location.href = "/login";
      return;
    }
    phase7Api.getMySettings().then(setPrefs).catch(() => setPrefs(null));
    phase7Api.listMemories().then(setMemories).catch(() => setMemories([]));
  }, []);

  const savePrefs = async (patch: Partial<UserPrefInfo>) => {
    if (!prefs) return;
    const updated = await phase7Api.patchMySettings(patch);
    setPrefs(updated);
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
  };

  const loadMemories = useCallback(() => {
    phase7Api.listMemories().then(setMemories).catch(() => setMemories([]));
  }, []);

  const options = [
    { id: "light", label: t("light", "Light") },
    { id: "dark", label: t("dark", "Dark") },
    { id: "system", label: t("system", "System") },
  ] as const;

  return (
    <div className="mx-auto w-full max-w-2xl px-4 py-8">
      <Link href="/" className="mb-6 inline-flex items-center gap-1.5 text-sm text-[var(--muted)] hover:text-[var(--fg)]">
        <ArrowLeft size={15} /> {t("backToChat", "Back to chat")}
      </Link>
      <h1 className="mb-6 text-xl font-semibold">{t("settings", "Settings")}</h1>

      <section className="border-b border-[var(--border)] py-4">
        <h2 className="mb-1 text-sm font-semibold">{t("general", "General")}</h2>
        <div className="text-sm text-[var(--muted)]">
          {t("signedInAs", "Signed in as")} {user?.email} ({user?.role}) · {branding?.product_name}
        </div>
      </section>

      <section className="border-b border-[var(--border)] py-4">
        <h2 className="mb-3 text-sm font-semibold">{t("theme", "Theme")}</h2>
        <div className="flex gap-2">
          {options.map((o) => (
            <button
              key={o.id}
              type="button"
              onClick={() => setTheme(o.id)}
              className={cn(
                "flex items-center gap-1.5 rounded-xl border border-[var(--border)] px-4 py-2 text-sm",
                theme === o.id && "border-accent text-accent",
              )}
            >
              {o.label}
            </button>
          ))}
        </div>
      </section>

      <section className="border-b border-[var(--border)] py-4">
        <h2 className="mb-3 text-sm font-semibold">{t("language", "Language")}</h2>
        <div className="flex gap-2">
          {([{"id":"zh-CN","label":t("chinese", "简体中文")},{"id":"en","label":t("english", "English")}] as const).map((o) => (
            <button key={o.id} type="button" onClick={() => setLocale(o.id)}
              className={cn("rounded-xl border border-[var(--border)] px-4 py-2 text-sm", locale === o.id && "border-accent text-accent")}>
              {o.label}
            </button>
          ))}
        </div>
      </section>

      {prefs && uiSettings?.features.custom_instructions !== false && (
        <section className="border-b border-[var(--border)] py-4">
          <h2 className="mb-3 text-sm font-semibold">{t("customInstructions", "Custom instructions")}</h2>
          <label className="mb-1 block text-xs text-[var(--muted)]">{t("aboutYou", "About you")}</label>
          <textarea
            rows={3}
            className={inputCls}
            defaultValue={prefs.about_me}
            onBlur={(e) => e.target.value !== prefs.about_me && savePrefs({ about_me: e.target.value })}
            placeholder={t("aboutPlaceholder", "What should the assistant know about you?")}
          />
          <label className="mb-1 mt-3 block text-xs text-[var(--muted)]">{t("responseStyle", "How should the assistant respond?")}</label>
          <textarea
            rows={3}
            className={inputCls}
            defaultValue={prefs.response_style}
            onBlur={(e) => e.target.value !== prefs.response_style && savePrefs({ response_style: e.target.value })}
            placeholder={t("stylePlaceholder", "Tone, format, constraints…")}
          />
          {saved && <div className="mt-2 text-xs text-accent">{t("saved", "Saved")}</div>}
        </section>
      )}

      {uiSettings?.features.memory !== false && <section className="border-b border-[var(--border)] py-4">
        <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold">
          <Brain size={15} /> {t("memory", "Memory")}
        </h2>
        {prefs && (
          <div className="mb-3 space-y-2 text-sm">
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={prefs.memory_enabled}
                onChange={(e) => savePrefs({ memory_enabled: e.target.checked })} />
              {t("enableMemory", "Enable memory")}
            </label>
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={prefs.memory_reference}
                onChange={(e) => savePrefs({ memory_reference: e.target.checked })} />
              {t("referenceMemory", "Reference saved memory in chats")}
            </label>
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={prefs.memory_auto_capture}
                onChange={(e) => savePrefs({ memory_auto_capture: e.target.checked })} />
              {t("autoCaptureMemory", "Auto-capture durable facts from conversations")}
            </label>
          </div>
        )}
        <div className="mb-2 flex gap-2">
          <input
            value={newMemory}
            onChange={(e) => setNewMemory(e.target.value)}
            onKeyDown={async (e) => {
              if (e.key === "Enter" && newMemory.trim()) {
                await phase7Api.createMemory({ content: newMemory.trim() });
                setNewMemory("");
                loadMemories();
              }
            }}
            placeholder={t("addMemory", "Add a memory, e.g. 'I prefer Python'")}
            className={inputCls}
          />
          <Button
            variant="primary"
            disabled={!newMemory.trim()}
            onClick={async () => {
              await phase7Api.createMemory({ content: newMemory.trim() });
              setNewMemory("");
              loadMemories();
            }}
          >
            <Plus size={15} />
          </Button>
        </div>
        {!memories ? (
          <Spinner className="h-5 w-5 text-[var(--muted)]" />
        ) : memories.length === 0 ? (
          <div className="rounded-xl border border-dashed border-[var(--border)] p-6 text-center text-sm text-[var(--muted)]">
            {t("noMemories", "No memories yet.")}
          </div>
        ) : (
          <div className="space-y-2">
            {memories.map((m) => (
              <div key={m.id} className="flex items-center justify-between rounded-xl border border-[var(--border)] px-3 py-2">
                <div className="min-w-0">
                  <div className={cn("text-sm", !m.enabled && "line-through opacity-50")}>{m.content}</div>
                  <div className="text-[10px] text-[var(--muted)]">{m.kind} · {m.category} · {new Date(m.updated_at).toLocaleDateString()}</div>
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  <IconBtn title={m.enabled ? t("disable", "Disable") : t("enable", "Enable")}
                    onClick={async () => { await phase7Api.updateMemory(m.id, { enabled: !m.enabled }); loadMemories(); }}>
                    <span className={cn("text-xs", m.enabled ? "text-accent" : "text-[var(--muted)]")}>{m.enabled ? "on" : "off"}</span>
                  </IconBtn>
                  <IconBtn title={t("delete", "Delete")} onClick={async () => { await phase7Api.deleteMemory(m.id); loadMemories(); }}>
                    <Trash2 size={14} />
                  </IconBtn>
                </div>
              </div>
            ))}
            <div className="pt-1">
              <Button variant="danger" onClick={async () => { await phase7Api.clearMemories(); loadMemories(); }}>
                {t("clearMemories", "Clear all memories")}
              </Button>
            </div>
          </div>
        )}
      </section>}

      <section className="border-b border-[var(--border)] py-4">
        <h2 className="mb-3 text-sm font-semibold">{t("dailyQuotas", "Daily quotas")}</h2>
        <p className="mb-2 text-xs text-[var(--muted)]">{t("unlimitedHint", "0 = unlimited. Applies to your account.")}</p>
        <div className="grid grid-cols-2 gap-3">
          <label className="block"><span className="mb-1 block text-xs text-[var(--muted)]">{t("messagesPerDay", "Messages / day")}</span>
            <input type="number" className={inputCls} defaultValue={prefs?.daily_message_limit ?? 0}
              onBlur={(e) => savePrefs({ daily_message_limit: Number(e.target.value) })} /></label>
          <label className="block"><span className="mb-1 block text-xs text-[var(--muted)]">{t("tokensPerDay", "Tokens / day")}</span>
            <input type="number" className={inputCls} defaultValue={prefs?.daily_token_limit ?? 0}
              onBlur={(e) => savePrefs({ daily_token_limit: Number(e.target.value) })} /></label>
          <label className="block"><span className="mb-1 block text-xs text-[var(--muted)]">{t("imagesPerDay", "Images / day")}</span>
            <input type="number" className={inputCls} defaultValue={prefs?.daily_image_limit ?? 0}
              onBlur={(e) => savePrefs({ daily_image_limit: Number(e.target.value) })} /></label>
          <label className="block"><span className="mb-1 block text-xs text-[var(--muted)]">{t("searchesPerDay", "Searches / day")}</span>
            <input type="number" className={inputCls} defaultValue={prefs?.daily_search_limit ?? 0}
              onBlur={(e) => savePrefs({ daily_search_limit: Number(e.target.value) })} /></label>
        </div>
      </section>

      <section className="py-4">
        <h2 className="mb-3 text-sm font-semibold">{t("account", "Account")}</h2>
        <button type="button" onClick={logout} className="rounded-xl border border-red-500/40 px-4 py-2 text-sm text-red-500 hover:bg-red-500/10">
          {t("logout", "Log out")}
        </button>
      </section>
    </div>
  );
}
