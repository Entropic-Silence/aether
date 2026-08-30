"use client";

import { useEffect, useState } from "react";
import { Palette, RotateCcw, Save } from "lucide-react";
import { api } from "@/lib/api";
import type { Branding } from "@/lib/types";
import { useApp } from "@/lib/hooks";
import { Button, Spinner } from "@/components/ui";

const inputClass = "w-full rounded-xl border border-[var(--border)] bg-transparent px-3.5 py-2.5 text-sm outline-none focus:border-[var(--fg)]";

export default function AppearancePage() {
  const { locale } = useApp();
  const zh = locale === "zh-CN";
  const [form, setForm] = useState<Branding | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => { api.branding().then(setForm).catch(() => setForm(null)); }, []);
  if (!form) return <Spinner className="h-6 w-6 text-[var(--muted)]" />;

  const save = async () => {
    setSaving(true);
    try {
      setForm(await api.updateBranding(form));
      setSaved(true);
      window.setTimeout(() => setSaved(false), 1800);
    } finally { setSaving(false); }
  };

  return (
    <div className="mx-auto max-w-5xl">
      <div className="mb-7 flex flex-wrap items-end justify-between gap-4">
        <div><div className="mb-2 flex items-center gap-2 text-xs font-medium uppercase tracking-[0.16em] text-[var(--muted)]"><Palette size={14} /> {zh ? "界面系统" : "Interface system"}</div><h1 className="text-2xl font-semibold tracking-tight">{zh ? "外观与品牌" : "Appearance & branding"}</h1><p className="mt-1.5 text-sm text-[var(--muted)]">{zh ? "控制登录页、浏览器标题、侧边栏和管理后台使用的统一品牌信息。" : "Control the shared identity used by sign-in, browser title, sidebar and admin console."}</p></div>
        <div className="flex gap-2"><Button onClick={() => setForm({ ...form, accent_color: "#0d0d0d", icon_set: "lucide" })}><RotateCcw size={15} /> {zh ? "恢复黑白" : "Reset monochrome"}</Button><Button variant="primary" onClick={save} disabled={saving}><Save size={15} /> {saved ? (zh ? "已保存" : "Saved") : saving ? (zh ? "保存中" : "Saving") : (zh ? "保存" : "Save")}</Button></div>
      </div>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_340px]">
        <section className="rounded-2xl border border-[var(--border)] p-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={zh ? "产品名称" : "Product name"}><input className={inputClass} value={form.product_name} onChange={(e) => setForm({ ...form, product_name: e.target.value })} /></Field>
            <Field label={zh ? "图标体系" : "Icon set"}><select className={inputClass} value={form.icon_set} onChange={(e) => setForm({ ...form, icon_set: e.target.value })}><option value="lucide">Lucide · {zh ? "简洁线性" : "clean outline"}</option></select></Field>
            <Field label={zh ? "品牌标语" : "Tagline"} wide><input className={inputClass} value={form.tagline} onChange={(e) => setForm({ ...form, tagline: e.target.value })} placeholder={zh ? "可选，用于登录页和品牌信息" : "Optional sign-in and brand message"} /></Field>
            <Field label={zh ? "Logo 地址" : "Logo URL"} wide><input className={inputClass} value={form.logo_url ?? ""} onChange={(e) => setForm({ ...form, logo_url: e.target.value || null })} placeholder="https://…" /></Field>
            <Field label={zh ? "强调色" : "Accent color"}><div className="flex gap-2"><input type="color" className="h-11 w-14 rounded-xl border border-[var(--border)] bg-transparent p-1" value={form.accent_color || "#0d0d0d"} onChange={(e) => setForm({ ...form, accent_color: e.target.value })} /><input className={inputClass} value={form.accent_color} onChange={(e) => setForm({ ...form, accent_color: e.target.value })} /></div></Field>
          </div>
        </section>

        <section className="rounded-2xl border border-[var(--border)] bg-[var(--sidebar)] p-5">
          <div className="mb-4 text-xs font-medium uppercase tracking-[0.14em] text-[var(--muted)]">{zh ? "实时预览" : "Live preview"}</div>
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg)] p-5 shadow-sm">
            <div className="flex items-center gap-3"><span className="flex h-10 w-10 items-center justify-center overflow-hidden rounded-full text-white" style={{ backgroundColor: form.accent_color || "#0d0d0d" }}>{form.logo_url ? <img src={form.logo_url} alt="" className="h-full w-full object-cover" /> : form.product_name.slice(0, 1).toUpperCase()}</span><div><div className="font-semibold">{form.product_name || "Aether"}</div><div className="text-xs text-[var(--muted)]">{form.tagline || (zh ? "智能助手工作空间" : "AI assistant workspace")}</div></div></div>
            <div className="mt-5 rounded-xl px-4 py-3 text-center text-sm text-white" style={{ backgroundColor: form.accent_color || "#0d0d0d" }}>{zh ? "主要操作" : "Primary action"}</div>
          </div>
          <p className="mt-4 text-xs leading-5 text-[var(--muted)]">{zh ? "建议保持黑、白和中性灰，以延续当前 ChatGPT 风格；强调色只用于状态与主要操作。" : "Use black, white and neutral grays to retain the current ChatGPT-like visual language; accent is reserved for status and primary actions."}</p>
        </section>
      </div>
    </div>
  );
}

function Field({ label, children, wide = false }: { label: string; children: React.ReactNode; wide?: boolean }) {
  return <label className={wide ? "sm:col-span-2" : ""}><span className="mb-1.5 block text-xs font-medium text-[var(--muted)]">{label}</span>{children}</label>;
}
