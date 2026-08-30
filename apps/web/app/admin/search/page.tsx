"use client";

import { useCallback, useEffect, useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { Button, IconBtn, Spinner } from "@/components/ui";

interface ProviderRow {
  kind: string;
  priority: number;
  enabled: boolean;
  api_key: string;
  base_url: string;
}

const KINDS = ["mock", "searxng", "tavily", "brave", "serper"] as const;
const NEEDS_KEY = new Set(["tavily", "brave", "serper"]);
const NEEDS_URL = new Set(["searxng"]);

const inputCls =
  "w-full rounded-lg border border-[var(--border)] bg-transparent px-3 py-2 text-sm outline-none focus:border-accent";

export default function SearchAdminPage() {
  const [rows, setRows] = useState<ProviderRow[] | null>(null);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [testOut, setTestOut] = useState<string | null>(null);

  const load = useCallback(() => {
    api.searchSettings().then((d) =>
      setRows(
        (d.providers ?? []).map((p) => ({
          kind: String(p.kind ?? "mock"),
          priority: Number(p.priority ?? 100),
          enabled: p.enabled !== false,
          api_key: String(p.api_key ?? ""),
          base_url: String(p.base_url ?? ""),
        })),
      ),
    );
  }, []);

  useEffect(load, [load]);

  const update = (i: number, patch: Partial<ProviderRow>) =>
    setRows((prev) => (prev ? prev.map((r, j) => (j === i ? { ...r, ...patch } : r)) : prev));

  const save = async () => {
    if (!rows) return;
    setSaved(false);
    setError(null);
    try {
      const res = await api.updateSearchSettings(rows as unknown as Array<Record<string, unknown>>);
      setSaved(res.configured);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    }
  };

  const test = async () => {
    setTestOut("testing…");
    const res = await api.testSearch();
    setTestOut(
      res.ok
        ? `OK via "${res.provider}": ${(res.results ?? []).map((r) => r.title).join(" | ") || "no results"}`
        : `Failed: ${res.error}`,
    );
  };

  if (!rows) return <Spinner className="h-6 w-6 text-[var(--muted)]" />;

  return (
    <div className="max-w-3xl">
      <h1 className="mb-1 text-xl font-semibold">Search providers</h1>
      <p className="mb-6 text-sm text-[var(--muted)]">
        Ordered by priority with automatic fallback. The <span className="font-mono">mock</span> provider returns a
        small offline corpus for development and tests.
      </p>

      <div className="space-y-3">
        {rows.map((r, i) => (
          <div key={i} className="rounded-xl border border-[var(--border)] p-4">
            <div className="mb-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <label className="block">
                <span className="mb-1 block text-xs text-[var(--muted)]">Kind</span>
                <select className={inputCls} value={r.kind} onChange={(e) => update(i, { kind: e.target.value })}>
                  {KINDS.map((k) => (
                    <option key={k} value={k}>{k}</option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className="mb-1 block text-xs text-[var(--muted)]">Priority</span>
                <input type="number" className={inputCls} value={r.priority}
                  onChange={(e) => update(i, { priority: Number(e.target.value) })} />
              </label>
              <label className="col-span-2 flex items-end gap-2 pb-2 text-sm">
                <input type="checkbox" checked={r.enabled} onChange={(e) => update(i, { enabled: e.target.checked })} />
                Enabled
              </label>
            </div>
            {NEEDS_URL.has(r.kind) && (
              <input className={inputCls} placeholder="https://searxng.example.org" value={r.base_url}
                onChange={(e) => update(i, { base_url: e.target.value })} />
            )}
            {NEEDS_KEY.has(r.kind) && (
              <input className={inputCls} type="password" placeholder="API key" value={r.api_key}
                onChange={(e) => update(i, { api_key: e.target.value })} />
            )}
            <div className="mt-2 flex justify-end">
              <IconBtn title="Remove" onClick={() => setRows((prev) => (prev ? prev.filter((_, j) => j !== i) : prev))}>
                <Trash2 size={15} />
              </IconBtn>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button onClick={() => setRows((prev) => [...(prev ?? []), { kind: "mock", priority: (prev?.length ?? 0) * 10 + 100, enabled: true, api_key: "", base_url: "" }])}>
          <Plus size={15} /> Add provider
        </Button>
        <Button variant="primary" onClick={save}>Save</Button>
        <Button onClick={test}>Test search</Button>
        {saved && <span className="text-sm text-accent">Saved — search is configured</span>}
      </div>
      {error && <div className="mt-3 text-sm text-red-500">{error}</div>}
      {testOut && <div className="mt-3 rounded-xl bg-[var(--surface)] p-3 text-xs">{testOut}</div>}
    </div>
  );
}
