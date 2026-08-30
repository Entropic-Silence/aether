"use client";

import { useEffect, useState } from "react";
import { phase8Api } from "@/lib/api";
import { Spinner } from "@/components/ui";

export default function LogsAdminPage() {
  const [logs, setLogs] = useState<Record<string, unknown>[] | null>(null);

  useEffect(() => {
    phase8Api.logs(200).then(setLogs).catch(() => setLogs([]));
  }, []);

  if (!logs) return <Spinner className="h-6 w-6 text-[var(--muted)]" />;

  return (
    <div className="max-w-4xl">
      <h1 className="mb-1 text-xl font-semibold">Request logs</h1>
      <p className="mb-4 text-sm text-[var(--muted)]">Recent API requests with latency and status.</p>
      {logs.length === 0 ? (
        <div className="rounded-xl border border-dashed border-[var(--border)] p-8 text-center text-sm text-[var(--muted)]">
          No logs yet.
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-[var(--border)]">
          <table className="w-full text-xs">
            <thead className="bg-[var(--surface)] text-left text-[var(--muted)]">
              <tr>
                <th className="px-3 py-2">Time</th>
                <th className="px-3 py-2">Method</th>
                <th className="px-3 py-2">Path</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Latency</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((l) => (
                <tr key={l.id as string} className="border-t border-[var(--border)]">
                  <td className="px-3 py-1.5 whitespace-nowrap">{new Date(l.created_at as string).toLocaleTimeString()}</td>
                  <td className="px-3 py-1.5">{l.method as string}</td>
                  <td className="px-3 py-1.5 truncate max-w-[280px]">{l.path as string}</td>
                  <td className="px-3 py-1.5">
                    <span className={(l.status as number) >= 500 ? "text-red-500" : (l.status as number) >= 400 ? "text-amber-500" : "text-accent"}>
                      {l.status as number}
                    </span>
                  </td>
                  <td className="px-3 py-1.5">{l.latency_ms as number}ms</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
