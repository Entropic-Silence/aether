"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ArrowLeft, BarChart3, Boxes, Cpu, FileText, Globe, Image, LayoutDashboard, Mic2, Palette, Plug, Puzzle, ScrollText, SearchCheck, ShieldCheck, SlidersHorizontal, Sparkles, Users } from "lucide-react";
import { api, getToken } from "@/lib/api";
import { useApp } from "@/lib/hooks";
import { Spinner } from "@/components/ui";
import { cn } from "@/components/ui";

const NAV = [
  { href: "/admin", label: "Overview", zh: "概览", icon: LayoutDashboard, group: "product" },
  { href: "/admin/features", label: "Features & access", zh: "功能与权限", icon: SlidersHorizontal, group: "product" },
  { href: "/admin/appearance", label: "Appearance", zh: "外观与品牌", icon: Palette, group: "product" },
  { href: "/admin/providers", label: "Providers", zh: "服务商", icon: Plug, group: "models" },
  { href: "/admin/models", label: "Models", zh: "对话模型", icon: Boxes, group: "models" },
  { href: "/admin/images", label: "Image Models", zh: "图片模型", icon: Image, group: "models" },
  { href: "/admin/audio", label: "Voice", zh: "语音服务", icon: Mic2, group: "models" },
  { href: "/admin/retrieval", label: "Retrieval", zh: "检索与视觉", icon: SearchCheck, group: "tools" },
  { href: "/admin/search", label: "Search", zh: "搜索服务", icon: Globe, group: "tools" },
  { href: "/admin/sandbox", label: "Sandbox", zh: "沙箱", icon: ShieldCheck, group: "tools" },
  { href: "/admin/mcp", label: "MCP", zh: "MCP 服务", icon: Plug, group: "tools" },
  { href: "/admin/skills", label: "Skills", zh: "技能", icon: Sparkles, group: "tools" },
  { href: "/admin/plugins", label: "Plugins", zh: "插件", icon: Puzzle, group: "tools" },
  { href: "/admin/prompts", label: "Prompts", zh: "系统提示词", icon: FileText, group: "tools" },
  { href: "/admin/usage", label: "Usage", zh: "用量", icon: BarChart3, group: "operations" },
  { href: "/admin/logs", label: "Logs", zh: "日志", icon: ScrollText, group: "operations" },
  { href: "/admin/workspaces", label: "Workspaces", zh: "工作区", icon: Users, group: "operations" },
  { href: "/admin/system", label: "System", zh: "系统", icon: Cpu, group: "operations" },
];

const GROUP_LABELS: Record<string, { label: string; zh: string }> = {
  product: { label: "Product", zh: "产品" }, models: { label: "Models & media", zh: "模型与媒体" },
  tools: { label: "Tools & knowledge", zh: "工具与知识" }, operations: { label: "Operations", zh: "运营与系统" },
};

function AdminLayoutInner({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, branding, locale } = useApp();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      window.location.href = "/login";
      return;
    }
    api
      .me()
      .then((u) => {
        if (!["owner", "admin", "moderator"].includes(u.role)) {
          window.location.href = "/";
          return;
        }
        setReady(true);
      })
      .catch(() => {
        window.location.href = "/login";
      });
  }, []);

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner className="h-6 w-6 text-[var(--muted)]" />
      </div>
    );
  }

  return (
    <div className="flex min-h-screen bg-[var(--bg)]">
      <aside className="sticky top-0 flex h-screen w-64 shrink-0 flex-col border-r border-[var(--border)] bg-[var(--sidebar)]">
        <div className="flex items-center justify-between border-b border-[var(--border)] px-4 py-4">
          <div>
            <div className="text-sm font-semibold tracking-tight">{branding?.product_name ?? "Aether"} {locale === "zh-CN" ? "管理后台" : "Admin"}</div>
            <div className="text-xs text-[var(--muted)]">{user?.email}</div>
          </div>
        </div>
        <nav className="flex-1 overflow-y-auto px-2 py-3">
          {NAV.map((item, index) => {
            const active = item.href === "/admin" ? pathname === "/admin" : pathname.startsWith(item.href);
            const previous = NAV[index - 1];
            return (
              <div key={item.href}>
                {(!previous || previous.group !== item.group) && <div className={cn("px-3 pb-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--muted)]", index > 0 && "mt-4")}>{locale === "zh-CN" ? GROUP_LABELS[item.group].zh : GROUP_LABELS[item.group].label}</div>}
                <Link href={item.href} className={cn("mb-0.5 flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm", active ? "bg-[var(--fg)] font-medium text-[var(--bg)]" : "text-[var(--muted)] hover:bg-black/5 hover:text-[var(--fg)] dark:hover:bg-white/10")}><item.icon size={16} />{locale === "zh-CN" ? item.zh : item.label}</Link>
              </div>
            );
          })}
        </nav>
        <div className="border-t border-[var(--border)] px-4 py-4">
          <button type="button" onClick={() => router.push("/")} className="flex items-center gap-1.5 text-sm text-[var(--muted)] hover:text-[var(--fg)]">
            <ArrowLeft size={15} /> {locale === "zh-CN" ? "返回应用" : "Back to app"}
          </button>
        </div>
      </aside>
      <main className="min-w-0 flex-1 overflow-y-auto px-5 py-7 md:px-8 lg:px-10">{children}</main>
    </div>
  );
}

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return <AdminLayoutInner>{children}</AdminLayoutInner>;
}
