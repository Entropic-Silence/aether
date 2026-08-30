"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { useRouter } from "next/navigation";
import { PanelLeft, Plus } from "lucide-react";
import { AppProvider, useApp } from "@/lib/hooks";
import { ConversationsProvider, useConversations } from "@/lib/chat-context";
import { Sidebar } from "./Sidebar";

function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { branding, user, authReady } = useApp();
  const { conversations, refresh, activeId, runningIds } = useConversations();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  const bare = pathname.startsWith("/login") || pathname.startsWith("/admin");

  useEffect(() => {
    setMobileOpen(false);
  }, [pathname, activeId]);

  useEffect(() => {
    if (authReady && !bare && !user) router.replace("/login");
  }, [authReady, bare, user, router]);

  if (bare) {
    return <div className="min-h-screen">{children}</div>;
  }

  if (!authReady || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center" aria-label="Loading">
        <div className="h-5 w-5 animate-spin rounded-full border-2 border-[var(--border)] border-t-[rgb(var(--accent))]" />
      </div>
    );
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar
        conversations={conversations}
        onRefresh={refresh}
        collapsed={collapsed}
        onToggle={() => setCollapsed(!collapsed)}
        mobileOpen={mobileOpen}
        onCloseMobile={() => setMobileOpen(false)}
        activeId={activeId}
        runningIds={runningIds}
      />
      <div className="relative flex min-w-0 flex-1 flex-col">
        <div className="absolute left-2 top-2 z-20 flex gap-1 md:hidden">
          <button
            type="button"
            onClick={() => setMobileOpen(true)}
            className="flex h-9 w-9 items-center justify-center rounded-lg text-[var(--muted)] hover:bg-[var(--surface)]"
          >
            <PanelLeft size={18} />
          </button>
          <button
            type="button"
            onClick={() => {
              window.history.pushState(null, "", "/");
              window.dispatchEvent(new CustomEvent("aether:new-chat"));
            }}
            className="flex h-9 w-9 items-center justify-center rounded-lg text-[var(--muted)] hover:bg-[var(--surface)]"
          >
            <Plus size={18} />
          </button>
        </div>
        <main className="flex min-h-0 flex-1 flex-col">{children}</main>
      </div>
      {branding?.tagline ? null : null}
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <AppProvider>
      <ConversationsProvider>
        <Shell>{children}</Shell>
      </ConversationsProvider>
    </AppProvider>
  );
}
