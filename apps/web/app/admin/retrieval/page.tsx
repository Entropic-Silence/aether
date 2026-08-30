"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { ModelInfo } from "@/lib/types";
import { Button, Spinner } from "@/components/ui";

export default function RetrievalSettingsPage() {
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [embeddingModelId, setEmbeddingModelId] = useState("");
  const [visionModelId, setVisionModelId] = useState("");
  const [chunkSize, setChunkSize] = useState(1200);
  const [chunkOverlap, setChunkOverlap] = useState(150);
  const [topK, setTopK] = useState(6);
  const [threshold, setThreshold] = useState(0);
  const [loading, setLoading] = useState(true);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [all, retrieval, vision] = await Promise.all([
          api.listModels(),
          api.retrievalSettings(),
          api.visionFallback(),
        ]);
        setModels(all);
        setEmbeddingModelId((retrieval.embedding_model_id as string) ?? "");
        setChunkSize((retrieval.chunk_size as number) ?? 1200);
        setChunkOverlap((retrieval.chunk_overlap as number) ?? 150);
        setTopK((retrieval.top_k as number) ?? 6);
        setThreshold((retrieval.score_threshold as number) ?? 0);
        setVisionModelId(vision.model_id ?? "");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const save = async () => {
    setSaved(false);
    setError(null);
    try {
      await api.updateRetrievalSettings({
        embedding_model_id: embeddingModelId || null,
        chunk_size: chunkSize,
        chunk_overlap: chunkOverlap,
        top_k: topK,
        score_threshold: threshold,
      });
      await api.updateVisionFallback(visionModelId || null);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    }
  };

  if (loading) return <Spinner className="h-6 w-6 text-[var(--muted)]" />;

  const visionCandidates = models.filter((m) => m.effective_capabilities?.image_input === true);
  const embeddingCandidates = models.filter((m) => m.model_type === "embedding");

  return (
    <div className="max-w-2xl">
      <h1 className="mb-1 text-xl font-semibold">Retrieval & Vision fallback</h1>
      <p className="mb-6 text-sm text-[var(--muted)]">
        Retrieval (RAG) and vision degradation are configured here, separate from the primary chat LLM.
      </p>

      <section className="mb-6 rounded-xl border border-[var(--border)] p-4">
        <h2 className="mb-3 text-sm font-semibold">Vision fallback chain</h2>
        <label className="mb-1 block text-xs text-[var(--muted)]">
          Model used to describe images when the primary model has no vision
        </label>
        <select value={visionModelId} onChange={(e) => setVisionModelId(e.target.value)} className={selectCls}>
          <option value="">None — image input disabled for non-vision models</option>
          {visionCandidates.map((m) => (
            <option key={m.id} value={m.id}>{m.display_name}</option>
          ))}
        </select>
        {visionCandidates.length === 0 && (
          <p className="mt-2 text-xs text-amber-600">
            No model with image_input capability. Enable image_input on a model first.
          </p>
        )}
      </section>

      <section className="mb-6 rounded-xl border border-[var(--border)] p-4">
        <h2 className="mb-3 text-sm font-semibold">Retrieval (RAG)</h2>
        <label className="mb-1 block text-xs text-[var(--muted)]">Embedding model</label>
        <select value={embeddingModelId} onChange={(e) => setEmbeddingModelId(e.target.value)} className={selectCls}>
          <option value="">None — files stored without semantic search</option>
          {embeddingCandidates.map((m) => (
            <option key={m.id} value={m.id}>{m.display_name} ({m.provider_name})</option>
          ))}
        </select>
        {embeddingCandidates.length === 0 && (
          <p className="mt-2 text-xs text-amber-600">
            No model of type "embedding" registered. Add one in Models with Model type = embedding.
          </p>
        )}
        <div className="mt-4 grid grid-cols-2 gap-3">
          <Field label="Chunk size (chars)">
            <input type="number" value={chunkSize} onChange={(e) => setChunkSize(Number(e.target.value))} className={inputCls} />
          </Field>
          <Field label="Chunk overlap (chars)">
            <input type="number" value={chunkOverlap} onChange={(e) => setChunkOverlap(Number(e.target.value))} className={inputCls} />
          </Field>
          <Field label="Top K passages">
            <input type="number" value={topK} onChange={(e) => setTopK(Number(e.target.value))} className={inputCls} />
          </Field>
          <Field label="Score threshold (cosine)">
            <input type="number" step="0.05" value={threshold} onChange={(e) => setThreshold(Number(e.target.value))} className={inputCls} />
          </Field>
        </div>
      </section>

      {error && <div className="mb-3 text-sm text-red-500">{error}</div>}
      <Button variant="primary" onClick={save}>{saved ? "Saved" : "Save settings"}</Button>
    </div>
  );
}

const selectCls =
  "w-full rounded-lg border border-[var(--border)] bg-transparent px-3 py-2 text-sm outline-none focus:border-accent";
const inputCls = selectCls;

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-[var(--muted)]">{label}</span>
      {children}
    </label>
  );
}
