"use client";

import { useEffect, useState } from "react";
import { phase8Api } from "@/lib/api";
import { Spinner } from "@/components/ui";

export default function UsageAdminPage() {
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [days, setDays] = useState(1);

  useEffect(() => {
    phase8Api.usageDashboard(days).then(setData).catch(() => setData({}));
  }, [days]);

  if (!data) return <Spinner className="h-6 w-6 text-[var(--muted)]" />;

  const byModel = (data.by_model ?? {}) as Record<string, { requests: number; input_tokens: number; output_tokens: number }>;

  return (
    <div className="max-w-3xl">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold">Usage dashboard</h1>
        <select value={days} onChange={(e) => setDays(Number(e.target.value))}
          className="rounded-lg border border-[var(--border)] bg-transparent px-3 py-1.5 text-sm">
          <option value={1}>Today</option>
          <option value={7}>7 days</option>
          <option value={30}>30 days</option>
        </select>
      </div>

      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Requests" value={data.requests as number} />
        <Stat label="Active users" value={data.active_users as number} />
        <Stat label="Input tokens" value={data.input_tokens as number} />
        <Stat label="Output tokens" value={data.output_tokens as number} />
      </div>

      <h2 className="mb-2 text-sm font-semibold">By model</h2>
      {Object.keys(byModel).length === 0 ? (
        <div className="rounded-xl border border-dashed border-[var(--border)] p-8 text-center text-sm text-[var(--muted)]">
          No usage recorded in this window.
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-[var(--border)]">
          <table className="w-full text-sm">
            <thead className="bg-[var(--surface)] text-left text-xs text-[var(--muted)]">
              <tr>
                <th className="px-4 py-2">Model</th>
                <th className="px-4 py-2">Requests</th>
                <th className="px-4 py-2">Input tokens</th>
                <th className="px-4 py-2">Output tokens</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(byModel).map(([name, v]) => (
                <tr key={name} className="border-t border-[var(--border)]">
                  <td className="px-4 py-2">{name}</td>
                  <td className="px-4 py-2">{v.requests}</td>
                  <td className="px-4 py-2">{v.input_tokens}</td>
                  <td className="px-4 py-2">{v.output_tokens}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border border-[var(--border)] p-4">
      <div className="text-xs text-[var(--muted)]">{label}</div>
      <div className="mt-1 text-2xl font-semibold">{value ?? 0}</div>
    </div>
  );
}
