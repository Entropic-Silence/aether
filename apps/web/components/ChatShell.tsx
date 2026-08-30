"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, Check, Image as ImageIcon, MessageCircle, Share2, WandSparkles } from "lucide-react";
import type { Block, Conversation, FileMeta, ImageAspectRatio, ImageGenerationResult, ImageModelInfo, Message, MessageBranch, ModelInfo, PluginInfo, UiSettings } from "@/lib/types";
import { api, phase6Api, phase8Api } from "@/lib/api";
import { runConversation, runResearch, streamGet } from "@/lib/stream";
import { useApp, useModelCatalog } from "@/lib/hooks";
import { useConversations } from "@/lib/chat-context";
import { Composer } from "./Composer";
import { AuthImage } from "./AuthImage";
import { MaskEditor } from "./MaskEditor";
import { MessageView, ThinkingDots, type LiveTool } from "./Message";
import { ModelSelector, ReasoningSelector } from "./ModelSelector";
import { Button, Spinner, cn } from "./ui";

interface StreamState {
  active: boolean;
  reasoning: string;
  text: string;
  assistantMessageId: string | null;
  tools: LiveTool[];
  search: { active: boolean; query: string; sourceCount: number };
  startedAt?: number | null;
}

interface ResearchProgress {
  phase: "planning" | "searching" | "reading" | "synthesizing" | "done";
  questions: string[];
  currentQuery: string;
  readingUrl: string;
  sourceCount: number;
}

interface PendingApproval {
  approvalId: string;
  toolCallId: string;
  name: string;
  risk: string;
}

interface WorkStep {
  event: string;
  label: string;
  detail: string;
  at: string;
}

interface WorkState {
  runId: string | null;
  status: string;
  steps: WorkStep[];
  plan: string[];
  approval: PendingApproval | null;
}

const IMAGE_ASPECT_RATIOS: Array<ImageAspectRatio | "auto"> = [
  "auto", "1:1", "16:9", "9:16", "3:2", "2:3", "4:3", "3:4", "5:4", "4:5", "21:9", "9:21",
];

function optimisticUserBlocks(content: string, files: FileMeta[]): Block[] {
  const blocks: Block[] = content ? [{ id: `tmp-text-${Date.now()}`, seq: 0, type: "text", data: { text: content } }] : [];
  files.forEach((file) => {
    blocks.push({
      id: `tmp-file-${file.id}`,
      seq: blocks.length,
      type: file.kind === "image" ? "image" : "file",
      data: {
        file_id: file.id, name: file.name, mime: file.mime, size: file.size,
        kind: file.kind, status: file.status,
        ...(file.kind === "image" ? { url: `/api/v1/files/${file.id}/download` } : {}),
      },
    });
  });
  return blocks;
}

