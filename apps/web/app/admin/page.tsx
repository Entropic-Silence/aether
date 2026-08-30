"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowUpRight, Boxes, Cpu, Image, Plug, SlidersHorizontal } from "lucide-react";
import { api } from "@/lib/api";
import type { ComputeInfo, FeatureControls, ModelInfo, Provider } from "@/lib/types";
import { useApp } from "@/lib/hooks";
import { Spinner } from "@/components/ui";

export default function AdminOverview() {
  const { locale } = useApp();
  const zh = locale === "zh-CN";
  const [providers, setProviders] = useState<Provider[] | null>(null);
  const [models, setModels] = useState<ModelInfo[] | null>(null);
  const [compute, setCompute] = useState<ComputeInfo | null>(null);
  const [controls, setControls] = useState<FeatureControls | null>(null);

  useEffect(() => {
    Promise.all([api.listProviders(), api.listModels(), api.compute(), api.featureControls()])
      .then(([p, m, c, f]) => { setProviders(p); setModels(m); setCompute(c); setControls(f); })
      .catch(() => { setProviders([]); setModels([]); });
  }, []);

  if (!providers || !models) return <Spinner className="h-6 w-6 text-[var(--muted)]" />;
  const enabledModels = models.filter((m) => m.enabled);
  const enabledProviders = providers.filter((p) => p.enabled);
  const featureCount = controls ? Object.values(controls.features).filter(Boolean).length : 0;

  return <div className="mx-auto max-w-6xl">
    <div className="mb-8"><div className="text-xs font-medium uppercase tracking-[0.16em] text-[var(--muted)]">{zh ? "控制中心" : "Control center"}</div><h1 className="mt-2 text-3xl font-semibold tracking-tight">{zh ? "系统概览" : "System overview"}</h1><p className="mt-2 max-w-2xl text-sm text-[var(--muted)]">{zh ? "从这里查看产品能力、模型连接和海光计算环境的整体状态。" : "Monitor product capabilities, model connectivity and the Hygon compute environment."}</p></div>

    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <Metric icon={<SlidersHorizontal size={18} />} label={zh ? "已开放功能" : "Enabled features"} value={`${featureCount} / ${controls ? Object.keys(controls.features).length : "—"}`} href="/admin/features" />
      <Metric icon={<Plug size={18} />} label={zh ? "服务商" : "Providers"} value={`${enabledProviders.length} / ${providers.length}`} href="/admin/providers" />
      <Metric icon={<Boxes size={18} />} label={zh ? "对话模型" : "Chat models"} value={`${enabledModels.length} / ${models.length}`} href="/admin/models" />
      <Metric icon={<Cpu size={18} />} label={zh ? "计算设备" : "Accelerator"} value={compute?.kind ?? "unknown"} sub={compute?.device_count ? `${compute.device_count} × ${compute.devices?.[0]?.name ?? "device"}` : (zh ? "未检测到设备" : "No device detected")} href="/admin/system" />
    </div>

    <div className="mt-8 grid gap-5 lg:grid-cols-[minmax(0,1.35fr)_minmax(280px,.65fr)]">
      <section className="overflow-hidden rounded-2xl border border-[var(--border)]"><div className="flex items-center justify-between border-b border-[var(--border)] px-5 py-4"><div><h2 className="text-sm font-semibold">{zh ? "模型运行状态" : "Model status"}</h2><p className="mt-0.5 text-xs text-[var(--muted)]">{zh ? "能力由探测结果和管理员覆盖共同决定。" : "Capabilities combine probe results with admin overrides."}</p></div><Link href="/admin/models" className="text-xs text-[var(--muted)] hover:text-[var(--fg)]">{zh ? "管理" : "Manage"}</Link></div><div className="divide-y divide-[var(--border)]">{models.slice(0, 8).map((model) => <div key={model.id} className="flex items-center gap-3 px-5 py-3.5"><span className={`h-2 w-2 rounded-full ${model.enabled ? "bg-emerald-500" : "bg-[var(--border)]"}`} /><div className="min-w-0 flex-1"><div className="truncate text-sm font-medium">{model.display_name}</div><div className="truncate text-xs text-[var(--muted)]">{model.provider_name} · {model.model_id}</div></div><span className="rounded-full bg-[var(--surface)] px-2.5 py-1 text-[10px] text-[var(--muted)]">{model.probe_status || "manual"}</span></div>)}{models.length === 0 && <div className="px-5 py-10 text-center text-sm text-[var(--muted)]">{zh ? "尚未配置模型" : "No models configured"}</div>}</div></section>
      <section className="rounded-2xl border border-[var(--border)] p-5"><h2 className="text-sm font-semibold">{zh ? "常用配置" : "Quick configuration"}</h2><div className="mt-4 space-y-2"><Quick href="/admin/features" icon={<SlidersHorizontal size={16} />} label={zh ? "功能与权限" : "Features & access"} /><Quick href="/admin/appearance" icon={<Image size={16} />} label={zh ? "外观与品牌" : "Appearance & branding"} /><Quick href="/admin/search" icon={<Plug size={16} />} label={zh ? "搜索服务" : "Search providers"} /><Quick href="/admin/plugins" icon={<Boxes size={16} />} label={zh ? "插件与工具" : "Plugins & tools"} /></div><div className="mt-6 rounded-xl bg-[var(--surface)] p-4 text-xs leading-5 text-[var(--muted)]">{zh ? "管理员配置会直接决定用户端入口、服务器权限和模型可用能力。敏感密钥始终以掩码返回。" : "Admin settings directly govern user entry points, server permissions and model capabilities. Stored secrets are always masked."}</div></section>
    </div>
  </div>;
}

function Metric({ icon, label, value, sub, href }: { icon: React.ReactNode; label: string; value: React.ReactNode; sub?: string; href: string }) { return <Link href={href} className="group rounded-2xl border border-[var(--border)] p-5 hover:bg-[var(--surface)]/55"><div className="flex items-center justify-between text-[var(--muted)]"><span className="flex h-9 w-9 items-center justify-center rounded-xl bg-[var(--surface)]">{icon}</span><ArrowUpRight size={15} className="opacity-0 transition-opacity group-hover:opacity-100" /></div><div className="mt-5 text-2xl font-semibold tracking-tight">{value}</div><div className="mt-1 text-xs text-[var(--muted)]">{label}</div>{sub && <div className="mt-1 truncate text-[10px] text-[var(--muted)]">{sub}</div>}</Link>; }
function Quick({ href, icon, label }: { href: string; icon: React.ReactNode; label: string }) { return <Link href={href} className="flex items-center gap-3 rounded-xl border border-transparent px-3 py-2.5 text-sm hover:border-[var(--border)] hover:bg-[var(--surface)]"><span className="text-[var(--muted)]">{icon}</span><span className="flex-1">{label}</span><ArrowUpRight size={14} className="text-[var(--muted)]" /></Link>; }
