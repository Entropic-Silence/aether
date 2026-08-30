"use client";

import { useCallback, useEffect, useState } from "react";
import { Pencil, Plus, Trash2, Wand2, X } from "lucide-react";
import { api } from "@/lib/api";
import type { ImageModelInfo } from "@/lib/types";
import { AuthImage } from "@/components/AuthImage";
import { Button, IconBtn, Spinner } from "@/components/ui";

const inputCls =
  "w-full rounded-lg border border-[var(--border)] bg-transparent px-3 py-2 text-sm outline-none focus:border-accent";

const EMPTY = {
  provider_kind: "diffusers_local",
  name: "",
  model_ref: "",
  base_url: "",
  api_key: "",
  defaults: { width: 512, height: 512, steps: 25, cfg: 7.0 },
  limits: { max_width: 1024, max_height: 1024, max_steps: 50 },
  skill_text: "",
  enabled: true,
  is_default: false,
};

export default function AdminImagesPage() {
  const [models, setModels] = useState<ImageModelInfo[] | null>(null);
  const [form, setForm] = useState<typeof EMPTY | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [testing, setTesting] = useState<string | null>(null);
  const [testImage, setTestImage] = useState<{ fileId: string; info: string } | null>(null);

  const load = useCallback(() => {
    api.listImageModels().then(setModels).catch(() => setModels([]));
  }, []);
  useEffect(load, [load]);

  const save = async () => {
    if (!form) return;
    setBusy(true);
    setError(null);
    try {
      const payload = { ...form };
      if (editingId) {
        await api.updateImageModel(editingId, payload);
      } else {
        await api.createImageModel(payload);
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

  const test = async (id: string) => {
    setTesting(id);
    setTestImage(null);
    try {
      const res = await api.generateImage({
        prompt: "a simple blue circle on white background",
        model_id: id,
        optimize: false,
        steps: 10,
        admin_test: true,
      });
      setTestImage({ fileId: res.file_id, info: `${res.width}×${res.height} · ${(res.duration_ms / 1000).toFixed(1)}s` });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Test failed");
    } finally {
      setTesting(null);
    }
  };

  if (!models) return <Spinner className="h-6 w-6 text-[var(--muted)]" />;

  return (
    <div className="max-w-3xl">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Image models</h1>
          <p className="text-sm text-[var(--muted)]">
            独立于对话模型配置；支持本机 Diffusers、OpenAI Images、ComfyUI、自定义 ComfyUI 工作流、
            Automatic1111/Forge/SD.Next 与 Stability AI API。
          </p>
        </div>
        <Button variant="primary" onClick={() => { setForm({ ...EMPTY }); setEditingId(null); }}>
          <Plus size={15} /> Add image model
        </Button>
      </div>

      {form && (
        <div className="mb-6 rounded-xl border border-[var(--border)] p-4">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold">{editingId ? "Edit image model" : "New image model"}</h2>
            <IconBtn onClick={() => { setForm(null); setEditingId(null); }}><X size={16} /></IconBtn>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <label className="block">
              <span className="mb-1 block text-xs text-[var(--muted)]">Provider kind</span>
              <select className={inputCls} value={form.provider_kind}
                onChange={(e) => setForm({ ...form, provider_kind: e.target.value })}>
                <option value="diffusers_local">diffusers_local (this host)</option>
                <option value="krea2_local">krea2_local (Krea 2, this host)</option>
                <option value="comfyui">comfyui (ComfyUI server)</option>
                <option value="openai_images">openai_images (remote API)</option>
                <option value="automatic1111">automatic1111 (A1111 / Forge / SD.Next)</option>
                <option value="stability_api">stability_api (Stability AI v2beta)</option>
              </select>
            </label>
            <label className="block">
              <span className="mb-1 block text-xs text-[var(--muted)]">Display name</span>
              <input className={inputCls} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </label>
            <label className="block sm:col-span-2">
              <span className="mb-1 block text-xs text-[var(--muted)]">
                {form.provider_kind === "diffusers_local" || form.provider_kind === "krea2_local"
                  ? "Local model path"
                  : form.provider_kind === "comfyui" ? "Checkpoint name (ComfyUI models dir)"
                    : form.provider_kind === "stability_api" ? "Endpoint model (core / ultra / sd3)" : "Model ID (remote)"}
              </span>
              <input className={inputCls} value={form.model_ref} onChange={(e) => setForm({ ...form, model_ref: e.target.value })}
                placeholder={form.provider_kind === "comfyui" ? "sd_xl_base_1.0.safetensors" : "/path/to/model"} />
            </label>
            {!["diffusers_local", "krea2_local"].includes(form.provider_kind) && (
              <>
                <label className="block">
                  <span className="mb-1 block text-xs text-[var(--muted)]">Base URL</span>
                  <input className={inputCls} value={form.base_url} onChange={(e) => setForm({ ...form, base_url: e.target.value })}
                    placeholder={form.provider_kind === "comfyui" ? "http://localhost:8188" : form.provider_kind === "automatic1111" ? "http://localhost:7860" : form.provider_kind === "stability_api" ? "https://api.stability.ai/v2beta" : "https://api.example.com/v1"} />
                </label>
                <label className="block">
                  <span className="mb-1 block text-xs text-[var(--muted)]">API key（可选）</span>
                  <input className={inputCls} type="password" value={form.api_key} onChange={(e) => setForm({ ...form, api_key: e.target.value })} />
                </label>
              </>
            )}
            <label className="block">
              <span className="mb-1 block text-xs text-[var(--muted)]">Defaults / adapter options (JSON)</span>
              <input className={inputCls} value={JSON.stringify(form.defaults)}
                onChange={(e) => { try { setForm({ ...form, defaults: JSON.parse(e.target.value) }); } catch { /* wait for valid json */ } }} />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs text-[var(--muted)]">Limits (JSON: max_width,max_height,max_steps)</span>
              <input className={inputCls} value={JSON.stringify(form.limits)}
                onChange={(e) => { try { setForm({ ...form, limits: JSON.parse(e.target.value) }); } catch { /* wait for valid json */ } }} />
            </label>
            <label className="block sm:col-span-2">
              <span className="mb-1 block text-xs text-[var(--muted)]">Prompt skill (guides the optimizer LLM)</span>
              <textarea className={inputCls} rows={3} value={form.skill_text}
                onChange={(e) => setForm({ ...form, skill_text: e.target.value })}
                placeholder="What this model is good at, prompt style, negative prompt conventions…" />
            </label>
          </div>
          {form.provider_kind === "comfyui" && (
            <p className="mt-2 text-xs leading-5 text-[var(--muted)]">
              可在 Defaults 中加入 <span className="font-mono">workflows.txt2img/img2img/inpaint</span> 的 ComfyUI API 工作流。
              支持占位符：${"{prompt}"}、${"{negative_prompt}"}、${"{width}"}、${"{height}"}、${"{steps}"}、
              ${"{cfg}"}、${"{seed}"}、${"{checkpoint}"}、${"{source_image}"}、${"{mask_image}"}。
            </p>
          )}
          <div className="mt-3 flex items-center gap-4 text-sm">
            <label className="flex items-center gap-1.5">
              <input type="checkbox" checked={form.enabled} onChange={(e) => setForm({ ...form, enabled: e.target.checked })} /> Enabled
            </label>
            <label className="flex items-center gap-1.5">
              <input type="checkbox" checked={form.is_default} onChange={(e) => setForm({ ...form, is_default: e.target.checked })} /> Default
            </label>
          </div>
          {error && <div className="mt-3 text-sm text-red-500">{error}</div>}
          <div className="mt-3 flex gap-2">
            <Button variant="primary" onClick={save} disabled={busy || !form.name}>{busy ? <Spinner /> : "Save"}</Button>
            <Button onClick={() => { setForm(null); setEditingId(null); }}>Cancel</Button>
          </div>
        </div>
      )}

      {testImage && (
        <div className="mb-4 flex items-center gap-3 rounded-xl border border-[var(--border)] p-3">
          <AuthImage src={`/api/v1/files/${testImage.fileId}/download`} alt="test" className="h-24 w-24 rounded-lg object-cover" />
          <div className="text-sm">
            <div className="font-medium">Test generation succeeded</div>
            <div className="text-xs text-[var(--muted)]">{testImage.info}</div>
          </div>
        </div>
      )}

      <div className="space-y-3">
        {models.length === 0 && (
          <div className="rounded-xl border border-dashed border-[var(--border)] p-8 text-center text-sm text-[var(--muted)]">
            No image models configured.
          </div>
        )}
        {models.map((m) => (
          <div key={m.id} className="flex items-center justify-between rounded-xl border border-[var(--border)] px-4 py-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-medium">{m.name}</span>
                <span className="rounded bg-[var(--surface)] px-1.5 py-0.5 text-xs text-[var(--muted)]">{m.provider_kind}</span>
                {m.is_default && <span className="text-xs text-accent">default</span>}
              </div>
              <div className="truncate font-mono text-xs text-[var(--muted)]">{m.model_ref || m.base_url}</div>
            </div>
            <div className="flex shrink-0 items-center gap-1">
              <Button variant="ghost" className="!px-2" onClick={() => test(m.id)} disabled={testing === m.id}>
                {testing === m.id ? <Spinner /> : <Wand2 size={14} />} Test
              </Button>
              <IconBtn title="Edit" onClick={() => {
                setForm({
                  ...EMPTY,
                  provider_kind: m.provider_kind, name: m.name, model_ref: m.model_ref, base_url: m.base_url,
                  defaults: m.defaults as typeof EMPTY.defaults, limits: m.limits as typeof EMPTY.limits,
                  skill_text: m.skill_text, enabled: m.enabled, is_default: m.is_default,
                });
                setEditingId(m.id);
              }}>
                <Pencil size={15} />
              </IconBtn>
              <IconBtn title="Delete" onClick={async () => { await api.deleteImageModel(m.id); load(); }}>
                <Trash2 size={15} />
              </IconBtn>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