export function ChatShell({ initialConversationId }: { initialConversationId?: string }) {
  const { branding, t, locale } = useApp();
  const { refresh: refreshConversations, setActiveId, setConversationRunning } = useConversations();
  const { models } = useModelCatalog();
  const router = useRouter();

  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [messageBranches, setMessageBranches] = useState<MessageBranch[]>([]);
  const [loading, setLoading] = useState(Boolean(initialConversationId));
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedModelId, setSelectedModelId] = useState<string | null>(null);
  const [reasoningEffort, setReasoningEffort] = useState("auto");
  const [stream, setStream] = useState<StreamState>({ active: false, reasoning: "", text: "", assistantMessageId: null, tools: [], search: { active: false, query: "", sourceCount: 0 } });
  const [runError, setRunError] = useState<string | null>(null);
  const [attachments, setAttachments] = useState<FileMeta[]>([]);
  const [uploading, setUploading] = useState(0);
  const [uiSettings, setUiSettings] = useState<UiSettings | null>(null);
  const [webSearch, setWebSearch] = useState(false);
  const [researchOpen, setResearchOpen] = useState(false);
  const [researchGoal, setResearchGoal] = useState("");
  const [researchProgress, setResearchProgress] = useState<ResearchProgress | null>(null);
  const [imageModels, setImageModels] = useState<ImageModelInfo[]>([]);
  const [imageOpen, setImageOpen] = useState(false);
  const [imagePrompt, setImagePrompt] = useState("");
  const [imageBusy, setImageBusy] = useState(false);
  const [imagePhase, setImagePhase] = useState<"idle" | "optimizing" | "generating">("idle");
  const [imageResult, setImageResult] = useState<ImageGenerationResult | null>(null);
  const [composerImageMode, setComposerImageMode] = useState(false);
  const [imageAspectRatio, setImageAspectRatio] = useState<ImageAspectRatio | "auto">("auto");
  const [imageTask, setImageTask] = useState<{ active: boolean; phase: "optimizing" | "generating"; refinedPrompt: string }>({
    active: false, phase: "optimizing", refinedPrompt: "",
  });
  const [imageMode, setImageMode] = useState<"txt2img" | "img2img" | "inpaint">("txt2img");
  const [imageModelId, setImageModelId] = useState<string | null>(null);
  const [sourceFile, setSourceFile] = useState<{ file_id: string; url: string } | null>(null);
  const [maskBlob, setMaskBlob] = useState<Blob | null>(null);
  const [strength, setStrength] = useState(0.6);
  const sourceInputRef = useRef<HTMLInputElement>(null);

  const selectedImageModel = useMemo(
    () => imageModels.find((m) => m.id === imageModelId) ?? imageModels.find((m) => m.is_default) ?? imageModels[0],
    [imageModels, imageModelId],
  );
  const [mode, setMode] = useState<"chat" | "work" | "study">("chat");
  const [workRuntime] = useState<"deepseek-harness" | "advanced" | "native">("deepseek-harness");
  const [pendingApproval, setPendingApproval] = useState<PendingApproval | null>(null);
  const [work, setWork] = useState<WorkState>({ runId: null, status: "", steps: [], plan: [], approval: null });
  const [steerText, setSteerText] = useState("");
  const [shareMsg, setShareMsg] = useState<string | null>(null);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [routingPrompt, setRoutingPrompt] = useState(false);
  const [workPlugins, setWorkPlugins] = useState<PluginInfo[]>([]);
  const [selectedPluginIds, setSelectedPluginIds] = useState<string[]>([]);
  const routingPromptRef = useRef(false);

  const shareConversation = useCallback(async () => {
    const cid = conversation?.id ?? initialConversationId;
    if (!cid) return;
    try {
      const share = await phase8Api.createShare(cid, "link");
      const url = `${window.location.origin}${share.url}`;
      try {
        await navigator.clipboard.writeText(url);
        setShareMsg(t("linkCopied", "Link copied to clipboard"));
      } catch {
        setShareMsg(url);
      }
      setTimeout(() => setShareMsg(null), 3000);
    } catch (e) {
      setShareMsg(e instanceof Error ? e.message : t("shareFailed", "Share failed"));
      setTimeout(() => setShareMsg(null), 3000);
    }
  }, [conversation, initialConversationId, t]);

  useEffect(() => {
    const loadUiSettings = () => api.uiSettings().then(setUiSettings).catch(() => setUiSettings(null));
    void loadUiSettings();
    api.listImageModels().then(setImageModels).catch(() => setImageModels([]));
    phase6Api.listPlugins().then((data) => setWorkPlugins(data.plugins.filter((plugin) => plugin.enabled && plugin.status === "valid"))).catch(() => setWorkPlugins([]));
    window.addEventListener("focus", loadUiSettings);
    const onVisibility = () => { if (document.visibilityState === "visible") void loadUiSettings(); };
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      window.removeEventListener("focus", loadUiSettings);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);

  useEffect(() => {
    if (conversation || !uiSettings?.features) return;
    if (mode === "chat" && uiSettings.features.chat === false && uiSettings.features.work !== false) setMode("work");
    if (mode === "work" && uiSettings.features.work === false && uiSettings.features.chat !== false) setMode("chat");
  }, [conversation, mode, uiSettings]);

  useEffect(() => {
    if (uiSettings?.features.image_generation === false) setComposerImageMode(false);
  }, [uiSettings?.features.image_generation]);

  const handleFiles = useCallback(async (files: File[]) => {
    for (const file of files) {
      setUploading((n) => n + 1);
      try {
        const meta = await api.uploadFile(file);
        setAttachments((prev) => [...prev, meta]);
      } catch (e) {
        setRunError(e instanceof Error ? e.message : "Upload failed");
      } finally {
        setUploading((n) => n - 1);
      }
    }
  }, []);
  const persistFailure = useCallback(async (
    convId: string,
    content: string,
    error: unknown,
    retryKind: "chat" | "image_generation" | "work" = "chat",
    durationMs = 0,
    parentUserMessageId?: string | null,
  ) => {
    const message = error instanceof Error ? error.message : String(error || "Generation failed");
    try {
      await api.recordConversationError(convId, {
        content, message, code: retryKind === "image_generation" ? "IMAGE_GENERATION_FAILED" : "RESPONSE_FAILED",
        retry_kind: retryKind,
        model_id: selectedModelId ?? models.find((model) => model.is_default)?.id ?? models[0]?.id ?? null,
        parent_user_message_id: parentUserMessageId ?? null,
        duration_ms: durationMs,
      });
      setMessages(await api.getMessages(convId));
      setRunError(null);
      refreshConversations();
    } catch {
      setMessages((prev) => [...prev, {
        id: `tmp-error-${Date.now()}`, conversation_id: convId,
        parent_id: prev[prev.length - 1]?.id ?? null, role: "assistant",
        model_id: selectedModelId ?? models.find((model) => model.is_default)?.id ?? models[0]?.id ?? null, status: "failed",
        error: { code: "RESPONSE_FAILED", message, retryable: true, kind: retryKind },
        usage: { duration_ms: durationMs }, created_at: new Date().toISOString(),
        blocks: [{ id: `tmp-error-block-${Date.now()}`, seq: 0, type: "error", data: { message, retryable: true, kind: retryKind } }],
      }]);
      setRunError(null);
    }
  }, [models, refreshConversations, selectedModelId]);
  const abortRef = useRef<AbortController | null>(null);
  const workAbortRef = useRef<AbortController | null>(null);
  const activeConversationIdRef = useRef<string | null>(initialConversationId ?? null);
  const recoveringRunRef = useRef<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);

  useEffect(() => {
    const reset = () => {
      workAbortRef.current?.abort();
      activeConversationIdRef.current = null;
      recoveringRunRef.current = null;
      setConversation(null);
      setMessages([]);
      setMessageBranches([]);
      setLoading(false);
      setLoadError(null);
      setRunError(null);
      setAttachments([]);
      setStream({ active: false, reasoning: "", text: "", assistantMessageId: null, tools: [], search: { active: false, query: "", sourceCount: 0 }, startedAt: null });
      setWork({ runId: null, status: "", steps: [], plan: [], approval: null });
      setResearchProgress(null);
      setImageTask({ active: false, phase: "optimizing", refinedPrompt: "" });
      setComposerImageMode(false);
      setImageAspectRatio("auto");
      setElapsedMs(0);
      setActiveId(null);
    };
    window.addEventListener("aether:new-chat", reset);
    return () => window.removeEventListener("aether:new-chat", reset);
  }, [setActiveId]);

  useEffect(() => {
    if (!stream.active || !stream.startedAt) return;
    setElapsedMs(Date.now() - stream.startedAt);
    const timer = window.setInterval(() => setElapsedMs(Date.now() - stream.startedAt!), 100);
    return () => window.clearInterval(timer);
  }, [stream.active, stream.startedAt]);

  const selectedModel: ModelInfo | undefined = useMemo(
    () => models.find((m) => m.id === selectedModelId) ?? models.find((m) => m.is_default) ?? models[0],
    [models, selectedModelId],
  );
  const supportsReasoning = selectedModel?.effective_capabilities?.reasoning === true;
  const canImages =
    selectedModel?.effective_capabilities?.image_input === true ||
    uiSettings?.vision_fallback_configured === true;

  useEffect(() => {
    setActiveId(initialConversationId ?? null);
    return () => setActiveId(null);
  }, [initialConversationId, setActiveId]);

  useEffect(() => {
    activeConversationIdRef.current = initialConversationId ?? null;
    workAbortRef.current?.abort();
    recoveringRunRef.current = null;
    setWork({ runId: null, status: "", steps: [], plan: [], approval: null });
    setStream({ active: false, reasoning: "", text: "", assistantMessageId: null, tools: [], search: { active: false, query: "", sourceCount: 0 }, startedAt: null });
    if (!initialConversationId) {
      setConversation(null);
      setMessages([]);
      setMessageBranches([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    (async () => {
      try {
        const [conv, msgs, branches] = await Promise.all([
          api.getConversation(initialConversationId),
          api.getMessages(initialConversationId),
          api.getMessageBranches(initialConversationId),
        ]);
        if (cancelled) return;
        setConversation(conv);
        setMessages(msgs);
        setMessageBranches(branches);
        setSelectedModelId(conv.model_id);
        setMode(conv.mode === "work" ? "work" : conv.mode === "study" ? "study" : "chat");
      } catch (e) {
        if (!cancelled) setLoadError(e instanceof Error ? e.message : "Failed to load conversation");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [initialConversationId]);

  useEffect(() => {
    const el = scrollRef.current;
    if (el && stickToBottom.current) el.scrollTop = el.scrollHeight;
  }, [messages, stream.text, stream.reasoning]);

  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
  };

  const stop = useCallback(async () => {
    const conversationId = conversation?.id ?? activeConversationIdRef.current;
    const messageId = stream.assistantMessageId;
    if (conversationId && messageId) {
      try {
        await api.cancelConversationRun(conversationId, messageId);
      } catch {
        /* aborting the connection remains a fallback */
      }
    }
    abortRef.current?.abort();
    setStream((s) => ({ ...s, active: false }));
    if (conversationId) {
      setConversationRunning(conversationId, false);
      window.setTimeout(() => api.getMessages(conversationId).then(setMessages).catch(() => undefined), 250);
    }
  }, [conversation?.id, setConversationRunning, stream.assistantMessageId]);

  const send = useCallback(
    async (content: string, opts?: { regenerateFrom?: string; skipOptimistic?: boolean; pendingAssistantId?: string }) => {
      if (stream.active) return;
      stickToBottom.current = true;
      setRunError(null);
      const regenerateFrom = opts?.regenerateFrom ?? null;
      const requestStarted = Date.now();

      let convId = conversation?.id ?? null;
      if (!convId) {
        const conv = await api.createConversation({
          model_id: selectedModel?.id ?? null,
          temporary: false,
          mode: mode === "study" ? "study" : "chat",
        });
        convId = conv.id;
        activeConversationIdRef.current = conv.id;
        setConversation(conv);
        window.history.replaceState(null, "", `/c/${conv.id}`);
        setActiveId(conv.id);
      }

      let optimisticUser: Message | null = null;
      if (!regenerateFrom && !opts?.skipOptimistic) {
        optimisticUser = {
          id: `tmp-user-${Date.now()}`,
          conversation_id: convId,
          parent_id: null,
          role: "user",
          model_id: null,
          status: "completed",
          error: null,
          usage: null,
          created_at: new Date().toISOString(),
          blocks: optimisticUserBlocks(content, attachments),
        };
        setMessages((prev) => [...prev, optimisticUser!]);
      }
      setElapsedMs(0);
      setStream({ active: true, reasoning: "", text: "", assistantMessageId: opts?.pendingAssistantId ?? null, tools: [], search: { active: false, query: "", sourceCount: 0 }, startedAt: null });
      setConversationRunning(convId, true);

      const fileIds = attachments.filter((a) => a.status !== "failed").map((a) => a.id);
      const sentAttachments = attachments;
      setAttachments([]);

      const controller = new AbortController();
      abortRef.current = controller;

      await runConversation(
        convId,
        {
          content,
          parent_id: regenerateFrom ?? undefined,
          model_id: selectedModel?.id ?? null,
          reasoning_effort: reasoningEffort === "auto" ? undefined : reasoningEffort,
          file_ids: regenerateFrom ? [] : fileIds,
          web_search: regenerateFrom ? false : webSearch,
        },
        {
          onEvent: ({ event, data }) => {
            if (activeConversationIdRef.current !== convId) {
              if (event === "conversation.title") refreshConversations();
              return;
            }
            if (event === "response.created") {
              const assistantId = data.assistant_message_id as string;
              setStream((s) => ({ ...s, assistantMessageId: assistantId, startedAt: s.startedAt ?? Date.now() }));
            } else if (event === "reasoning.delta") {
              setStream((s) => ({ ...s, reasoning: s.reasoning + (data.delta as string) }));
            } else if (event === "block.delta") {
              setStream((s) => ({ ...s, text: s.text + (data.delta as string) }));
            } else if (event === "tool.started") {
              setStream((s) => ({
                ...s,
                tools: [
                  ...s.tools,
                  {
                    id: String(data.tool_call_id),
                    name: String(data.name),
                    arguments: (data.arguments as Record<string, unknown>) ?? {},
                    status: "running",
                  },
                ],
              }));
            } else if (event === "tool.approval_required") {
              setPendingApproval({
                approvalId: String(data.approval_id),
                toolCallId: String(data.tool_call_id),
                name: String(data.name),
                risk: String(data.risk ?? ""),
              });
            } else if (event === "tool.completed") {
              setStream((s) => ({
                ...s,
                tools: s.tools.map((t) =>
                  t.id === data.tool_call_id
                    ? {
                        ...t,
                        status: data.ok === false ? "failed" : "done",
                        result: {
                          ok: data.ok,
                          exit_code: data.exit_code,
                          stdout: data.stdout,
                          stderr: data.stderr,
                          files: data.files,
                        },
                      }
                    : t,
                ),
              }));
            } else if (event === "tool.failed") {
              setStream((s) => ({
                ...s,
                tools: s.tools.map((t) =>
                  t.id === data.tool_call_id
                    ? { ...t, status: "failed", result: { ok: false, error: data.error } }
                    : t,
                ),
              }));
            } else if (event === "search.started") {
              setStream((s) => ({
                ...s,
                search: { active: true, query: String(data.query ?? ""), sourceCount: 0 },
              }));
            } else if (event === "search.result") {
              setStream((s) => ({
                ...s,
                search: { ...s.search, active: false, sourceCount: Array.isArray(data.sources) ? data.sources.length : 0 },
              }));
            } else if (event === "conversation.title") {
              refreshConversations();
            } else if (event === "error") {
              setStream((s) => ({ ...s, active: false }));
              setConversationRunning(convId!, false);
            }
          },
          onError: (err) => {
            if (activeConversationIdRef.current !== convId) {
              setConversationRunning(convId!, false);
              return;
            }
            setStream((s) => ({ ...s, active: false }));
            setConversationRunning(convId!, false);
            if (sentAttachments.length) setAttachments(sentAttachments);
            void persistFailure(convId!, content, new Error(err.message || "Generation failed"), "chat", Date.now() - requestStarted, regenerateFrom);
          },
          onDone: async () => {
            if (activeConversationIdRef.current !== convId) {
              refreshConversations();
              setConversationRunning(convId!, false);
              return;
            }
            setStream({ active: false, reasoning: "", text: "", assistantMessageId: null, tools: [], search: { active: false, query: "", sourceCount: 0 } });
            try {
              const msgs = await api.getMessages(convId!);
              setMessages(msgs);
            } catch {
              /* keep optimistic state */
            }
            refreshConversations();
            setConversationRunning(convId!, false);
          },
        },
        controller.signal,
      ).catch(async (e) => {
        if (activeConversationIdRef.current !== convId) {
          if ((e as Error).name !== "AbortError") setConversationRunning(convId!, false);
          return;
        }
        setStream((s) => ({ ...s, active: false }));
        if ((e as Error).name !== "AbortError") {
          setConversationRunning(convId!, false);
          if (sentAttachments.length) setAttachments(sentAttachments);
          await persistFailure(convId!, content, e, "chat", Date.now() - requestStarted, regenerateFrom);
        }
      });
    },
    [conversation, selectedModel, reasoningEffort, stream.active, attachments, webSearch, mode, refreshConversations, setActiveId, setConversationRunning, persistFailure],
  );

  const startResearch = useCallback(async () => {
    const goal = researchGoal.trim();
    if (!goal || stream.active) return;
    setResearchOpen(false);
    setResearchGoal("");
    setRunError(null);
    stickToBottom.current = true;

    let convId = conversation?.id ?? null;
    if (!convId) {
      const conv = await api.createConversation({ model_id: selectedModel?.id ?? null });
      convId = conv.id;
      setConversation(conv);
      window.history.replaceState(null, "", `/c/${conv.id}`);
      setActiveId(conv.id);
    }

    setStream({
      active: true, reasoning: "", text: "", assistantMessageId: null, tools: [],
      search: { active: false, query: "", sourceCount: 0 }, startedAt: null,
    });
    setConversationRunning(convId, true);
    setResearchProgress({ phase: "planning", questions: [], currentQuery: "", readingUrl: "", sourceCount: 0 });

    const controller = new AbortController();
    abortRef.current = controller;
    const targetConv = convId;

    await runResearch(
      convId,
      { goal, model_id: selectedModel?.id ?? null },
      {
        onEvent: ({ event, data }) => {
          if (event === "response.created") {
            setStream((s) => ({ ...s, assistantMessageId: data.assistant_message_id as string, startedAt: s.startedAt ?? Date.now() }));
          } else if (event === "research.planning") {
            setResearchProgress((p) => p && { ...p, phase: "planning" });
          } else if (event === "research.plan") {
            setResearchProgress((p) => p && { ...p, questions: (data.questions as string[]) ?? [] });
          } else if (event === "research.searching") {
            setResearchProgress((p) => p && { ...p, phase: "searching", currentQuery: String(data.query ?? "") });
          } else if (event === "research.reading") {
            setResearchProgress((p) => p && { ...p, phase: "reading", readingUrl: String(data.url ?? "") });
          } else if (event === "research.synthesizing") {
            setResearchProgress((p) => p && { ...p, phase: "synthesizing", sourceCount: Number(data.source_count ?? 0) });
          } else if (event === "block.delta") {
            setStream((s) => ({ ...s, text: s.text + (data.delta as string) }));
          }
        },
        onError: (err) => {
          setStream((s) => ({ ...s, active: false }));
          setResearchProgress(null);
          setRunError(err.message || "Research failed");
          setConversationRunning(targetConv, false);
        },
        onDone: async () => {
          setStream({ active: false, reasoning: "", text: "", assistantMessageId: null, tools: [], search: { active: false, query: "", sourceCount: 0 } });
          setResearchProgress((p) => (p ? { ...p, phase: "done" } : p));
          try {
            const msgs = await api.getMessages(targetConv);
            setMessages(msgs);
          } catch {
            /* keep */
          }
          refreshConversations();
          setConversationRunning(targetConv, false);
          setTimeout(() => setResearchProgress(null), 1500);
        },
      },
      controller.signal,
    ).catch((e) => {
      setStream((s) => ({ ...s, active: false }));
      setResearchProgress(null);
      if ((e as Error).name !== "AbortError") setRunError((e as Error).message || "Research failed");
    });
  }, [researchGoal, conversation, selectedModel, stream.active, refreshConversations, setActiveId, setConversationRunning]);

  const subscribeToWork = useCallback((runId: string, convId: string) => {
    const controller = new AbortController();
    workAbortRef.current?.abort();
    workAbortRef.current = controller;
    setWork({ runId, status: "working", steps: [], plan: [], approval: null });
    streamGet(
      `/api/v1/work/runs/${runId}/events`,
      {
        onEvent: ({ event, data }) => {
          if (activeConversationIdRef.current !== convId) return;
          const stepFor = (label: string, detail = "") => {
            setWork((w) => ({
              ...w,
              steps: [...w.steps, { event, label, detail, at: new Date().toISOString() }],
            }));
          };
          if (event === "reasoning.delta") {
            setStream((s) => ({ ...s, reasoning: s.reasoning + String(data.delta ?? ""), startedAt: s.startedAt ?? Date.now() }));
          } else if (event === "block.delta") {
            setStream((s) => ({ ...s, text: s.text + String(data.delta ?? ""), startedAt: s.startedAt ?? Date.now() }));
          } else if (event === "work.planning") {
            setStream((s) => ({ ...s, startedAt: s.startedAt ?? Date.now() }));
            setWork((w) => ({ ...w, status: "planning" }));
            stepFor("Planning", String(data.task ?? "").slice(0, 120));
          } else if (event === "work.plan") {
            const steps = Array.isArray(data.steps) ? (data.steps as string[]) : [];
            setWork((w) => ({ ...w, plan: steps }));
          } else if (event === "work.status") {
            setWork((w) => ({ ...w, status: "working" }));
            stepFor(locale === "zh-CN" ? "正在整理结果" : "Preparing result", String(data.status ?? ""));
          } else if (event === "work.step") {
            setWork((w) => ({ ...w, status: "working" }));
            stepFor(String(data.step ?? "Working"), String(data.tool ?? ""));
          } else if (event === "work.waiting_approval") {
            setWork((w) => ({
              ...w,
              status: "waiting_approval",
              approval: {
                approvalId: String(data.approval_id),
                toolCallId: String(data.tool_call_id),
                name: String(data.name),
                risk: String(data.risk ?? ""),
              },
            }));
          } else if (event === "work.approved") {
            setWork((w) => ({ ...w, approval: null, status: "working" }));
          } else if (event === "tool.denied") {
            setWork((w) => ({ ...w, approval: null, status: "working" }));
            stepFor("Tool denied", String(data.name ?? ""));
          } else if (event === "work.steered") {
            stepFor("New instruction", String(data.content ?? "").slice(0, 120));
          } else if (event === "work.completed") {
            setWork((w) => ({ ...w, status: "completed" }));
          } else if (event === "work.failed") {
            setWork((w) => ({ ...w, status: "failed" }));
          } else if (event === "work.cancelled") {
            setWork((w) => ({ ...w, status: "cancelled" }));
          } else if (event === "work.done") {
            recoveringRunRef.current = null;
            api.getMessages(convId).then(setMessages).catch(() => undefined).finally(() => {
              setStream({ active: false, reasoning: "", text: "", assistantMessageId: null, tools: [], search: { active: false, query: "", sourceCount: 0 } });
              refreshConversations();
              setConversationRunning(convId, false);
            });
          }
        },
        onError: (err) => {
          if (activeConversationIdRef.current !== convId) return;
          setWork((w) => ({ ...w, status: "failed" }));
          setStream((s) => ({ ...s, active: false }));
          setConversationRunning(convId, false);
          api.getMessages(convId).then(setMessages).catch(() => undefined);
        },
      },
      controller.signal,
    ).catch((error) => {
      if ((error as Error).name === "AbortError" || activeConversationIdRef.current !== convId) return;
      setWork((w) => ({ ...w, status: "failed" }));
      setStream((s) => ({ ...s, active: false }));
      setConversationRunning(convId, false);
    });
  }, [refreshConversations, locale, setConversationRunning]);

  useEffect(() => {
    const convId = conversation?.id;
    if (!convId || loading) return;
    let cancelled = false;
    let pollTimer: number | undefined;
    (async () => {
      const runs = conversation.mode === "work" ? await phase6Api.workRuns(convId).catch(() => []) : [];
      if (cancelled || activeConversationIdRef.current !== convId) return;
      const activeRun = runs.find((run) => ["working", "planning", "waiting_approval"].includes(run.status));
      const pendingMessage = [...messages].reverse().find((message) =>
        message.role === "assistant" && ["working", "streaming"].includes(message.status));
      if (activeRun) {
        if (recoveringRunRef.current === activeRun.id) return;
        recoveringRunRef.current = activeRun.id;
        const assistantId = activeRun.assistant_message_id ?? pendingMessage?.id ?? null;
        setStream({ active: true, reasoning: "", text: "", assistantMessageId: assistantId, tools: [], search: { active: false, query: "", sourceCount: 0 }, startedAt: Date.now() });
        setConversationRunning(convId, true);
        subscribeToWork(activeRun.id, convId);
        return;
      }
      if (!pendingMessage) return;
      setStream({ active: true, reasoning: "", text: "", assistantMessageId: pendingMessage.id, tools: [], search: { active: false, query: "", sourceCount: 0 }, startedAt: Date.now() });
      setConversationRunning(convId, true);
      const poll = async () => {
        const next = await api.getMessages(convId).catch(() => null);
        if (!next || cancelled || activeConversationIdRef.current !== convId) return;
        setMessages(next);
        const stillPending = next.some((message) => message.role === "assistant" && ["working", "streaming"].includes(message.status));
        if (stillPending) pollTimer = window.setTimeout(poll, 1000);
        else {
          setStream({ active: false, reasoning: "", text: "", assistantMessageId: null, tools: [], search: { active: false, query: "", sourceCount: 0 }, startedAt: null });
          setConversationRunning(convId, false);
          refreshConversations();
        }
      };
      pollTimer = window.setTimeout(poll, 1000);
    })();
    return () => {
      cancelled = true;
      if (pollTimer) window.clearTimeout(pollTimer);
    };
  }, [conversation?.id, conversation?.mode, loading, messages.length, refreshConversations, setConversationRunning, subscribeToWork]);

  const sendWork = useCallback(async (task: string, skipOptimistic = false) => {
    if (work.status === "working" || work.status === "planning" || work.status === "waiting_approval") return;
    let convId = conversation?.id ?? null;
    if (!convId) {
      const conv = await api.createConversation({ mode: "work", model_id: selectedModel?.id ?? null });
      convId = conv.id;
      activeConversationIdRef.current = conv.id;
      setConversation(conv);
      window.history.replaceState(null, "", `/c/${conv.id}`);
      setActiveId(conv.id);
    }
    const optimisticUser: Message = {
      id: `tmp-work-user-${Date.now()}`, conversation_id: convId, parent_id: null, role: "user",
      model_id: null, status: "completed", error: null, usage: null, created_at: new Date().toISOString(),
      blocks: optimisticUserBlocks(task, attachments),
    };
    if (!skipOptimistic) setMessages((prev) => [...prev, optimisticUser]);
    const fileIds = attachments.filter((a) => a.status !== "failed").map((a) => a.id);
    const sentAttachments = attachments;
    setAttachments([]);
    try {
      const res = await phase6Api.startWork(convId, { task, model_id: selectedModel?.id ?? null, runtime: workRuntime, file_ids: fileIds, plugin_ids: selectedPluginIds });
      setElapsedMs(0);
      setStream({ active: true, reasoning: "", text: "", assistantMessageId: res.assistant_message_id, tools: [], search: { active: false, query: "", sourceCount: 0 }, startedAt: null });
      setConversationRunning(convId, true);
      subscribeToWork(res.run_id, convId);
    } catch (e) {
      if (!skipOptimistic) setMessages((prev) => prev.filter((message) => message.id !== optimisticUser.id));
      if (sentAttachments.length) setAttachments(sentAttachments);
      setStream((current) => ({ ...current, active: false, assistantMessageId: null }));
      setConversationRunning(convId, false);
      await persistFailure(convId, task, e instanceof Error ? e : new Error("Failed to start work run"), "work");
    }
  }, [conversation, selectedModel, workRuntime, work.status, subscribeToWork, setActiveId, attachments, selectedPluginIds, setConversationRunning, persistFailure]);

  const decideApproval = useCallback(async (approval: PendingApproval, decision: "allow" | "deny", rule: "once" | "always") => {
    setPendingApproval(null);
    try {
      if (work.runId) {
        await phase6Api.approveWorkTool(work.runId, approval.approvalId, decision, rule);
      } else if (conversation) {
        await phase6Api.approveChatTool(conversation.id, approval.approvalId, decision, rule);
      }
    } catch (e) {
      setRunError(e instanceof Error ? e.message : "Approval failed");
    }
  }, [work.runId, conversation]);

  const steerWork = useCallback(async () => {
    const text = steerText.trim();
    if (!text || !work.runId) return;
    setSteerText("");
    try {
      await phase6Api.steerWork(work.runId, text);
    } catch (e) {
      setRunError(e instanceof Error ? e.message : "Steering failed");
    }
  }, [steerText, work.runId]);

  const cancelWork = useCallback(async () => {
    if (!work.runId) return;
    try {
      await phase6Api.cancelWork(work.runId);
    } catch {
      /* best effort */
    }
    workAbortRef.current?.abort();
    recoveringRunRef.current = null;
    setWork((current) => ({ ...current, status: "cancelled", approval: null }));
    setStream({ active: false, reasoning: "", text: "", assistantMessageId: null, tools: [], search: { active: false, query: "", sourceCount: 0 }, startedAt: null });
    if (conversation?.id) {
      setConversationRunning(conversation.id, false);
      window.setTimeout(() => api.getMessages(conversation.id).then(setMessages).catch(() => undefined), 300);
    }
  }, [conversation?.id, setConversationRunning, work.runId]);

  const uploadSourceImage = useCallback(async (file: File) => {
    try {
      const meta = await api.uploadFile(file);
      const url = URL.createObjectURL(file);
      setSourceFile({ file_id: meta.id, url });
      setMaskBlob(null);
    } catch (e) {
      setRunError(e instanceof Error ? e.message : "Upload failed");
    }
  }, []);

  const createImage = useCallback(async () => {
    const prompt = imagePrompt.trim();
    if (!prompt || imageBusy) return;
    if (imageMode !== "txt2img" && !sourceFile) {
      setRunError("Provide a source image for image-to-image / inpainting.");
      return;
    }
    if (imageMode === "inpaint" && !maskBlob) {
      setRunError("Paint a mask region for inpainting.");
      return;
    }
    setImageBusy(true);
    setRunError(null);
    setImageResult(null);
    const doOptimize = imageMode === "txt2img";
    setImagePhase(doOptimize ? "optimizing" : "generating");
    try {
      let maskFileId: string | null = null;
      if (imageMode === "inpaint" && maskBlob) {
        const maskFile = new File([maskBlob], "mask.png", { type: "image/png" });
        const meta = await api.uploadFile(maskFile);
        maskFileId = meta.id;
      }
      let refinedPrompt = prompt;
      let refinedNegative = "";
      let optimized = false;
      let refinedAspectRatio: ImageAspectRatio | "auto" = imageAspectRatio;
      if (doOptimize) {
        const refinement = await api.optimizeImagePrompt({
          prompt,
          model_id: imageModelId,
          optimizer_model_id: selectedModel?.id ?? null,
          aspect_ratio: imageAspectRatio,
        });
        refinedPrompt = refinement.prompt;
        refinedNegative = refinement.negative_prompt;
        optimized = refinement.optimized;
        refinedAspectRatio = imageAspectRatio === "auto" ? refinement.aspect_ratio : imageAspectRatio;
      }
      setImagePhase("generating");
      const result = await api.generateImage({
        prompt: refinedPrompt,
        negative_prompt: refinedNegative,
        optimize: false,
        mode: imageMode,
        model_id: imageModelId,
        source_file_id: imageMode !== "txt2img" ? sourceFile?.file_id ?? null : null,
        mask_file_id: maskFileId,
        strength,
        aspect_ratio: refinedAspectRatio,
      });
      const visibleResult = { ...result, optimized, prompt_used: refinedPrompt, negative_prompt_used: refinedNegative };
      setImageResult(visibleResult);
      let convId = conversation?.id ?? null;
      if (!convId) {
        const conv = await api.createConversation({});
        convId = conv.id;
        setConversation(conv);
        window.history.replaceState(null, "", `/c/${conv.id}`);
        setActiveId(conv.id);
      }
      await api.attachImageToConversation(convId, result.file_id, prompt, {
        prompt_used: refinedPrompt, negative_prompt_used: refinedNegative, model_name: result.model.name,
        aspect_ratio: result.aspect_ratio, width: result.width, height: result.height,
      });
      const msgs = await api.getMessages(convId);
      setMessages(msgs);
      refreshConversations();
    } catch (e) {
      setRunError(e instanceof Error ? e.message : "Image generation failed");
    } finally {
      setImageBusy(false);
      setImagePhase("idle");
    }
  }, [imagePrompt, imageBusy, imageMode, imageModelId, imageAspectRatio, sourceFile, maskBlob, strength, conversation, refreshConversations, selectedModel, setActiveId]);

  const createImageFromComposer = useCallback(async (rawPrompt: string, retryUserMessageId?: string, skipOptimistic = false) => {
    const prompt = rawPrompt.trim();
    if (!prompt || imageTask.active || imageModels.length === 0) return;
    setRunError(null);
    setStream((current) => ({ ...current, active: false, assistantMessageId: null }));
    setImageTask({ active: true, phase: "optimizing", refinedPrompt: "" });
    stickToBottom.current = true;
    let convId = conversation?.id ?? null;
    if (!convId) {
      const conv = await api.createConversation({ mode: "chat", model_id: selectedModel?.id ?? null });
      convId = conv.id;
      setConversation(conv);
      window.history.replaceState(null, "", `/c/${conv.id}`);
      setActiveId(conv.id);
    }
    const optimisticUser: Message = {
      id: `tmp-image-user-${Date.now()}`, conversation_id: convId, parent_id: null, role: "user",
      model_id: null, status: "completed", error: null, usage: null, created_at: new Date().toISOString(),
      blocks: optimisticUserBlocks(prompt, attachments),
    };
    if (!retryUserMessageId && !skipOptimistic) setMessages((prev) => [...prev, optimisticUser]);
    setComposerImageMode(false);
    setConversationRunning(convId, true);
    const source = attachments.find((file) => file.kind === "image");
    const canUseSource = Boolean(source && selectedImageModel?.capabilities?.image_to_image === true);
    setAttachments([]);
    try {
      const refinement = await api.optimizeImagePrompt({
        prompt,
        model_id: imageModelId,
        optimizer_model_id: selectedModel?.id ?? null,
        aspect_ratio: imageAspectRatio,
      });
      setImageTask({ active: true, phase: "generating", refinedPrompt: refinement.prompt });
      const result = await api.generateImage({
        prompt: refinement.prompt,
        negative_prompt: refinement.negative_prompt,
        optimize: false,
        mode: canUseSource ? "img2img" : "txt2img",
        model_id: imageModelId,
        source_file_id: canUseSource ? source!.id : null,
        aspect_ratio: imageAspectRatio === "auto" ? refinement.aspect_ratio : imageAspectRatio,
      });
      await api.attachImageToConversation(convId, result.file_id, prompt, {
        prompt_used: refinement.prompt,
        negative_prompt_used: refinement.negative_prompt,
        model_name: result.model.name,
        parent_user_message_id: retryUserMessageId,
        aspect_ratio: result.aspect_ratio,
        width: result.width,
        height: result.height,
      });
      setMessages(await api.getMessages(convId));
      refreshConversations();
    } catch (e) {
      await persistFailure(convId, prompt, e instanceof Error ? e : new Error("Image generation failed"), "image_generation", 0, retryUserMessageId);
      setAttachments((current) => current.length ? current : attachments);
    } finally {
      setImageTask({ active: false, phase: "optimizing", refinedPrompt: "" });
      setConversationRunning(convId, false);
    }
  }, [attachments, conversation, imageModelId, imageModels.length, imageTask.active, imageAspectRatio, refreshConversations, selectedImageModel, selectedModel, setActiveId, setConversationRunning, persistFailure]);

  const submitPrompt = useCallback(async (text: string) => {
    const prompt = text.trim();
    if (!prompt || routingPromptRef.current) return;
    const pendingAssistantId = `tmp-routing-assistant-${Date.now()}`;
    const optimisticUser: Message = {
      id: `tmp-routing-user-${Date.now()}`,
      conversation_id: conversation?.id ?? "pending",
      parent_id: null,
      role: "user",
      model_id: null,
      status: "completed",
      error: null,
      usage: null,
      created_at: new Date().toISOString(),
      blocks: optimisticUserBlocks(prompt, attachments),
    };
    routingPromptRef.current = true;
    setRoutingPrompt(true);
    setMessages((prev) => [...prev, optimisticUser]);
    setStream({
      active: true, reasoning: "", text: "", assistantMessageId: pendingAssistantId,
      tools: [], search: { active: false, query: "", sourceCount: 0 }, startedAt: null,
    });
    const routingDone = () => {
      routingPromptRef.current = false;
      setRoutingPrompt(false);
    };
    if (composerImageMode) {
      routingDone();
      await createImageFromComposer(prompt, undefined, true);
      return;
    }
    if (mode === "work") {
      routingDone();
      await sendWork(prompt, true);
      return;
    }
    const mightConcernImage = /(?:图|画|照片|海报|插画|头像|壁纸|角色|logo|生成一张|创建一张|画一|image|picture|photo|illustration|poster|wallpaper|draw|paint)/i.test(prompt);
    if (uiSettings?.features.image_generation !== false && imageModels.length > 0 && mightConcernImage) {
      try {
        const intent = await api.classifyImageIntent(prompt, selectedModel?.id ?? null);
        if (intent.image_request) {
          routingDone();
          await createImageFromComposer(prompt, undefined, true);
          return;
        }
      } catch {
        // Intent routing must never prevent a normal chat message.
      }
    }
    routingDone();
    await send(prompt, { skipOptimistic: true, pendingAssistantId });
  }, [attachments, composerImageMode, conversation?.id, createImageFromComposer, imageModels.length, mode, selectedModel?.id, send, sendWork, uiSettings?.features.image_generation]);

  const regenerate = useCallback(() => {
    const lastUser = [...messages].reverse().find((m) => m.role === "user");
    const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant");
    if (!lastUser || stream.active) return;
    setMessages((prev) => {
      const idx = prev.findIndex((m) => m.id === lastUser.id);
      return prev.slice(0, idx + 1);
    });
    const wasImageGeneration = lastAssistant?.error?.kind === "image_generation"
      || lastAssistant?.blocks.some((block) => block.type === "image" && block.data.generated === true);
    if (wasImageGeneration) {
      const prompt = String(lastUser.blocks.find((block) => block.type === "text" || block.type === "markdown")?.data.text ?? "");
      void createImageFromComposer(prompt, lastUser.id);
    } else {
      void send("", { regenerateFrom: lastUser.id });
    }
  }, [messages, stream.active, send, createImageFromComposer]);

  const editLastPrompt = useCallback(async (message: Message, text: string) => {
    if (stream.active || !conversation) return;
    setRunError(null);
    try {
      await api.updateMessageText(conversation.id, message.id, text);
      const idx = messages.findIndex((item) => item.id === message.id);
      setMessages((prev) => prev.slice(0, idx + 1).map((item) => item.id === message.id
        ? { ...item, blocks: item.blocks.map((block) => block.type === "text" || block.type === "markdown" ? { ...block, data: { ...block.data, text } } : block) }
        : item));
      await send("", { regenerateFrom: message.id });
    } catch (e) {
      setRunError(e instanceof Error ? e.message : "Failed to edit message");
    }
  }, [conversation, messages, send, stream.active]);

  useEffect(() => {
    if (!conversation?.id || stream.active || imageTask.active) return;
    api.getMessageBranches(conversation.id).then(setMessageBranches).catch(() => undefined);
  }, [conversation?.id, imageTask.active, messages.length, stream.active]);

  const switchMessageBranch = useCallback(async (messageId: string) => {
    if (!conversation || stream.active) return;
    await api.activateMessageBranch(conversation.id, messageId);
    const [nextMessages, nextBranches] = await Promise.all([
      api.getMessages(conversation.id), api.getMessageBranches(conversation.id),
    ]);
    setMessages(nextMessages);
    setMessageBranches(nextBranches);
  }, [conversation, stream.active]);





  const lastAssistantId = [...messages].reverse().find((m) => m.role === "assistant")?.id;
  const lastUserId = [...messages].reverse().find((m) => m.role === "user")?.id;
  const streamingMessageId = stream.assistantMessageId;

  if (loadError) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3 text-[var(--muted)]">
        <AlertCircle size={28} />
        <div>{loadError}</div>
        <Button onClick={() => router.push("/")}>{t("newChatAfterError", "Start a new chat")}</Button>
      </div>
    );
  }

  const showHero = !loading && !conversation && messages.length === 0;
  const featureFlags = uiSettings?.features;
  const suggestions = locale === "zh-CN"
    ? ["帮我总结一份文档", "制定一个详细计划", "分析数据并生成图表", "创建一张图片"]
    : ["Summarize a document", "Make a detailed plan", "Analyze data and create a chart", "Create an image"];
  const composerControls = (
    <>
      <ModelSelector models={models} selectedId={selectedModel?.id ?? null} onSelect={setSelectedModelId} />
      {supportsReasoning && <ReasoningSelector value={reasoningEffort} onChange={setReasoningEffort} />}
    </>
  );
  const busy = routingPrompt || stream.active || imageTask.active || ["working", "planning", "waiting_approval"].includes(work.status);
  const activeWork = Boolean(work.runId) && ["working", "planning", "waiting_approval"].includes(work.status);

  return (
    <div className="relative flex h-full flex-col">
      {conversation && uiSettings?.public_sharing_enabled !== false && (
        <div className="absolute right-3 top-2 z-20 flex items-center gap-2">
          {shareMsg && <span className="rounded-lg bg-[var(--surface)] px-2 py-1 text-xs text-[var(--muted)]">{shareMsg}</span>}
          <button
            type="button"
            onClick={shareConversation}
            title={t("share", "Share conversation")}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-[var(--muted)] hover:bg-[var(--surface)] hover:text-[var(--fg)]"
          >
            <Share2 size={16} />
          </button>
        </div>
      )}
      <div ref={scrollRef} onScroll={onScroll} className="flex-1 overflow-y-auto">
        {showHero ? (
          <div className="hero-enter relative flex h-full flex-col items-center justify-center px-4 pb-16">
            <div className="absolute left-1/2 top-5 -translate-x-1/2">
              <NewChatModeSwitch mode={mode} onMode={setMode} chatAvailable={featureFlags?.chat !== false} workAvailable={featureFlags?.work !== false} />
            </div>
            <h1 className="mb-8 text-center text-[30px] font-semibold tracking-[-0.035em]">
              {mode === "work"
                ? (locale === "zh-CN" ? "你想完成什么工作？" : "What would you like to work on?")
                : t("greeting", "How can I help you today?")}
            </h1>
            <div className="w-full max-w-3xl">
              {runError && <ErrorBanner message={runError} />}
              <Composer
                onSend={submitPrompt}
                streaming={busy}
                onStop={mode === "work" ? cancelWork : stop}
                autoFocus
                placeholder={composerImageMode
                  ? (locale === "zh-CN" ? "描述你想创建的图片" : "Describe the image you want")
                  : mode === "work" ? (locale === "zh-CN" ? "描述目标，或添加文件和上下文" : "Describe a goal, or add files and context")
                  : t("message", `Message ${branding?.product_name ?? ""}`)}
                attachments={attachments}
                uploading={uploading}
                onFiles={featureFlags?.file_uploads === false ? undefined : handleFiles}
                onRemoveAttachment={(id) => setAttachments((prev) => prev.filter((a) => a.id !== id))}
                canImages={canImages}
                webSearch={webSearch}
                onToggleWebSearch={() => setWebSearch(!webSearch)}
                searchAvailable={featureFlags?.web_search !== false && uiSettings?.search_configured === true && selectedModel?.effective_capabilities?.tool_calling === true}
                onDeepResearch={featureFlags?.deep_research === false ? undefined : () => setResearchOpen(true)}
                imageAvailable={featureFlags?.image_generation !== false && imageModels.length > 0}
                onCreateImage={() => setComposerImageMode(true)}
                sttAvailable={featureFlags?.audio !== false && uiSettings?.stt_configured === true}
                controls={composerControls}
                imageCreation={composerImageMode}
                onCancelImageCreation={() => setComposerImageMode(false)}
                imageAspectRatio={imageAspectRatio}
                onImageAspectRatioChange={setImageAspectRatio}
                workPlugins={mode === "work" && featureFlags?.plugins !== false ? workPlugins : []}
                selectedPluginIds={selectedPluginIds}
                onTogglePlugin={(id) => setSelectedPluginIds((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id])}
              />
              {mode === "work" && (
                <p className="mt-3 text-center text-xs text-[var(--muted)]">
                  {locale === "zh-CN" ? "工作模式会先规划任务，使用可用工具，并生成可继续修改的成果。" : "Work plans the task, uses available tools, and produces a result you can refine."}
                </p>
              )}
              <div className="mt-3 grid grid-cols-2 gap-2 sm:flex sm:flex-wrap sm:justify-center">
                {suggestions.map((suggestion) => (
                  <button
                    key={suggestion}
                    type="button"
                    onClick={() => suggestion.includes("图片") || suggestion === "Create an image"
                      ? setComposerImageMode(true)
                      : mode === "work" ? sendWork(suggestion) : send(suggestion)}
                    className="rounded-full border border-[var(--border)] bg-[var(--bg)] px-3.5 py-2 text-xs text-[var(--muted)] hover:-translate-y-0.5 hover:border-[var(--muted)] hover:text-[var(--fg)] hover:shadow-sm"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
              <p className="mt-2 text-center text-xs text-[var(--muted)]">
                {t("disclaimer", "Responses are generated by configured models and may be inaccurate.")}
              </p>
            </div>
          </div>
        ) : (
          <div className="mx-auto w-full max-w-3xl px-4 pb-6 pt-14 md:pt-8">
            {loading && (
              <div className="flex justify-center py-10">
                <Spinner className="h-6 w-6 text-[var(--muted)]" />
              </div>
            )}
            {!loading &&
              messages.filter((m) => !(stream.active && m.id === streamingMessageId)).map((m) => {
                const branch = m.role === "assistant"
                  ? messageBranches.find((item) => item.alternatives.some((alt) => alt.message_id === m.id))
                  : undefined;
                const branchIndex = branch?.alternatives.findIndex((alt) => alt.message_id === m.id) ?? -1;
                return (
                <MessageView
                  key={m.id}
                  message={m}
                  modelName={m.role === "assistant" ? selectedModel?.display_name : undefined}
                  isLastAssistant={m.id === lastAssistantId}
                  isLastUser={m.id === lastUserId}
                  onRegenerate={regenerate}
                  onEditUser={m.role === "user" && m.id === lastUserId ? (text) => editLastPrompt(m, text) : undefined}
                  busy={stream.active}
                  branchPosition={branch ? branchIndex + 1 : undefined}
                  branchCount={branch?.alternatives.length}
                  onPreviousBranch={branch && branchIndex > 0 ? () => void switchMessageBranch(branch.alternatives[branchIndex - 1].message_id) : undefined}
                  onNextBranch={branch && branchIndex < branch.alternatives.length - 1 ? () => void switchMessageBranch(branch.alternatives[branchIndex + 1].message_id) : undefined}
                />
              )})}
            {researchProgress && researchProgress.phase !== "done" && (
              <ResearchProgressCard progress={researchProgress} />
            )}
            {imageTask.active && <ImageGenerationProgress phase={imageTask.phase} refinedPrompt={imageTask.refinedPrompt} />}
            {stream.active && !researchProgress && stream.search.active && (
              <div className="my-2 flex items-center gap-2 rounded-xl border border-[var(--border)] bg-[var(--surface)] px-3.5 py-2.5 text-sm text-[var(--muted)]">
                <Spinner className="h-3.5 w-3.5" />
                {t("searchingWeb", "Searching the web for")} “{stream.search.query}”…
              </div>
            )}
            {stream.active && !researchProgress && !stream.search.active && stream.search.sourceCount > 0 && (
              <div className="my-2 rounded-xl border border-[var(--border)] bg-[var(--surface)] px-3.5 py-2.5 text-sm text-[var(--muted)]">
                {t("sourcesRead", "Read web sources")}: {stream.search.sourceCount}
              </div>
            )}
            {stream.active && streamingMessageId && (
              <MessageView
                message={{
                  id: streamingMessageId,
                  conversation_id: conversation?.id ?? "",
                  parent_id: null,
                  role: "assistant",
                  model_id: selectedModel?.id ?? null,
                  status: "streaming",
                  error: null,
                  usage: null,
                  created_at: new Date().toISOString(),
                  blocks: [],
                }}
                streaming
                streamingReasoning={stream.reasoning}
                streamingText={stream.text}
                streamingTools={stream.tools}
                elapsedMs={elapsedMs}
              />
            )}
            {work.runId && <WorkTimeline work={work} />}
            {work.approval && (
              <ApprovalCard approval={work.approval} onDecide={decideApproval} />
            )}
            {pendingApproval && !work.approval && (
              <ApprovalCard approval={pendingApproval} onDecide={decideApproval} />
            )}
          </div>
        )}
      </div>
      {!showHero && (
        <div className="mx-auto w-full max-w-3xl px-4 pb-4">
          {activeWork ? (
            <div className="composer-shell mb-2 flex items-end gap-2 rounded-[28px] border border-[var(--border)] bg-[var(--composer)] p-2 shadow-sm">
              <input
                value={steerText}
                onChange={(e) => setSteerText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    steerWork();
                  }
                }}
                placeholder={t("steerPlaceholder", "Add an instruction while it works…")}
                className="min-h-11 flex-1 bg-transparent px-3 py-2 text-sm outline-none"
              />
              <button type="button" onClick={steerWork} disabled={!steerText.trim()} className="h-10 rounded-full bg-[var(--surface)] px-4 text-sm font-medium disabled:opacity-40">{t("send", "Send")}</button>
              <button type="button" onClick={cancelWork} className="h-10 rounded-full bg-red-600 px-4 text-sm font-medium text-white">{t("cancelRun", "Cancel run")}</button>
            </div>
          ) : (<>
          {runError && <ErrorBanner message={runError} />}
          <Composer
            onSend={submitPrompt}
            streaming={busy}
            onStop={mode === "work" ? cancelWork : stop}
            placeholder={composerImageMode
              ? (locale === "zh-CN" ? "描述你想创建的图片" : "Describe the image you want")
              : t("message", `Message ${branding?.product_name ?? ""}`)}
            attachments={attachments}
            uploading={uploading}
            onFiles={featureFlags?.file_uploads === false ? undefined : handleFiles}
            onRemoveAttachment={(id) => setAttachments((prev) => prev.filter((a) => a.id !== id))}
            canImages={canImages}
            webSearch={webSearch}
            onToggleWebSearch={() => setWebSearch(!webSearch)}
            searchAvailable={featureFlags?.web_search !== false && uiSettings?.search_configured === true && selectedModel?.effective_capabilities?.tool_calling === true}
            onDeepResearch={featureFlags?.deep_research === false ? undefined : () => setResearchOpen(true)}
            imageAvailable={featureFlags?.image_generation !== false && imageModels.length > 0}
            onCreateImage={() => setComposerImageMode(true)}
            sttAvailable={featureFlags?.audio !== false && uiSettings?.stt_configured === true}
            controls={composerControls}
            imageCreation={composerImageMode}
            onCancelImageCreation={() => setComposerImageMode(false)}
            imageAspectRatio={imageAspectRatio}
            onImageAspectRatioChange={setImageAspectRatio}
            workPlugins={mode === "work" && featureFlags?.plugins !== false ? workPlugins : []}
            selectedPluginIds={selectedPluginIds}
            onTogglePlugin={(id) => setSelectedPluginIds((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id])}
          />
          </>)}
          <p className="mt-2 text-center text-xs text-[var(--muted)]">
            {t("disclaimer", "Responses may be inaccurate. Verify important information.")}
          </p>
        </div>
      )}
      {researchOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={() => setResearchOpen(false)}>
          <div className="w-full max-w-lg rounded-2xl bg-[var(--bg)] p-5" onClick={(e) => e.stopPropagation()}>
            <h2 className="mb-1 text-base font-semibold">{t("deepResearch", "Deep research")}</h2>
            <p className="mb-3 text-xs text-[var(--muted)]">
              {t("researchDescription", "Plans sub-questions, searches and reads multiple sources, cross-checks, then writes a cited report.")}
            </p>
            <textarea
              autoFocus
              value={researchGoal}
              onChange={(e) => setResearchGoal(e.target.value)}
              rows={3}
              placeholder={t("researchPlaceholder", "What should be researched?")}
              className="w-full rounded-xl border border-[var(--border)] bg-transparent px-3 py-2 text-sm outline-none focus:border-accent"
            />

            <label className="mt-3 flex items-center justify-between gap-3 text-xs text-[var(--muted)]">
              <span>
                {locale === "zh-CN" ? "画面比例" : "Aspect ratio"}
                <span className="ml-1 opacity-70">
                  {locale === "zh-CN" ? "（自动会由大模型根据构图判断）" : "(Auto lets the language model choose for the composition)"}
                </span>
              </span>
              <select
                aria-label={locale === "zh-CN" ? "画面比例" : "Aspect ratio"}
                value={imageAspectRatio}
                onChange={(event) => setImageAspectRatio(event.target.value as ImageAspectRatio | "auto")}
                className="rounded-lg border border-[var(--border)] bg-transparent px-2.5 py-1.5 text-xs text-[var(--fg)] outline-none"
              >
                {IMAGE_ASPECT_RATIOS.map((ratio) => (
                  <option key={ratio} value={ratio}>{ratio === "auto" ? (locale === "zh-CN" ? "自动" : "Auto") : ratio}</option>
                ))}
              </select>
            </label>
            <div className="mt-3 flex justify-end gap-2">
              <Button onClick={() => setResearchOpen(false)}>{t("cancel", "Cancel")}</Button>
              <Button variant="primary" disabled={!researchGoal.trim()} onClick={startResearch}>
                {t("startResearch", "Start research")}
              </Button>
            </div>
          </div>
        </div>
      )}
      {imageOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={() => !imageBusy && setImageOpen(false)}>
          <div className="max-h-[92vh] w-full max-w-lg overflow-y-auto rounded-2xl bg-[var(--bg)] p-5" onClick={(e) => e.stopPropagation()}>
            <h2 className="mb-1 text-base font-semibold">{t("createImage", "Create image")}</h2>
            <p className="mb-3 text-xs text-[var(--muted)]">
              Text-to-image, image-to-image, and masked inpainting. txt2img prompts are optimized by the chat model.
            </p>

            <div className="mb-3 flex flex-wrap items-center gap-2">
              {(["txt2img", "img2img", "inpaint"] as const).map((m) => {
                const cap = selectedImageModel?.capabilities ?? {};
                const supported = m === "txt2img"
                  ? cap.text_to_image !== false
                  : m === "img2img" ? cap.image_to_image === true : cap.inpainting === true;
                return (
                  <button
                    key={m}
                    type="button"
                    disabled={!supported}
                    onClick={() => setImageMode(m)}
                    className={cn(
                      "rounded-full px-3 py-1.5 text-xs font-medium capitalize",
                      imageMode === m ? "bg-[var(--fg)] text-[var(--bg)]" : "bg-[var(--surface)] text-[var(--muted)] hover:bg-[var(--border)]",
                      !supported && "opacity-40",
                    )}
                    title={supported ? m : t("unsupported", "Not supported by the selected model")}
                  >
                    {m === "txt2img" ? t("textToImage", "Text → Image") : m === "img2img" ? t("imageToImage", "Image → Image") : t("inpaint", "Inpaint")}
                  </button>
                );
              })}
              <select
                value={imageModelId ?? ""}
                onChange={(e) => setImageModelId(e.target.value || null)}
                className="ml-auto rounded-lg border border-[var(--border)] bg-transparent px-2 py-1.5 text-xs"
              >
                <option value="">{t("defaultImageModel", "Default image model")}</option>
                {imageModels.map((m) => (
                  <option key={m.id} value={m.id}>{m.name}</option>
                ))}
              </select>
            </div>

            <textarea
              autoFocus
              value={imagePrompt}
              onChange={(e) => setImagePrompt(e.target.value)}
              rows={3}
              placeholder={imageMode === "txt2img" ? t("imagePrompt", "Describe the image to create…") : t("editPrompt", "Describe the desired result…")}
              className="w-full rounded-xl border border-[var(--border)] bg-transparent px-3 py-2 text-sm outline-none focus:border-accent"
            />

            {imageMode !== "txt2img" && (
              <div className="mt-3">
                <input
                  ref={sourceInputRef}
                  type="file"
                  accept="image/*"
                  className="hidden"
                  onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadSourceImage(f); e.target.value = ""; }}
                />
                {!sourceFile ? (
                  <button
                    type="button"
                    onClick={() => sourceInputRef.current?.click()}
                    className="flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-[var(--border)] px-3 py-6 text-sm text-[var(--muted)] hover:bg-[var(--surface)]"
                  >
                    {t("chooseSource", "Choose source image")}
                  </button>
                ) : (
                  <div className="flex items-start gap-3">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={sourceFile.url} alt="source" className="h-24 w-24 rounded-xl border border-[var(--border)] object-cover" />
                    <div className="flex flex-col gap-1 text-xs text-[var(--muted)]">
                      <span>{t("sourceSelected", "Source image selected")}</span>
                      <button type="button" className="text-left text-accent hover:underline" onClick={() => sourceInputRef.current?.click()}>
                        {t("change", "Change")}
                      </button>
                    </div>
                  </div>
                )}
                {imageMode === "img2img" && (
                  <label className="mt-3 flex items-center gap-2 text-xs text-[var(--muted)]">
                    {t("strength", "Strength")}
                    <input type="range" min={0.1} max={0.95} step={0.05} value={strength} onChange={(e) => setStrength(Number(e.target.value))} />
                    <span>{strength.toFixed(2)}</span>
                  </label>
                )}
                {imageMode === "inpaint" && sourceFile && (
                  <div className="mt-3">
                    <MaskEditor imageUrl={sourceFile.url} onMaskChange={setMaskBlob} />
                  </div>
                )}
              </div>
            )}

            {imageBusy && (
              <div className="mt-3 flex flex-col items-center gap-3 rounded-xl border border-[var(--border)] px-4 py-8">
                <div className="flex items-center gap-1.5">
                  <span className="h-2 w-2 animate-bounce rounded-full bg-accent" style={{ animationDelay: "0ms" }} />
                  <span className="h-2 w-2 animate-bounce rounded-full bg-accent" style={{ animationDelay: "150ms" }} />
                  <span className="h-2 w-2 animate-bounce rounded-full bg-accent" style={{ animationDelay: "300ms" }} />
                </div>
                <div className="text-sm text-[var(--muted)]">
                  {imagePhase === "optimizing"
                    ? t("optimizingPrompt", "Optimizing your prompt with the chat model…")
                    : t("generatingImage", "Generating image on the accelerator…")}
                </div>
              </div>
            )}

            {imageResult && !imageBusy && (
              <div className="mt-3 overflow-hidden rounded-xl border border-[var(--border)]">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <AuthImage src={`/api/v1/files/${imageResult.file_id}/download`} alt="preview" className="w-full" />
                <div className="space-y-1 px-3 py-2 text-xs text-[var(--muted)]">
                  <div>
                    {imageResult.model.name} · {imageResult.aspect_ratio} · {imageResult.width}×{imageResult.height} · {(imageResult.duration_ms / 1000).toFixed(1)}s · {imageResult.mode}
                  </div>
                  {imageResult.optimized && (
                    <div className="rounded-lg bg-[var(--surface)] px-2 py-1.5">
                      <span className="font-medium text-accent">{t("refinedPrompt", "Prompt refined by chat model:")}</span>{" "}
                      <span className="line-clamp-3">{imageResult.prompt_used}</span>
                    </div>
                  )}
                </div>
              </div>
            )}
            <div className="mt-3 flex justify-end gap-2">
              <Button onClick={() => { setImageOpen(false); setImageResult(null); }} disabled={imageBusy}>{t("close", "Close")}</Button>
              {imageResult && !imageBusy && (
                <Button onClick={createImage} disabled={!imagePrompt.trim()}>{t("regenerate", "Regenerate")}</Button>
              )}
              <Button variant="primary" disabled={!imagePrompt.trim() || imageBusy} onClick={createImage}>
                {imageBusy ? <Spinner /> : imageResult ? t("generateAgain", "Generate again") : t("generate", "Generate")}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ResearchProgressCard({ progress }: { progress: ResearchProgress }) {
  const { t } = useApp();
  const steps: { key: ResearchProgress["phase"]; label: string }[] = [
    { key: "planning", label: t("planning", "Planning") },
    { key: "searching", label: t("searching", "Searching") },
    { key: "reading", label: t("reading", "Reading") },
    { key: "synthesizing", label: t("writing", "Writing") },
  ];
  const activeIdx = steps.findIndex((s) => s.key === progress.phase);
  return (
    <div className="my-3 rounded-xl border border-[var(--border)] p-4">
      <div className="mb-3 flex items-center gap-2 text-sm font-medium">
        <Spinner className="h-3.5 w-3.5 text-[var(--muted)]" />
        {t("researchRunning", "Deep research in progress")}
      </div>
      <div className="mb-3 flex flex-wrap gap-1.5">
        {steps.map((s, i) => (
          <span
            key={s.key}
            className={
              i < activeIdx
                ? "rounded-full bg-accent/15 px-2.5 py-1 text-xs text-accent"
                : i === activeIdx
                  ? "rounded-full bg-accent px-2.5 py-1 text-xs font-medium text-white"
                  : "rounded-full bg-[var(--surface)] px-2.5 py-1 text-xs text-[var(--muted)]"
            }
          >
            {s.label}
          </span>
        ))}
      </div>
      {progress.questions.length > 0 && progress.phase === "planning" || progress.phase === "searching" ? (
        <ul className="mb-2 space-y-0.5 text-xs text-[var(--muted)]">
          {progress.questions.slice(0, 4).map((q) => (
            <li key={q}>· {q}</li>
          ))}
        </ul>
      ) : null}
      {progress.currentQuery && progress.phase === "searching" && (
        <div className="text-xs text-[var(--muted)]">Searching: {progress.currentQuery}</div>
      )}
      {progress.readingUrl && progress.phase === "reading" && (
        <div className="truncate text-xs text-[var(--muted)]">Reading: {progress.readingUrl}</div>
      )}
      {progress.phase === "synthesizing" && (
        <div className="text-xs text-[var(--muted)]">Synthesizing from {progress.sourceCount} sources…</div>
      )}
    </div>
  );
}

function NewChatModeSwitch({
  mode,
  onMode,
  chatAvailable,
  workAvailable,
}: {
  mode: "chat" | "work" | "study";
  onMode: (mode: "chat" | "work" | "study") => void;
  chatAvailable: boolean;
  workAvailable: boolean;
}) {
  const { t } = useApp();
  const modes = [
    { id: "chat" as const, label: t("chat", "Chat"), icon: <MessageCircle size={15} /> },
    { id: "work" as const, label: t("work", "Work"), icon: <WandSparkles size={15} /> },
  ].filter((item) => item.id === "chat" ? chatAvailable : workAvailable);
  return (
    <div className="flex items-center rounded-full border border-[var(--border)] bg-[var(--surface)] p-1 shadow-sm">
      {modes.map((item) => (
        <button
          key={item.id}
          type="button"
          onClick={() => onMode(item.id)}
          className={cn(
            "flex items-center gap-1.5 rounded-full px-4 py-1.5 text-sm font-medium text-[var(--muted)] transition-all",
            mode === item.id && "bg-[var(--bg)] text-[var(--fg)] shadow-sm",
          )}
        >
          {item.icon}{item.label}
        </button>
      ))}
    </div>
  );
}

function ImageGenerationProgress({ phase, refinedPrompt }: { phase: "optimizing" | "generating"; refinedPrompt: string }) {
  const { locale } = useApp();
  return (
    <div className="my-5 flex gap-4">
      <div className="image-waiting relative h-24 w-24 shrink-0 overflow-hidden rounded-2xl bg-[var(--surface)]">
        <ImageIcon size={24} className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 text-[var(--muted)]" />
      </div>
      <div className="min-w-0 self-center">
        <div className="flex items-center gap-2 text-sm font-medium">
          <ThinkingDots className="text-violet-500" />
          {phase === "optimizing"
            ? (locale === "zh-CN" ? "正在理解并润色提示词…" : "Refining your prompt…")
            : (locale === "zh-CN" ? "正在生成图片…" : "Creating your image…")}
        </div>
        {refinedPrompt && (
          <p className="mt-2 line-clamp-3 text-xs leading-5 text-[var(--muted)]">
            {locale === "zh-CN" ? "已润色：" : "Refined: "}{refinedPrompt}
          </p>
        )}
      </div>
    </div>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="mb-2 flex items-start gap-2 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-500">
      <AlertCircle size={16} className="mt-0.5 shrink-0" />
      <span>{message}</span>
    </div>
  );
}

function ApprovalCard({
  approval,
  onDecide,
}: {
  approval: PendingApproval;
  onDecide: (approval: PendingApproval, decision: "allow" | "deny", rule: "once" | "always") => void;
}) {
  const { locale } = useApp();
  return (
    <div className="mb-2 rounded-xl border border-amber-500/40 bg-amber-500/10 px-4 py-3">
      <div className="text-sm font-medium">
        {locale === "zh-CN" ? "智能体想要使用" : "Agent wants to use"} <span className="font-mono">{approval.name}</span>
      </div>
      <div className="mt-0.5 text-xs text-[var(--muted)]">
        {locale === "zh-CN" ? "风险等级" : "Risk level"}: {approval.risk || (locale === "zh-CN" ? "未知" : "unknown")} · {locale === "zh-CN" ? "需要你的批准" : "requires your approval"}
      </div>
      <div className="mt-2 flex gap-2">
        <Button variant="primary" onClick={() => onDecide(approval, "allow", "once")}>{locale === "zh-CN" ? "允许一次" : "Allow once"}</Button>
        <Button onClick={() => onDecide(approval, "allow", "always")}>{locale === "zh-CN" ? "始终允许" : "Always allow"}</Button>
        <Button variant="danger" onClick={() => onDecide(approval, "deny", "once")}>{locale === "zh-CN" ? "拒绝" : "Deny"}</Button>
      </div>
    </div>
  );
}

function WorkTimeline({ work }: { work: WorkState }) {
  const { locale } = useApp();
  const statusLabel: Record<string, string> = {
    planning: locale === "zh-CN" ? "规划中" : "Planning",
    working: locale === "zh-CN" ? "执行中" : "Working",
    waiting_approval: locale === "zh-CN" ? "等待批准" : "Waiting for approval",
    completed: locale === "zh-CN" ? "已完成" : "Completed",
    failed: locale === "zh-CN" ? "失败" : "Failed",
    cancelled: locale === "zh-CN" ? "已取消" : "Cancelled",
  };
  const active = !["completed", "failed", "cancelled"].includes(work.status);
  return (
    <div className="my-3 rounded-xl border border-[var(--border)] p-4">
      <div className="mb-2 flex items-center gap-2 text-sm font-medium">
        {active ? (
          <ThinkingDots className="text-accent" />
        ) : work.status === "completed" ? (
          <Check size={15} className="text-accent" />
        ) : (
          <AlertCircle size={15} className="text-red-500" />
        )}
        {locale === "zh-CN" ? "工作任务" : "Work run"}: {statusLabel[work.status] ?? work.status}
      </div>

      {work.plan.length > 0 && (
        <div className="mb-2 rounded-lg bg-[var(--surface)] px-3 py-2">
          <div className="mb-1 text-xs font-semibold text-[var(--muted)]">{locale === "zh-CN" ? "计划" : "Plan"}</div>
          <ol className="list-decimal space-y-0.5 pl-4 text-xs text-[var(--muted)]">
            {work.plan.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ol>
        </div>
      )}

      {work.steps.length > 0 && (
        <ol className="space-y-1 border-l border-[var(--border)] pl-3 text-xs text-[var(--muted)]">
          {work.steps.map((s, i) => (
            <li key={i}>
              <span className="font-medium text-[var(--fg)]">{s.label}</span>
              {s.detail ? ` · ${s.detail}` : ""}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
