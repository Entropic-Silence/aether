"use client";

import { useCallback, useEffect, useState } from "react";
import { Pencil, Plug, Plus, RefreshCw, Trash2, X } from "lucide-react";
import { phase6Api } from "@/lib/api";
import type { McpServerInfo } from "@/lib/types";
import { Button, IconBtn, Spinner } from "@/components/ui";

const inputCls =
  "w-full rounded-lg border border-[var(--border)] bg-transparent px-3 py-2 text-sm outline-none focus:border-accent";

const EMPTY = { name: "", transport: "stdio", command: "", args: "", url: "", enabled: true };

export default function McpAdminPage() {
  const [servers, setServers] = useState<McpServerInfo[] | null>(null);
  const [form, setForm] = useState<typeof EMPTY | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [testOut, setTestOut] = useState<Record<string, string>>({});

  const load = useCallback(() => {
    phase6Api.listMcpServers().then(setServers).catch(() => setServers([]));
  }, []);
  useEffect(load, [load]);

  const buildConfig = (f: typeof EMPTY) =>
    f.transport === "stdio"
      ? { command: f.command, args: f.args.split(/\s+/).filter(Boolean) }
      : { url: f.url };

  const save = async () => {
    if (!form) return;
    setBusy(true);
    setError(null);
    try {
      const payload = { name: form.name, transport: form.transport, enabled: form.enabled, config: buildConfig(form) };
      if (editingId) await phase6Api.updateMcpServer(editingId, payload);
      else await phase6Api.createMcpServer(payload);
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
    setTestOut((t) => ({ ...t, [id]: "testing…" }));
    const res = await phase6Api.testMcpServer(id);
    setTestOut((t) => ({
      ...t,
      [id]: res.ok
        ? `OK · ${res.tool_count} tools: ${(res.tools ?? []).map((x) => x.name).join(", ")}`
        : `Failed: ${res.error}`,
    }));
    load();
  };

  if (!servers) return <Spinner className="h-6 w-6 text-[var(--muted)]" />;

  return (
    <div className="max-w-3xl">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">MCP servers</h1>
          <p className="text-sm text-[var(--muted)]">
            Model Context Protocol tool servers (stdio / HTTP / SSE). Discovered tools join the agent loop
            and require approval before running.
          </p>
        </div>
        <Button variant="primary" onClick={() => { setForm({ ...EMPTY }); setEditingId(null); }}>
          <Plus size={15} /> Add server
        </Button>
      </div>

      {form && (
        <div className="mb-6 rounded-xl border border-[var(--border)] p-4">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold">{editingId ? "Edit MCP server" : "New MCP server"}</h2>
            <IconBtn onClick={() => { setForm(null); setEditingId(null); }}><X size={16} /></IconBtn>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <label className="block">
              <span className="mb-1 block text-xs text-[var(--muted)]">Name</span>
              <input className={inputCls} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs text-[var(--muted)]">Transport</span>
              <select className={inputCls} value={form.transport} onChange={(e) => setForm({ ...form, transport: e.target.value })}>
                <option value="stdio">stdio</option>
                <option value="http">http</option>
                <option value="sse">sse</option>
              </select>
            </label>
            {form.transport === "stdio" ? (
              <>
                <label className="block">
                  <span className="mb-1 block text-xs text-[var(--muted)]">Command</span>
                  <input className={inputCls} value={form.command} placeholder="/usr/bin/python3" onChange={(e) => setForm({ ...form, command: e.target.value })} />
                </label>
                <label className="block">
                  <span className="mb-1 block text-xs text-[var(--muted)]">Arguments (space separated)</span>
                  <input className={inputCls} value={form.args} placeholder="/path/server.py --flag" onChange={(e) => setForm({ ...form, args: e.target.value })} />
                </label>
              </>
            ) : (
              <label className="block sm:col-span-2">
                <span className="mb-1 block text-xs text-[var(--muted)]">URL</span>
                <input className={inputCls} value={form.url} placeholder="https://mcp.example.org" onChange={(e) => setForm({ ...form, url: e.target.value })} />
              </label>
            )}
          </div>
          {error && <div className="mt-3 text-sm text-red-500">{error}</div>}
          <div className="mt-3 flex gap-2">
            <Button variant="primary" onClick={save} disabled={busy || !form.name}>{busy ? <Spinner /> : "Save"}</Button>
            <Button onClick={() => { setForm(null); setEditingId(null); }}>Cancel</Button>
          </div>
        </div>
      )}

      <div className="space-y-3">
        {servers.length === 0 && (
          <div className="rounded-xl border border-dashed border-[var(--border)] p-8 text-center text-sm text-[var(--muted)]">
            <Plug className="mx-auto mb-2" size={22} />
            No MCP servers configured.
          </div>
        )}
        {servers.map((s) => (
          <div key={s.id} className="rounded-xl border border-[var(--border)] px-4 py-3">
            <div className="flex items-center justify-between">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-medium">{s.name}</span>
                  <span className="rounded bg-[var(--surface)] px-1.5 py-0.5 text-xs text-[var(--muted)]">{s.transport}</span>
                  <span className={
                    s.last_status === "connected" ? "text-xs text-accent" : s.last_status === "error" ? "text-xs text-red-500" : "text-xs text-[var(--muted)]"
                  }>
                    {s.last_status}
                  </span>
                </div>
                {s.last_error && <div className="mt-1 truncate text-xs text-red-500">{s.last_error}</div>}
                {testOut[s.id] && <div className="mt-1 text-xs text-[var(--muted)]">{testOut[s.id]}</div>}
              </div>
              <div className="flex shrink-0 items-center gap-1">
                <Button variant="ghost" className="!px-2" onClick={() => test(s.id)}>
                  <RefreshCw size={14} /> Test
                </Button>
                <IconBtn title="Delete" onClick={async () => { await phase6Api.deleteMcpServer(s.id); load(); }}>
                  <Trash2 size={15} />
                </IconBtn>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
