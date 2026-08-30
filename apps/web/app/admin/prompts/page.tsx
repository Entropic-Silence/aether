"use client";

import { useCallback, useEffect, useState } from "react";
import { Check, Pencil, Plus, Trash2, X } from "lucide-react";
import { phase8Api } from "@/lib/api";
import type { PromptInfo } from "@/lib/types";
import { Button, IconBtn, Spinner } from "@/components/ui";

const inputCls =
  "w-full rounded-lg border border-[var(--border)] bg-transparent px-3 py-2 text-sm outline-none focus:border-accent";

export default function PromptsAdminPage() {
  const [prompts, setPrompts] = useState<PromptInfo[] | null>(null);
  const [form, setForm] = useState<{ name: string; text: string } | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    phase8Api.listPrompts().then(setPrompts).catch(() => setPrompts([]));
  }, []);
  useEffect(load, [load]);

  const save = async () => {
    if (!form) return;
    setBusy(true);
    setError(null);
    try {
      if (editing) await phase8Api.updatePrompt(editing, { text: form.text });
      else await phase8Api.createPrompt(form);
      setForm(null);
      setEditing(null);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setBusy(false);
    }
  };

  const activate = async (p: PromptInfo) => {
    if (p.status !== "published") {
      await phase8Api.updatePrompt(p.id, { status: "published" });
    }
    await phase8Api.activatePrompt(p.id);
    load();
  };

  return (
    <div className="max-w-3xl">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">System prompts</h1>
          <p className="text-sm text-[var(--muted)]">Versioned base prompts. The active one overrides the default.</p>
        </div>
        <Button variant="primary" onClick={() => { setForm({ name: "default", text: "" }); setEditing(null); }}>
          <Plus size={15} /> New prompt
        </Button>
      </div>

      {form && (
        <div className="mb-6 rounded-xl border border-[var(--border)] p-4">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold">{editing ? "Edit prompt" : "New prompt"}</h2>
            <IconBtn onClick={() => { setForm(null); setEditing(null); }}><X size={16} /></IconBtn>
          </div>
          {!editing && (
            <label className="mb-3 block"><span className="mb-1 block text-xs text-[var(--muted)]">Name</span>
              <input className={inputCls} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
          )}
          <label className="block"><span className="mb-1 block text-xs text-[var(--muted)]">Prompt text</span>
            <textarea rows={6} className={inputCls} value={form.text} onChange={(e) => setForm({ ...form, text: e.target.value })} /></label>
          {error && <div className="mt-3 text-sm text-red-500">{error}</div>}
          <div className="mt-3 flex gap-2">
            <Button variant="primary" onClick={save} disabled={busy}>{busy ? <Spinner /> : "Save"}</Button>
            <Button onClick={() => { setForm(null); setEditing(null); }}>Cancel</Button>
          </div>
        </div>
      )}

      {!prompts ? (
        <Spinner className="h-6 w-6 text-[var(--muted)]" />
      ) : prompts.length === 0 ? (
        <div className="rounded-xl border border-dashed border-[var(--border)] p-8 text-center text-sm text-[var(--muted)]">
          No system prompts. The built-in default is used.
        </div>
      ) : (
        <div className="space-y-3">
          {prompts.map((p) => (
            <div key={p.id} className="rounded-xl border border-[var(--border)] px-4 py-3">
              <div className="flex items-center justify-between">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{p.name}</span>
                    <span className="text-xs text-[var(--muted)]">v{p.version}</span>
                    <span className={p.status === "published" ? "rounded bg-accent/10 px-1.5 py-0.5 text-xs text-accent" : "rounded bg-[var(--surface)] px-1.5 py-0.5 text-xs text-[var(--muted)]"}>
                      {p.status}
                    </span>
                    {p.is_active && <span className="rounded bg-accent px-1.5 py-0.5 text-xs text-white">active</span>}
                  </div>
                  <div className="mt-1 line-clamp-2 text-xs text-[var(--muted)]">{p.text || "(empty)"}</div>
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  {!p.is_active && (
                    <Button variant="ghost" className="!px-2" onClick={() => activate(p)}>
                      <Check size={14} /> Activate
                    </Button>
                  )}
                  <IconBtn title="Edit" onClick={() => { setForm({ name: p.name, text: p.text }); setEditing(p.id); }}>
                    <Pencil size={15} />
                  </IconBtn>
                  {!p.is_active && (
                    <IconBtn title="Delete" onClick={async () => { await phase8Api.deletePrompt(p.id); load(); }}>
                      <Trash2 size={15} />
                    </IconBtn>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
