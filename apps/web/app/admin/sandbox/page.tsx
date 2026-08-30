"use client";

import { useCallback, useEffect, useState } from "react";
import { FlaskConical, ShieldAlert } from "lucide-react";
import { api } from "@/lib/api";
import { Button, Spinner } from "@/components/ui";

interface SandboxInfo {
  capabilities: {
    provider: string;
    user_isolation: boolean;
    network_isolated: boolean;
    filesystem_pivot: boolean;
    rlimits: boolean;
    wall_timeout: boolean;
    note: string;
  };
  default_timeout_s: number;
}

export default function SandboxAdminPage() {
  const [info, setInfo] = useState<SandboxInfo | null>(null);
  const [testResult, setTestResult] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    fetch("/api/v1/system/sandbox", {
      headers: { Authorization: `Bearer ${localStorage.getItem("aether_token")}` },
    })
      .then((r) => r.json())
      .then(setInfo)
      .catch(() => setInfo(null));
  }, []);

  useEffect(load, [load]);

  const runTest = async () => {
    setBusy(true);
    setTestResult(null);
    try {
      const res = await fetch("/api/v1/system/sandbox/test", {
        method: "POST",
        headers: { Authorization: `Bearer ${localStorage.getItem("aether_token")}` },
      });
      setTestResult(await res.json());
    } finally {
      setBusy(false);
    }
  };

  if (!info) return <Spinner className="h-6 w-6 text-[var(--muted)]" />;

  const caps = info.capabilities;
  const rows: [string, boolean, string][] = [
    ["Unprivileged user isolation", caps.user_isolation, "code runs as nobody, never root"],
    ["Network isolation", caps.network_isolated, "sandbox cannot reach the network"],
    ["Filesystem pivot", caps.filesystem_pivot, "sandbox sees a private filesystem view"],
    ["Resource limits (CPU/RAM/files/procs)", caps.rlimits, "rlimits enforced per execution"],
    ["Wall-time kill", caps.wall_timeout, "process group killed on timeout"],
  ];

  return (
    <div className="max-w-2xl">
      <h1 className="mb-1 text-xl font-semibold">Sandbox</h1>
      <p className="mb-6 text-sm text-[var(--muted)]">
        Active provider: <span className="font-mono">{caps.provider}</span> · default timeout{" "}
        {info.default_timeout_s}s. Capabilities are detected, not assumed.
      </p>

      {!caps.network_isolated && (
        <div className="mb-4 flex items-start gap-2 rounded-xl border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-600">
          <ShieldAlert size={16} className="mt-0.5 shrink-0" />
          <span>{caps.note}</span>
        </div>
      )}

      <div className="mb-6 overflow-hidden rounded-xl border border-[var(--border)]">
        {rows.map(([label, ok, desc]) => (
          <div key={label} className="flex items-center justify-between border-b border-[var(--border)] px-4 py-2.5 last:border-b-0">
            <div>
              <div className="text-sm font-medium">{label}</div>
              <div className="text-xs text-[var(--muted)]">{desc}</div>
            </div>
            <span className={ok ? "text-accent" : "text-red-500"}>{ok ? "enabled" : "not available"}</span>
          </div>
        ))}
      </div>

      <div className="flex items-center gap-3">
        <Button variant="primary" onClick={runTest} disabled={busy}>
          {busy ? <Spinner /> : <FlaskConical size={15} />} Run sandbox test
        </Button>
        <span className="text-xs text-[var(--muted)]">executes print(6*7) inside the sandbox</span>
      </div>
      {testResult && (
        <pre className="mt-3 rounded-xl bg-[var(--surface)] p-3 text-xs">
          {JSON.stringify(testResult, null, 2)}
        </pre>
      )}
    </div>
  );
}
