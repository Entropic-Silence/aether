"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { Conversation } from "./types";
import { api, getToken } from "./api";

interface ConversationsState {
  conversations: Conversation[];
  refresh: () => Promise<void>;
  activeId: string | null;
  setActiveId: (id: string | null) => void;
  runningIds: Set<string>;
  setConversationRunning: (id: string, running: boolean) => void;
}

const ConversationsContext = createContext<ConversationsState | null>(null);

export function ConversationsProvider({ children }: { children: React.ReactNode }) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [runningIds, setRunningIds] = useState<Set<string>>(new Set());

  const setConversationRunning = useCallback((id: string, running: boolean) => {
    setRunningIds((current) => {
      const next = new Set(current);
      if (running) next.add(id);
      else next.delete(id);
      return next;
    });
  }, []);

  const refresh = useCallback(async () => {
    if (!getToken()) return;
    try {
      setConversations(await api.listConversations());
    } catch {
      setConversations([]);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const handleAuthChanged = () => void refresh();
    window.addEventListener("aether:auth-changed", handleAuthChanged);
    window.addEventListener("storage", handleAuthChanged);
    return () => {
      window.removeEventListener("aether:auth-changed", handleAuthChanged);
      window.removeEventListener("storage", handleAuthChanged);
    };
  }, [refresh]);

  return (
    <ConversationsContext.Provider value={{ conversations, refresh, activeId, setActiveId, runningIds, setConversationRunning }}>
      {children}
    </ConversationsContext.Provider>
  );
}

export function useConversations(): ConversationsState {
  const ctx = useContext(ConversationsContext);
  if (!ctx) throw new Error("useConversations must be used within ConversationsProvider");
  return ctx;
}
