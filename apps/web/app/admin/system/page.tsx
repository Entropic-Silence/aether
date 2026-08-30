"use client";

import { useCallback, useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { api } from "@/lib/api";
import type { ComputeInfo } from "@/lib/types";
import { Button, Spinner } from "@/components/ui";

const KIND_LABEL: Record<string, string> = {
  hygon_dcu: "Hygon DCU",
  cuda: "NVIDIA CUDA",
  rocm: "AMD ROCm",
  cpu: "CPU only",
  none: "None detected",
};

export default function SystemPage() {
  const [info, setInfo] = useState<ComputeInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ts, setTs] = useState<Date | null>(null);

  const load = useCallback(() => {
    api
      .compute()
      .then((data) => {
        setInfo(data);
        setTs(new Date());
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"));
  }, []);

  useEffect(load, [load]);

  if (error) return <div className="text-sm text-red-500">{error}</div>;
  if (!info) return <Spinner className="h-6 w-6 text-[var(--muted)]" />;

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">System · Compute resources</h1>
          <p className="text-sm text-[var(--muted)]">
            Detected through the AcceleratorAdapter — never assumes NVIDIA. DCU is identified via
            /dev/kfd + hy-smi + DTK even when PyTorch exposes it as a CUDA device.
          </p>
        </div>
        <Button onClick={load}><RefreshCw size={14} /> Refresh</Button>
      </div>

      <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Stat label="Accelerator" value={KIND_LABEL[info.kind] ?? info.kind} />
        <Stat label="Devices" value={info.device_count} />
        <Stat label="DTK version" value={info.dtk_version || "—"} />
        <Stat label="HIP version" value={info.hip_version || "—"} />
        <Stat label="PyTorch" value={info.torch_version || "—"} />
        <Stat label="Runtime backend" value={info.backend} />
        <Stat label="Driver" value={info.driver || "—"} />
        <Stat label="Checked" value={ts ? ts.toLocaleTimeString() : "—"} />
      </div>

      <h2 className="mb-2 text-sm font-semibold">Devices</h2>
      <div className="space-y-3">
        {info.devices.map((d) => {
          const usedPct = d.memory_total_mb ? Math.round((d.memory_used_mb / d.memory_total_mb) * 100) : 0;
          return (
            <div key={d.index} className="rounded-xl border border-[var(--border)] p-4">
              <div className="mb-2 flex items-center justify-between">
                <div className="font-medium">
                  Device {d.index} · {d.name || "unknown"}
                </div>
                {typeof d.temperature_c === "number" && (
                  <span className="text-xs text-[var(--muted)]">
                    {d.temperature_c}°C · {d.power_w}W / {d.power_cap_w}W
                  </span>
                )}
              </div>
              <div className="mb-1 flex justify-between text-xs text-[var(--muted)]">
                <span>
                  Memory {fmtMb(d.memory_used_mb)} / {fmtMb(d.memory_total_mb)}
                </span>
                <span>{usedPct}% used</span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-[var(--surface)]">
                <div className="h-full rounded-full bg-accent" style={{ width: `${usedPct}%` }} />
              </div>
              {typeof d.utilization_pct === "number" && (
                <div className="mt-2 text-xs text-[var(--muted)]">Utilization {d.utilization_pct}%</div>
              )}
            </div>
          );
        })}
        {info.devices.length === 0 && (
          <div className="rounded-xl border border-dashed border-[var(--border)] p-6 text-center text-sm text-[var(--muted)]">
            No accelerator devices detected. CPU fallback is used for local workloads.
          </div>
        )}
      </div>
    </div>
  );
}

function fmtMb(mb: number): string {
  return mb >= 1024 ? `${(mb / 1024).toFixed(1)} GiB` : `${mb} MiB`;
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-[var(--border)] p-3">
      <div className="text-xs text-[var(--muted)]">{label}</div>
      <div className="mt-0.5 truncate text-lg font-semibold">{value}</div>
    </div>
  );
}
