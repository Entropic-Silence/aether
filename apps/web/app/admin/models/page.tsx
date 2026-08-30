"use client";

import { useCallback, useEffect, useState } from "react";
import { FlaskConical, Pencil, Plus, Star, Trash2, X } from "lucide-react";
import { api } from "@/lib/api";
import type { ModelInfo, Provider } from "@/lib/types";
import { Button, IconBtn, Spinner, cn } from "@/components/ui";

const BOOL_CAPS = [
  "image_input", "audio_input", "video_input", "image_generation", "image_edit",
  "reasoning", "tool_calling", "parallel_tool_calling", "structured_output",
  "json_mode", "embeddings", "file_input", "web_search_native", "tts", "stt",
];

const EMPTY_FORM = {
  provider_id: "",
  model_id: "",
  display_name: "",
  description: "",
  model_family: "",
  model_type: "chat",
  context_window: 4096,
  max_output_tokens: 2048,
  enabled: true,
  is_default: false,
  priority: 100,
  weight: 1,
  capabilities: {} as Record<string, boolean>,
  extra_body: "{}",
};

export default function ModelsPage() {
  const [models, setModels] = useState<ModelInfo[] | null>(null);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [form, setForm] = useState<typeof EMPTY_FORM | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [probeBusy, setProbeBusy] = useState<string | null>(null);
  const [testModel, setTestModel] = useState<ModelInfo | null>(null);

  const load = useCallback(() => {
    api.listModels().then(setModels).catch(() => setModels([]));
    api.listProviders().then(setProviders).catch(() => setProviders([]));
  }, []);
  useEffect(load, [load]);

  const openNew = () => {
    setForm({ ...EMPTY_FORM, provider_id: providers[0]?.id ?? "" });
    setEditingId(null);
  };

  const openEdit = (m: ModelInfo) => {
    const caps: Record<string, boolean> = {};
    for (const key of BOOL_CAPS) caps[key] = m.effective_capabilities?.[key] === true;
    setForm({
      provider_id: m.provider_id,
      model_id: m.model_id,
      display_name: m.display_name,
      description: m.description,
      model_family: m.model_family,
      model_type: m.model_type || "chat",
      context_window: m.context_window,
      max_output_tokens: m.max_output_tokens,
      enabled: m.enabled,
      is_default: m.is_default,
      priority: m.priority,
      weight: m.weight,
      capabilities: caps,
      extra_body: JSON.stringify(m.extra_body ?? {}, null, 2),
    });
    setEditingId(m.id);
  };

  const save = async () => {
    if (!form) return;
    setBusy(true);
    setError(null);
    let extraBody = {};
    try {
      extraBody = JSON.parse(form.extra_body || "{}");
    } catch {
      setError("Extra body must be valid JSON");
      setBusy(false);
      return;
    }
    const payload = { ...form, extra_body: extraBody };
    try {
      if (editingId) {
        const { provider_id, model_id, ...patch } = payload;
        await api.updateModel(editingId, patch);
      } else {
        await api.createModel(payload);
      }
      setForm(null);
      setEditingId(null);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setBusy(false);
    }
  };

  const probe = async (id: string) => {
    setProbeBusy(id);
    try {
      await api.probeModel(id);
      load();
    } finally {
      setProbeBusy(null);
    }
  };

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Models</h1>
          <p className="text-sm text-[var(--muted)]">
            Capabilities drive the UI. Probe to auto-detect, then override manually — admin has final say.
          </p>
        </div>
        <Button variant="primary" onClick={openNew} disabled={providers.length === 0}>
          <Plus size={15} /> Add model
        </Button>
      </div>

      {providers.length === 0 && (
        <div className="mb-4 rounded-xl border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-600">
          Add a provider first — models attach to providers.
        </div>
      )}

      {form && (
        <div className="mb-6 rounded-xl border border-[var(--border)] p-4">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold">{editingId ? "Edit model" : "New model"}</h2>
            <IconBtn onClick={() => { setForm(null); setEditingId(null); }}><X size={16} /></IconBtn>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <Field label="Provider">
              <select className={inputCls} value={form.provider_id} disabled={Boolean(editingId)}
                onChange={(e) => setForm({ ...form, provider_id: e.target.value })}>
                {providers.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </Field>
            <Field label="Model ID (remote)">
              <input className={inputCls} value={form.model_id} disabled={Boolean(editingId)}
                onChange={(e) => setForm({ ...form, model_id: e.target.value })} placeholder="Qwen3-32B" />
            </Field>
            <Field label="Display name">
              <input className={inputCls} value={form.display_name}
                onChange={(e) => setForm({ ...form, display_name: e.target.value })} />
            </Field>
            <Field label="Model family">
              <input className={inputCls} value={form.model_family}
                onChange={(e) => setForm({ ...form, model_family: e.target.value })} placeholder="qwen3" />
            </Field>
            <Field label="Model type">
              <select className={inputCls} value={form.model_type}
                onChange={(e) => setForm({ ...form, model_type: e.target.value })}>
                <option value="chat">Chat (LLM)</option>
                <option value="embedding">Embedding</option>
              </select>
            </Field>
            <Field label="Context window">
              <input className={inputCls} type="number" value={form.context_window}
                onChange={(e) => setForm({ ...form, context_window: Number(e.target.value) })} />
            </Field>
            <Field label="Max output tokens">
              <input className={inputCls} type="number" value={form.max_output_tokens}
                onChange={(e) => setForm({ ...form, max_output_tokens: Number(e.target.value) })} />
            </Field>
            <Field label="Priority (lower = preferred)">
              <input className={inputCls} type="number" value={form.priority}
                onChange={(e) => setForm({ ...form, priority: Number(e.target.value) })} />
            </Field>
            <Field label="Description">
              <input className={inputCls} value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })} />
            </Field>
            <Field label="Extra body JSON (vLLM/SGLang params)">
              <textarea className={cn(inputCls, "font-mono text-xs")} rows={2} value={form.extra_body}
                onChange={(e) => setForm({ ...form, extra_body: e.target.value })} />
            </Field>
          </div>

          <div className="mt-4">
            <div className="mb-2 text-xs font-semibold text-[var(--muted)]">Capabilities</div>
            <div className="flex flex-wrap gap-2">
              {BOOL_CAPS.map((cap) => (
                <button key={cap} type="button"
                  onClick={() => setForm({ ...form, capabilities: { ...form.capabilities, [cap]: !form.capabilities[cap] } })}
                  className={cn(
                    "rounded-full border px-3 py-1 text-xs",
                    form.capabilities[cap]
                      ? "border-accent bg-accent/10 text-accent"
                      : "border-[var(--border)] text-[var(--muted)]",
                  )}>
                  {cap}
                </button>
              ))}
            </div>
          </div>

          <div className="mt-4 flex items-center gap-4 text-sm">
            <label className="flex items-center gap-1.5">
              <input type="checkbox" checked={form.enabled} onChange={(e) => setForm({ ...form, enabled: e.target.checked })} />
              Enabled
            </label>
            <label className="flex items-center gap-1.5">
              <input type="checkbox" checked={form.is_default} onChange={(e) => setForm({ ...form, is_default: e.target.checked })} />
              Default model
            </label>
          </div>

          {error && <div className="mt-3 text-sm text-red-500">{error}</div>}
          <div className="mt-4 flex gap-2">
            <Button variant="primary" onClick={save} disabled={busy || !form.model_id || !form.provider_id}>
              {busy ? <Spinner /> : "Save"}
            </Button>
            <Button onClick={() => { setForm(null); setEditingId(null); }}>Cancel</Button>
          </div>
        </div>
      )}

      {!models ? (
        <Spinner className="h-6 w-6 text-[var(--muted)]" />
      ) : (
        <div className="space-y-3">
          {models.map((m) => {
            const caps = m.effective_capabilities ?? {};
            return (
              <div key={m.id} className="rounded-xl border border-[var(--border)] px-4 py-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{m.display_name}</span>
                      {m.is_default && <Star size={13} className="fill-accent text-accent" />}
                      {!m.enabled && <span className="text-xs text-red-500">disabled</span>}
                      <span className={cn(
                        "rounded px-1.5 py-0.5 text-[10px]",
                        m.probe_status === "probed" ? "bg-accent/10 text-accent" : "bg-[var(--surface)] text-[var(--muted)]",
                      )}>
                        {m.probe_status}
                      </span>
                    </div>
                    <div className="truncate font-mono text-xs text-[var(--muted)]">
                      {m.model_id} · {m.provider_name} · ctx {m.context_window}
                    </div>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {Object.entries(caps).filter(([, v]) => v === true).map(([k]) => (
                        <span key={k} className="rounded bg-[var(--surface)] px-1.5 py-0.5 text-[10px] text-[var(--muted)]">{k}</span>
                      ))}
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    <Button variant="ghost" className="!px-2" onClick={() => probe(m.id)} disabled={probeBusy === m.id}>
                      {probeBusy === m.id ? <Spinner /> : <FlaskConical size={14} />} Probe
                    </Button>
                    <Button variant="ghost" className="!px-2" onClick={() => setTestModel(m)}>Test</Button>
                    <IconBtn title="Edit" onClick={() => openEdit(m)}><Pencil size={15} /></IconBtn>
                    <IconBtn title="Delete" onClick={async () => { await api.deleteModel(m.id); load(); }}>
                      <Trash2 size={15} />
                    </IconBtn>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {testModel && <TestDialog model={testModel} onClose={() => setTestModel(null)} />}
    </div>
  );
}

function TestDialog({ model, onClose }: { model: ModelInfo; onClose: () => void }) {
  const [prompt, setPrompt] = useState("Hello! Reply in one short sentence.");
  const [result, setResult] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true);
    setResult(null);
    const res = await api.testModel(model.id, prompt);
    setResult(JSON.stringify(res, null, 2));
    setBusy(false);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div className="max-h-[80vh] w-full max-w-2xl overflow-y-auto rounded-2xl bg-[var(--bg)] p-5" onClick={(e) => e.stopPropagation()}>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold">Test · {model.display_name}</h2>
          <IconBtn onClick={onClose}><X size={16} /></IconBtn>
        </div>
        <textarea className={cn(inputCls, "font-mono text-xs")} rows={2} value={prompt} onChange={(e) => setPrompt(e.target.value)} />
        <div className="mt-2">
          <Button variant="primary" onClick={run} disabled={busy}>{busy ? <Spinner /> : "Run"}</Button>
        </div>
        {result && (
          <pre className="mt-3 max-h-72 overflow-auto rounded-xl bg-[var(--surface)] p-3 text-xs">{result}</pre>
        )}
      </div>
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
