"use client";

import { useEffect, useRef, useState } from "react";
import { Check, PackagePlus, Puzzle, Upload } from "lucide-react";
import type { PluginInfo } from "@/lib/types";
import { phase6Api } from "@/lib/api";
import { Button, Spinner } from "@/components/ui";

export default function PluginsPage() {
  const [plugins, setPlugins] = useState<PluginInfo[] | null>(null);
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const load = () => phase6Api.listPlugins().then((data) => setPlugins(data.plugins)).catch((e) => setMessage(e instanceof Error ? e.message : "加载失败"));
  useEffect(() => { void load(); }, []);
  const toggle = async (plugin: PluginInfo) => {
    setBusy(plugin.plugin_id);
    try { await phase6Api.setPluginEnabled(plugin.plugin_id, !plugin.enabled); await load(); }
    catch (e) { setMessage(e instanceof Error ? e.message : "操作失败"); }
    finally { setBusy(""); }
  };
  const importFile = async (file?: File) => {
    if (!file) return;
    setBusy("import"); setMessage("");
    try { await phase6Api.importPlugin(file); setMessage("插件清单已导入并启用"); await load(); }
    catch (e) { setMessage(e instanceof Error ? e.message : "导入失败"); }
    finally { setBusy(""); }
  };
  return (
    <main className="mx-auto w-full max-w-4xl px-5 py-8">
      <div className="mb-6 flex items-center justify-between gap-4">
        <div><h1 className="flex items-center gap-2 text-xl font-semibold"><Puzzle size={20} />插件</h1><p className="mt-1 text-sm text-[var(--muted)]">启用管理员提供的插件，或导入 DeepSeek Harness / Cordis 的 package.json。</p></div>
        <><input ref={input} type="file" accept="application/json,.json" className="hidden" onChange={(e) => { void importFile(e.target.files?.[0]); e.target.value = ""; }} /><Button onClick={() => input.current?.click()} disabled={busy === "import"}>{busy === "import" ? <Spinner /> : <Upload size={15} />}导入插件</Button></>
      </div>
      {message && <div className="mb-4 rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-3 text-sm">{message}</div>}
      {plugins === null ? <div className="flex justify-center py-16"><Spinner /></div> : plugins.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-[var(--border)] p-10 text-center text-[var(--muted)]"><PackagePlus className="mx-auto mb-3" />管理员尚未配置插件。</div>
      ) : <div className="grid gap-3">{plugins.map((plugin) => (
        <button key={plugin.plugin_id} type="button" disabled={plugin.status !== "valid" || busy === plugin.plugin_id} onClick={() => void toggle(plugin)} className="flex items-center gap-4 rounded-2xl border border-[var(--border)] p-4 text-left hover:bg-[var(--surface)] disabled:opacity-50">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--surface)]"><Puzzle size={19} /></span>
          <span className="min-w-0 flex-1"><span className="block font-medium">{plugin.name}</span><span className="block truncate text-xs text-[var(--muted)]">{plugin.description || `${plugin.format} · ${plugin.capabilities.join(", ") || "manifest"}`}</span></span>
          <span className={`flex h-6 w-6 items-center justify-center rounded-full border ${plugin.enabled ? "border-[var(--fg)] bg-[var(--fg)] text-[var(--bg)]" : "border-[var(--border)]"}`}>{plugin.enabled && <Check size={14} />}</span>
        </button>
      ))}</div>}
    </main>
  );
}
