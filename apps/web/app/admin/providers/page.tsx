"use client";

import { useCallback, useEffect, useState } from "react";
import { Pencil, Plug, Plus, RefreshCw, Trash2, X } from "lucide-react";
import { api } from "@/lib/api";
import type { Provider } from "@/lib/types";
import { Button, IconBtn, Spinner } from "@/components/ui";

const EMPTY = {
  kind: "openai_compatible",
  name: "",
  base_url: "",
  api_key: "",
  headers: {} as Record<string, string>,
  proxy: "",
  timeout_ms: 120000,
  retry: { max: 2, backoff_ms: 500 } as { max?: number; backoff_ms?: number },
  concurrency: 8,
  organization: "",
  project: "",
  enabled: true,
};

export default function ProvidersPage() {
  const [providers, setProviders] = useState<Provider[] | null>(null);
  const [editing, setEditing] = useState<typeof EMPTY | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api.listProviders().then(setProviders).catch(() => setProviders([]));
  }, []);
  useEffect(load, [load]);

  const save = async () => {
    if (!editing) return;
    setBusy(true);
    setError(null);
    try {
      if (editingId) await api.updateProvider(editingId, editing);
      else await api.createProvider(editing);
      setEditing(null);
      setEditingId(null);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setBusy(false);
    }
  };

  const test = async (id: string) => {
    setTestResult((t) => ({ ...t, [id]: "testing" }));
    const res = await api.testProvider(id);
    setTestResult((t) => ({
      ...t,
      [id]: res.ok ? `ok (${res.models?.length ?? 0} models)` : `failed: ${JSON.stringify(res.error)}`,
    }));
  };

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Providers</h1>
          <p className="text-sm text-[var(--muted)]">Model service sources. OpenAI-compatible is the baseline protocol.</p>
        </div>
        <Button variant="primary" onClick={() => { setEditing({ ...EMPTY }); setEditingId(null); }}>
          <Plus size={15} /> Add provider
        </Button>
      </div>

      {editing && (
        <div className="mb-6 rounded-xl border border-[var(--border)] p-4">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold">{editingId ? "Edit provider" : "New provider"}</h2>
            <IconBtn onClick={() => { setEditing(null); setEditingId(null); }}><X size={16} /></IconBtn>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Name">
              <input className={inputCls} value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value })} placeholder="Local vLLM" />
            </Field>
            <Field label="Base URL">
              <input className={inputCls} value={editing.base_url} onChange={(e) => setEditing({ ...editing, base_url: e.target.value })} placeholder="http://localhost:8000/v1" />
            </Field>
            <Field label="API Key (encrypted at rest)">
              <input className={inputCls} type="password" value={editing.api_key} onChange={(e) => setEditing({ ...editing, api_key: e.target.value })} placeholder={editingId ? "leave blank to keep" : "sk-..."} />
            </Field>
            <Field label="Kind">
              <select className={inputCls} value={editing.kind} onChange={(e) => setEditing({ ...editing, kind: e.target.value })}>
                <option value="openai_compatible">OpenAI-compatible</option>
              </select>
            </Field>
            <Field label="Proxy (optional)">
              <input className={inputCls} value={editing.proxy} onChange={(e) => setEditing({ ...editing, proxy: e.target.value })} />
            </Field>
            <Field label="Timeout (ms)">
              <input className={inputCls} type="number" value={editing.timeout_ms} onChange={(e) => setEditing({ ...editing, timeout_ms: Number(e.target.value) })} />
            </Field>
          </div>
          {error && <div className="mt-3 text-sm text-red-500">{error}</div>}
          <div className="mt-4 flex gap-2">
            <Button variant="primary" onClick={save} disabled={busy || !editing.name || !editing.base_url}>
              {busy ? <Spinner /> : "Save"}
            </Button>
            <Button onClick={() => { setEditing(null); setEditingId(null); }}>Cancel</Button>
          </div>
        </div>
      )}

      {!providers ? (
        <Spinner className="h-6 w-6 text-[var(--muted)]" />
      ) : (
        <div className="space-y-3">
          {providers.length === 0 && (
            <div className="rounded-xl border border-dashed border-[var(--border)] p-8 text-center text-sm text-[var(--muted)]">
              <Plug className="mx-auto mb-2" size={22} />
              No providers configured. Add an OpenAI-compatible endpoint such as vLLM or SGLang.
            </div>
          )}
          {providers.map((p) => (
            <div key={p.id} className="flex items-center justify-between rounded-xl border border-[var(--border)] px-4 py-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-medium">{p.name}</span>
                  <span className="rounded bg-[var(--surface)] px-1.5 py-0.5 text-xs text-[var(--muted)]">{p.kind}</span>
                  {!p.enabled && <span className="text-xs text-red-500">disabled</span>}
                </div>
                <div className="truncate font-mono text-xs text-[var(--muted)]">{p.base_url}</div>
                {testResult[p.id] && (
                  <div className={`text-xs ${testResult[p.id].startsWith("ok") ? "text-accent" : "text-red-500"}`}>
                    {testResult[p.id]}
                  </div>
                )}
              </div>
              <div className="flex shrink-0 items-center gap-1">
                <Button onClick={() => test(p.id)} variant="ghost" className="!px-2">
                  <RefreshCw size={14} /> Test
                </Button>
                <IconBtn title="Edit" onClick={() => {
                  setEditing({ ...EMPTY, ...p, api_key: "", retry: p.retry ?? { max: 2, backoff_ms: 500 } });
                  setEditingId(p.id);
                }}>
                  <Pencil size={15} />
                </IconBtn>
                <IconBtn title="Delete" onClick={async () => { await api.deleteProvider(p.id); load(); }}>
                  <Trash2 size={15} />
                </IconBtn>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const inputCls =
  "w-full rounded-lg border border-[var(--border)] bg-transparent px-3 py-2 text-sm outline-none focus:border-accent";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-[var(--muted)]">{label}</span>
      {children}
    </label>
  );
}
