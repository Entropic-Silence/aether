"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Clock, Play, Plus, Trash2, X } from "lucide-react";
import { phase7Api } from "@/lib/api";
import type { TaskInfo, TaskRunInfo } from "@/lib/types";
import { getToken } from "@/lib/api";
import { Button, IconBtn, Spinner } from "@/components/ui";

const inputCls =
  "w-full rounded-lg border border-[var(--border)] bg-transparent px-3 py-2 text-sm outline-none focus:border-accent";

const EMPTY = { name: "", prompt: "", schedule_type: "one_time", schedule_value: "", timezone: "UTC" };

export default function TasksPage() {
  const [tasks, setTasks] = useState<TaskInfo[] | null>(null);
  const [form, setForm] = useState<typeof EMPTY | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [runsFor, setRunsFor] = useState<string | null>(null);
  const [runs, setRuns] = useState<TaskRunInfo[] | null>(null);

  const load = useCallback(() => {
    phase7Api.listTasks().then(setTasks).catch(() => setTasks([]));
  }, []);
  useEffect(() => {
    if (!getToken()) {
      window.location.href = "/login";
      return;
    }
    load();
  }, [load]);

  const save = async () => {
    if (!form) return;
    setBusy(true);
    setError(null);
    try {
      await phase7Api.createTask(form);
      setForm(null);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setBusy(false);
    }
  };

  const showRuns = async (id: string) => {
    setRunsFor(id);
    setRuns(null);
    setRuns(await phase7Api.taskRuns(id));
  };

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-8">
      <Link href="/" className="mb-6 inline-flex items-center gap-1.5 text-sm text-[var(--muted)] hover:text-[var(--fg)]">
        <ArrowLeft size={15} /> Back to chat
      </Link>
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Scheduled tasks</h1>
          <p className="text-sm text-[var(--muted)]">Run a prompt on a schedule; results are saved as conversations.</p>
        </div>
        <Button variant="primary" onClick={() => setForm({ ...EMPTY })}>
          <Plus size={15} /> New task
        </Button>
      </div>

      {form && (
        <div className="mb-6 rounded-xl border border-[var(--border)] p-4">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold">New task</h2>
            <IconBtn onClick={() => setForm(null)}><X size={16} /></IconBtn>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <label className="block"><span className="mb-1 block text-xs text-[var(--muted)]">Name</span>
              <input className={inputCls} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
            <label className="block"><span className="mb-1 block text-xs text-[var(--muted)]">Schedule type</span>
              <select className={inputCls} value={form.schedule_type} onChange={(e) => setForm({ ...form, schedule_type: e.target.value })}>
                <option value="one_time">One-time (ISO datetime)</option>
                <option value="interval">Interval (seconds)</option>
                <option value="cron">Cron expression</option>
              </select></label>
            <label className="block sm:col-span-2"><span className="mb-1 block text-xs text-[var(--muted)]">Schedule value</span>
              <input className={inputCls} value={form.schedule_value}
                placeholder={form.schedule_type === "cron" ? "0 8 * * *" : form.schedule_type === "interval" ? "3600" : "2026-09-01T08:00:00+00:00"}
                onChange={(e) => setForm({ ...form, schedule_value: e.target.value })} /></label>
            <label className="block sm:col-span-2"><span className="mb-1 block text-xs text-[var(--muted)]">Prompt</span>
              <textarea rows={3} className={inputCls} value={form.prompt} onChange={(e) => setForm({ ...form, prompt: e.target.value })} /></label>
          </div>
          {error && <div className="mt-3 text-sm text-red-500">{error}</div>}
          <div className="mt-3 flex gap-2">
            <Button variant="primary" onClick={save} disabled={busy || !form.prompt || !form.schedule_value}>{busy ? <Spinner /> : "Create"}</Button>
            <Button onClick={() => setForm(null)}>Cancel</Button>
          </div>
        </div>
      )}

      {!tasks ? (
        <Spinner className="h-6 w-6 text-[var(--muted)]" />
      ) : tasks.length === 0 ? (
        <div className="rounded-xl border border-dashed border-[var(--border)] p-10 text-center text-sm text-[var(--muted)]">
          <Clock className="mx-auto mb-2" size={22} />
          No scheduled tasks. Try “Summarize AI news every day at 8:00”.
        </div>
      ) : (
        <div className="space-y-3">
          {tasks.map((t) => (
            <div key={t.id} className="rounded-xl border border-[var(--border)] px-4 py-3">
              <div className="flex items-center justify-between">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{t.name || t.prompt.slice(0, 40)}</span>
                    <span className="rounded bg-[var(--surface)] px-1.5 py-0.5 text-xs text-[var(--muted)]">{t.schedule_type}</span>
                    {!t.enabled && <span className="text-xs text-red-500">disabled</span>}
                  </div>
                  <div className="mt-0.5 truncate text-xs text-[var(--muted)]">{t.prompt}</div>
                  <div className="mt-0.5 text-[10px] text-[var(--muted)]">
                    value: {t.schedule_value} · next: {t.next_run ? new Date(t.next_run).toLocaleString() : "—"}
                    {t.last_run ? ` · last: ${new Date(t.last_run).toLocaleString()}` : ""}
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  <IconBtn title="Run now" onClick={async () => { await phase7Api.runTask(t.id); setTimeout(() => showRuns(t.id), 2000); }}>
                    <Play size={15} />
                  </IconBtn>
                  <IconBtn title="Runs" onClick={() => showRuns(t.id)}><Clock size={15} /></IconBtn>
                  <IconBtn title="Delete" onClick={async () => { await phase7Api.deleteTask(t.id); load(); }}>
                    <Trash2 size={15} />
                  </IconBtn>
                </div>
              </div>
              {runsFor === t.id && runs && (
                <div className="mt-2 space-y-1 border-t border-[var(--border)] pt-2">
                  {runs.length === 0 && <div className="text-xs text-[var(--muted)]">No runs yet.</div>}
                  {runs.map((r) => (
                    <div key={r.id} className="flex items-center justify-between text-xs">
                      <span className={r.status === "completed" ? "text-accent" : r.status === "failed" ? "text-red-500" : "text-[var(--muted)]"}>
                        {r.status}
                      </span>
                      <span className="text-[var(--muted)]">{new Date(r.started_at).toLocaleString()}</span>
                      {r.conversation_id && (
                        <Link href={`/c/${r.conversation_id}`} className="text-accent hover:underline">view</Link>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
