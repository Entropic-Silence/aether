"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  BriefcaseBusiness,
  Clock,
  FolderKanban,
  Image as ImageIcon,
  Library as LibraryIcon,
  MessageSquare,
  Loader2,
  PanelLeft,
  Pin,
  Plus,
  Puzzle,
  Search,
  Settings,
  ShieldCheck,
  Trash2,
  X,
} from "lucide-react";
import type { Conversation } from "@/lib/types";
import { api, phase8Api } from "@/lib/api";
import { useApp } from "@/lib/hooks";
import { IconBtn, cn } from "./ui";

export function Sidebar({
  conversations,
  onRefresh,
  collapsed,
  onToggle,
  mobileOpen,
  onCloseMobile,
  activeId,
  runningIds,
}: {
  conversations: Conversation[];
  onRefresh: () => void;
  collapsed: boolean;
  onToggle: () => void;
  mobileOpen: boolean;
  onCloseMobile: () => void;
  activeId: string | null;
  runningIds: Set<string>;
}) {
  const { user, branding, uiSettings, logout, t } = useApp();
  const features = uiSettings?.features;
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<Conversation | null>(null);
  const [searchResults, setSearchResults] = useState<{
    conversations: { id: string; title: string }[];
    files: { id: string; name: string; kind: string }[];
    projects: { id: string; name: string }[];
  } | null>(null);

  useEffect(() => {
    const q = query.trim();
    if (!q) {
      setSearchResults(null);
      return;
    }
    const t = setTimeout(() => {
      phase8Api.globalSearch(q)
        .then((r) => setSearchResults({
          conversations: (r.conversations as { id: string; title: string }[]) ?? [],
          files: (r.files as { id: string; name: string; kind: string }[]) ?? [],
          projects: (r.projects as { id: string; name: string }[]) ?? [],
        }))
        .catch(() => setSearchResults(null));
    }, 250);
    return () => clearTimeout(t);
  }, [query]);

  const pinned = conversations.filter((c) => c.pinned);
  const recent = conversations.filter(
    (c) => !c.pinned && c.title.toLowerCase().includes(query.toLowerCase()),
  );
  const visibleRecent = recent.slice(0, 50);

  const startNewChat = () => {
    onCloseMobile();
    window.history.pushState(null, "", "/");
    window.dispatchEvent(new CustomEvent("aether:new-chat"));
  };

  const remove = async () => {
    if (!pendingDelete) return;
    const id = pendingDelete.id;
    setPendingDelete(null);
    await api.deleteConversation(id);
    onRefresh();
    if (activeId === id) router.push("/");
  };

  const togglePin = async (c: Conversation) => {
    await api.updateConversation(c.id, { pinned: !c.pinned });
    onRefresh();
  };

  if (collapsed && !mobileOpen) {
    return (
      <div className="flex w-14 shrink-0 flex-col items-center gap-2 border-r border-[var(--border)] bg-[var(--sidebar)] py-3">
        <IconBtn title={t("openSidebar", "Open sidebar")} onClick={onToggle}>
          <PanelLeft size={18} />
        </IconBtn>
      </div>
    );
  }

  return (
    <>
      {mobileOpen && (
        <div className="fixed inset-0 z-30 bg-black/40 md:hidden" onClick={onCloseMobile} />
      )}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex w-[260px] shrink-0 flex-col bg-[var(--sidebar)] shadow-[1px_0_0_var(--border)] transition-transform duration-300 md:static md:translate-x-0",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="flex items-center justify-between px-3 pt-3">
          {(features?.chat !== false || features?.work !== false) && <button
            type="button"
            onClick={onToggle}
            className="flex h-9 w-9 items-center justify-center rounded-lg text-[var(--muted)] hover:bg-black/5 dark:hover:bg-white/10"
            title={t("closeSidebar", "Close sidebar")}
          >
            <PanelLeft size={18} />
          </button>}
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={onCloseMobile}
              className="flex h-9 w-9 items-center justify-center rounded-lg text-[var(--muted)] hover:bg-black/5 md:hidden dark:hover:bg-white/10"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        <div className="px-3 pt-2">
          <button
            type="button"
            onClick={startNewChat}
            className="flex items-center gap-2 rounded-lg px-2.5 py-2 text-sm font-medium hover:bg-black/5 dark:hover:bg-white/10"
          >
            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-[var(--fg)] text-[var(--bg)]">
              <Plus size={14} />
            </span>
            {t("newChat", "New chat")}
          </button>
          <div className="mt-1 flex items-center gap-2 rounded-lg px-2.5 py-2 text-sm text-[var(--muted)] hover:bg-black/5 dark:hover:bg-white/10">
            <Search size={15} />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t("searchChats", "Search chats")}
              aria-label={t("searchChats", "Search chats")}
              className="w-full bg-transparent outline-none placeholder:text-[var(--muted)]"
            />
          </div>
          {features?.projects !== false && <Link href="/projects" className="mt-1 flex items-center gap-2 rounded-lg px-2.5 py-2 text-sm text-[var(--muted)] hover:bg-black/5 dark:hover:bg-white/10">
            <FolderKanban size={15} />
            {t("projects", "Projects")}
          </Link>}
          {features?.image_generation !== false && <Link href="/images" className="flex items-center gap-2 rounded-lg px-2.5 py-2 text-sm text-[var(--muted)] hover:bg-black/5 dark:hover:bg-white/10">
            <ImageIcon size={15} />
            {t("images", "Images")}
          </Link>}
          {features?.tasks !== false && <Link href="/tasks" className="flex items-center gap-2 rounded-lg px-2.5 py-2 text-sm text-[var(--muted)] hover:bg-black/5 dark:hover:bg-white/10">
            <Clock size={15} />
            {t("tasks", "Tasks")}
          </Link>}
          {features?.library !== false && <Link href="/library" className="flex items-center gap-2 rounded-lg px-2.5 py-2 text-sm text-[var(--muted)] hover:bg-black/5 dark:hover:bg-white/10">
            <LibraryIcon size={15} />
            {t("library", "Library")}
          </Link>}
          {features?.plugins !== false && <Link href="/plugins" className="flex items-center gap-2 rounded-lg px-2.5 py-2 text-sm text-[var(--muted)] hover:bg-black/5 dark:hover:bg-white/10">
            <Puzzle size={15} />
            {t("plugins", "Plugins")}
          </Link>}
        </div>

        <nav className="mt-2 flex-1 overflow-y-auto px-3 pb-4">
          {searchResults ? (
            <div>
              <div className="px-2.5 pb-1 pt-3 text-xs font-semibold text-[var(--muted)]">{t("results", "Results")}</div>
              {searchResults.conversations.length === 0 && searchResults.files.length === 0 && searchResults.projects.length === 0 && (
                <div className="px-2.5 py-2 text-sm text-[var(--muted)]">{t("noResults", "No results")}</div>
              )}
              {searchResults.conversations.map((c) => (
                <Link key={c.id} href={`/c/${c.id}`} onClick={onCloseMobile}
                  className="flex items-center gap-2 rounded-lg px-2.5 py-2 text-sm hover:bg-black/5 dark:hover:bg-white/10">
                  <MessageSquare size={14} className="shrink-0 text-[var(--muted)]" />
                  <span className="truncate">{c.title}</span>
                </Link>
              ))}
              {searchResults.projects.map((p) => (
                <Link key={p.id} href={`/projects/${p.id}`} onClick={onCloseMobile}
                  className="flex items-center gap-2 rounded-lg px-2.5 py-2 text-sm hover:bg-black/5 dark:hover:bg-white/10">
                  <FolderKanban size={14} className="shrink-0 text-[var(--muted)]" />
                  <span className="truncate">{p.name}</span>
                </Link>
              ))}
              {searchResults.files.map((f) => (
                <Link key={f.id} href="/library" onClick={onCloseMobile}
                  className="flex items-center gap-2 rounded-lg px-2.5 py-2 text-sm hover:bg-black/5 dark:hover:bg-white/10">
                  <LibraryIcon size={14} className="shrink-0 text-[var(--muted)]" />
                  <span className="truncate">{f.name}</span>
                </Link>
              ))}
            </div>
          ) : (
            <>
              {pinned.length > 0 && (
                <>
                  <div className="px-2.5 pb-1 pt-3 text-xs font-semibold text-[var(--muted)]">{t("pinned", "Pinned")}</div>
                  {pinned.map((c) => (
                    <ChatRow key={c.id} c={c} active={activeId === c.id} running={runningIds.has(c.id)} onDelete={() => setPendingDelete(c)} onPin={togglePin} />
                  ))}
                </>
              )}
              <div className="px-2.5 pb-1 pt-3 text-xs font-semibold text-[var(--muted)]">{t("chats", "Chats")}</div>
              {recent.length === 0 && (
                <div className="px-2.5 py-2 text-sm text-[var(--muted)]">{t("noChats", "No chats yet")}</div>
              )}
              {visibleRecent.map((c) => (
                <ChatRow key={c.id} c={c} active={activeId === c.id} running={runningIds.has(c.id)} onDelete={() => setPendingDelete(c)} onPin={togglePin} />
              ))}
              {recent.length > visibleRecent.length && (
                <div className="px-2.5 py-2 text-xs text-[var(--muted)]">{t("moreChats", "Search to find older chats")}</div>
              )}
            </>
          )}
        </nav>

        <div className="relative border-t border-[var(--border)] px-3 py-2">
          {menuOpen && (
            <div className="absolute bottom-full left-3 right-3 z-20 mb-1 rounded-xl border border-[var(--border)] bg-[var(--bg)] py-1 shadow-xl">
              {user?.role === "owner" || user?.role === "admin" ? (
                <Link href="/admin" className="flex items-center gap-2 px-3 py-2 text-sm hover:bg-[var(--surface)]" onClick={() => setMenuOpen(false)}>
                  <ShieldCheck size={15} /> {t("adminConsole", "Admin console")}
                </Link>
              ) : null}
              <Link href="/settings" className="flex items-center gap-2 px-3 py-2 text-sm hover:bg-[var(--surface)]" onClick={() => setMenuOpen(false)}>
                <Settings size={15} /> {t("settings", "Settings")}
              </Link>
              <button type="button" onClick={logout} className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-[var(--surface)]">
                <X size={15} /> {t("logout", "Log out")}
              </button>
            </div>
          )}
          <button
            type="button"
            onClick={() => setMenuOpen(!menuOpen)}
            className="flex w-full items-center gap-2.5 rounded-lg px-2 py-2 hover:bg-black/5 dark:hover:bg-white/10"
          >
            <span className="flex h-7 w-7 items-center justify-center rounded-full bg-accent text-xs font-semibold text-white">
              {(user?.name || user?.email || "?").slice(0, 1).toUpperCase()}
            </span>
            <span className="truncate text-sm">{user?.name || user?.email}</span>
          </button>
          <div className="px-2 pb-1 pt-1 text-[11px] text-[var(--muted)]">{branding?.product_name}</div>
        </div>
      </aside>
      {pendingDelete && (
        <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/45 p-4" onClick={() => setPendingDelete(null)}>
          <div role="dialog" aria-modal="true" className="w-full max-w-sm rounded-2xl bg-[var(--bg)] p-5 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <h2 className="text-base font-semibold">{t("deleteChat", "Delete chat?")}</h2>
            <p className="mt-2 text-sm text-[var(--muted)]">{t("deleteChatWarning", "This chat will be permanently deleted.")}</p>
            <div className="mt-5 flex justify-end gap-2">
              <button type="button" onClick={() => setPendingDelete(null)} className="rounded-full border border-[var(--border)] px-4 py-2 text-sm">{t("cancel", "Cancel")}</button>
              <button type="button" onClick={remove} className="rounded-full bg-red-600 px-4 py-2 text-sm font-medium text-white">{t("delete", "Delete")}</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function ChatRow({
  c,
  active,
  running,
  onDelete,
  onPin,
}: {
  c: Conversation;
  active: boolean;
  running: boolean;
  onDelete: () => void;
  onPin: (c: Conversation) => void;
}) {
  const { t } = useApp();
  const title = !c.title || c.title === "New chat" ? t("newChat", "New chat") : c.title;
  return (
    <div
      className={cn(
        "group relative flex items-center rounded-lg",
        active ? "bg-black/5 dark:bg-white/10" : "hover:bg-black/5 dark:hover:bg-white/10",
      )}
    >
      <Link href={`/c/${c.id}`} className="flex min-w-0 flex-1 items-center gap-2 px-2.5 py-2 text-sm">
        {running ? <Loader2 size={14} className="shrink-0 animate-spin text-accent" /> : c.mode === "work"
          ? <BriefcaseBusiness size={14} className="shrink-0 text-[var(--muted)]" />
          : <MessageSquare size={14} className="shrink-0 text-[var(--muted)]" />}
        <span className="truncate">{title}</span>
      </Link>
      <div className="hidden items-center gap-0.5 pr-1.5 group-hover:flex">
        <IconBtn title={c.pinned ? t("unpin", "Unpin") : t("pin", "Pin")} onClick={() => onPin(c)} className="h-7 w-7">
          <Pin size={13} className={cn(c.pinned && "text-accent")} />
        </IconBtn>
        <IconBtn title={t("delete", "Delete")} onClick={onDelete} className="h-7 w-7">
          <Trash2 size={13} />
        </IconBtn>
      </div>
    </div>
  );
}
