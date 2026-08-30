"use client";

import { useCallback, useEffect, useState } from "react";
import { Puzzle, RefreshCw } from "lucide-react";
import { phase6Api } from "@/lib/api";
import type { PluginInfo } from "@/lib/types";
import { Button, Spinner } from "@/components/ui";

export default function PluginsAdminPage() {
  const [data, setData] = useState<{ plugins_dir: string; plugins: PluginInfo[] } | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    phase6Api.listPlugins().then(setData).catch(() => setData({ plugins_dir: "", plugins: [] }));
  }, []);
  useEffect(load, [load]);

  const rescan = async () => {
    setBusy(true);
    try {
      await phase6Api.rescanPlugins();
      load();
    } finally {
      setBusy(false);
    }
  };

  if (!data) return <Spinner className="h-6 w-6 text-[var(--muted)]" />;

  return (
    <div className="max-w-3xl">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Plugins</h1>
          <p className="text-sm text-[var(--muted)]">
            Aether plugin.yaml and DeepSeek Harness Cordis package.json manifests are discovered from <span className="font-mono">{data.plugins_dir || "plugins/"}</span>.
          </p>
        </div>
        <Button variant="primary" onClick={rescan} disabled={busy}>
          {busy ? <Spinner /> : <RefreshCw size={15} />} Rescan
        </Button>
      </div>

      {data.plugins.length === 0 ? (
        <div className="rounded-xl border border-dashed border-[var(--border)] p-10 text-center text-sm text-[var(--muted)]">
          <Puzzle className="mx-auto mb-2" size={22} />
          No plugins installed. Add an Aether <span className="font-mono">plugin.yaml</span> or a DeepSeek Harness
          <span className="font-mono"> dsh-plugin package.json</span>, then rescan.
        </div>
      ) : (
        <div className="space-y-3">
          {data.plugins.map((p) => (
            <div key={p.plugin_id} className="rounded-xl border border-[var(--border)] px-4 py-3">
              <div className="flex items-center gap-2">
                <span className="font-medium">{p.name}</span>
                <span className="text-xs text-[var(--muted)]">v{p.version}</span>
                <span className={p.status === "valid" ? "text-xs text-accent" : "text-xs text-red-500"}>
                  {p.status}
                </span>
              </div>
              {p.capabilities.length > 0 && (
                <div className="mt-1 flex flex-wrap gap-1">
                  {p.capabilities.map((c) => (
                    <span key={c} className="rounded bg-[var(--surface)] px-1.5 py-0.5 text-[10px] text-[var(--muted)]">{c}</span>
                  ))}
                </div>
              )}
              {p.problems.length > 0 && (
                <ul className="mt-1 list-inside list-disc text-xs text-red-500">
                  {p.problems.map((pr, i) => <li key={i}>{pr}</li>)}
                </ul>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
