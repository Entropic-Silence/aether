"use client";

import { useCallback, useEffect, useState } from "react";
import { Download, Pencil, Plus, RefreshCw, Trash2, Upload, X } from "lucide-react";
import { phase6Api } from "@/lib/api";
import type { SkillInfo } from "@/lib/types";
import { Button, IconBtn, Spinner } from "@/components/ui";

const inputCls =
  "w-full rounded-lg border border-[var(--border)] bg-transparent px-3 py-2 text-sm outline-none focus:border-accent";

const SCOPES = ["global", "workspace", "project", "user", "model", "tool", "image_model"];

const EMPTY = {
  name: "", version: "1.0.0", description: "", instructions: "", trigger: "",
  priority: 100, scope: "global", enabled: true,
};

export default function SkillsAdminPage() {
  const [skills, setSkills] = useState<SkillInfo[] | null>(null);
  const [form, setForm] = useState<typeof EMPTY | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    phase6Api.listSkills().then(setSkills).catch(() => setSkills([]));
  }, []);
  useEffect(load, [load]);

  const save = async () => {
    if (!form) return;
    setBusy(true);
    setError(null);
    try {
      if (editingId) await phase6Api.updateSkill(editingId, { ...form });
      else await phase6Api.createSkill({ ...form });
      setForm(null);
      setEditingId(null);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setBusy(false);
    }
  };

  const exportSkill = async (id: string, name: string) => {
    const res = await phase6Api.exportSkill(id);
    const blob = new Blob([JSON.stringify(res.skill, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${name}.skill.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const importSkill = async (file: File) => {
    try {
      const text = await file.text();
      if (file.name.toLowerCase().endsWith(".md")) await phase6Api.importMarkdownSkill(file.name, text);
      else await phase6Api.importSkill(JSON.parse(text));
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Import failed");
    }
  };

  const syncDeepSeek = async () => {
    setBusy(true);
    setError(null);
    try {
      await phase6Api.syncDeepSeekSkills();
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "DeepSeek Harness skill scan failed");
    } finally {
      setBusy(false);
    }
  };

  if (!skills) return <Spinner className="h-6 w-6 text-[var(--muted)]" />;

  return (
    <div className="max-w-3xl">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Skills</h1>
          <p className="text-sm text-[var(--muted)]">
            Install JSON or SKILL.md packages. DeepSeek Harness roots (.dsh/skills and .agents/skills) are supported.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg bg-[var(--surface)] px-3.5 py-2 text-sm font-medium hover:bg-[var(--border)]">
            <Upload size={15} /> Import skill
            <input type="file" accept=".json,.md" className="hidden"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) importSkill(f); e.target.value = ""; }} />
          </label>
          <Button onClick={syncDeepSeek} disabled={busy}><RefreshCw size={15} /> Scan DSH</Button>
          <Button variant="primary" onClick={() => { setForm({ ...EMPTY }); setEditingId(null); }}>
            <Plus size={15} /> New skill
          </Button>
        </div>
      </div>

      {form && (
        <div className="mb-6 rounded-xl border border-[var(--border)] p-4">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold">{editingId ? "Edit skill" : "New skill"}</h2>
            <IconBtn onClick={() => { setForm(null); setEditingId(null); }}><X size={16} /></IconBtn>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <label className="block"><span className="mb-1 block text-xs text-[var(--muted)]">Name</span>
              <input className={inputCls} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
            <label className="block"><span className="mb-1 block text-xs text-[var(--muted)]">Version</span>
              <input className={inputCls} value={form.version} onChange={(e) => setForm({ ...form, version: e.target.value })} /></label>
            <label className="block"><span className="mb-1 block text-xs text-[var(--muted)]">Scope</span>
              <select className={inputCls} value={form.scope} onChange={(e) => setForm({ ...form, scope: e.target.value })}>
                {SCOPES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select></label>
            <label className="block"><span className="mb-1 block text-xs text-[var(--muted)]">Priority (lower first)</span>
              <input type="number" className={inputCls} value={form.priority} onChange={(e) => setForm({ ...form, priority: Number(e.target.value) })} /></label>
            <label className="block sm:col-span-2"><span className="mb-1 block text-xs text-[var(--muted)]">Description</span>
              <input className={inputCls} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></label>
            <label className="block sm:col-span-2"><span className="mb-1 block text-xs text-[var(--muted)]">Instructions (injected into system prompt)</span>
              <textarea rows={4} className={inputCls} value={form.instructions} onChange={(e) => setForm({ ...form, instructions: e.target.value })} /></label>
          </div>
          <div className="mt-3 flex items-center gap-4 text-sm">
            <label className="flex items-center gap-1.5">
              <input type="checkbox" checked={form.enabled} onChange={(e) => setForm({ ...form, enabled: e.target.checked })} /> Enabled
            </label>
          </div>
          {error && <div className="mt-3 text-sm text-red-500">{error}</div>}
          <div className="mt-3 flex gap-2">
            <Button variant="primary" onClick={save} disabled={busy || !form.name || !form.instructions}>{busy ? <Spinner /> : "Save"}</Button>
            <Button onClick={() => { setForm(null); setEditingId(null); }}>Cancel</Button>
          </div>
        </div>
      )}

      <div className="space-y-3">
        {skills.length === 0 && (
          <div className="rounded-xl border border-dashed border-[var(--border)] p-8 text-center text-sm text-[var(--muted)]">
            No skills defined.
          </div>
        )}
        {skills.map((s) => (
          <div key={s.id} className="rounded-xl border border-[var(--border)] px-4 py-3">
            <div className="flex items-center justify-between">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-medium">{s.name}</span>
                  <span className="text-xs text-[var(--muted)]">v{s.version}</span>
                  <span className="rounded bg-[var(--surface)] px-1.5 py-0.5 text-xs text-[var(--muted)]">{s.scope}</span>
                  <span className="rounded bg-[var(--surface)] px-1.5 py-0.5 text-xs text-[var(--muted)]">{s.source}</span>
                  {!s.enabled && <span className="text-xs text-red-500">disabled</span>}
                </div>
                {s.description && <div className="mt-1 text-xs text-[var(--muted)]">{s.description}</div>}
              </div>
              <div className="flex shrink-0 items-center gap-1">
                <IconBtn title="Export" onClick={() => exportSkill(s.id, s.name)}><Download size={15} /></IconBtn>
                <IconBtn title="Edit" onClick={() => {
                  setForm({ name: s.name, version: s.version, description: s.description, instructions: s.instructions, trigger: s.trigger, priority: s.priority, scope: s.scope, enabled: s.enabled });
                  setEditingId(s.id);
                }}><Pencil size={15} /></IconBtn>
                <IconBtn title="Delete" onClick={async () => { await phase6Api.deleteSkill(s.id); load(); }}><Trash2 size={15} /></IconBtn>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
