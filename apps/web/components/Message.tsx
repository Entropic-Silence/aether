"use client";

import { useEffect, useState } from "react";
import { Check, ChevronDown, ChevronLeft, ChevronRight, Copy, Download, ExternalLink, Eye, File as FileIcon, FileArchive, FileAudio, FileCode, FileSpreadsheet, FileText, FileVideo, Lightbulb, Pencil, Presentation, RefreshCw, Save, Terminal, ThumbsDown, ThumbsUp } from "lucide-react";
import type { Message } from "@/lib/types";
import { api, getToken, phase7Api } from "@/lib/api";
import { useApp } from "@/lib/hooks";
import { AuthImage } from "./AuthImage";
import { Markdown } from "./Markdown";
import { IconBtn, Spinner, cn } from "./ui";

function fmtSize(bytes: number): string {
  if (!bytes) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function fileExtension(name: string): string {
  return (name.includes(".") ? name.split(".").pop() || "FILE" : "FILE").slice(0, 8).toUpperCase();
}

function MessageFileIcon({ name, mime = "" }: { name: string; mime?: string }) {
  const ext = fileExtension(name).toLowerCase();
  if (["xls", "xlsx", "csv", "ods"].includes(ext)) return <FileSpreadsheet size={22} className="text-emerald-600" />;
  if (["ppt", "pptx", "key"].includes(ext)) return <Presentation size={22} className="text-orange-500" />;
  if (["zip", "rar", "7z", "tar", "gz"].includes(ext)) return <FileArchive size={22} className="text-amber-600" />;
  if (mime.startsWith("audio/") || ["mp3", "wav", "m4a", "flac"].includes(ext)) return <FileAudio size={22} className="text-violet-500" />;
  if (mime.startsWith("video/") || ["mp4", "mov", "mkv", "webm"].includes(ext)) return <FileVideo size={22} className="text-fuchsia-500" />;
  if (["js", "ts", "tsx", "jsx", "py", "json", "html", "css", "md"].includes(ext)) return <FileCode size={22} className="text-sky-600" />;
  if (["pdf", "doc", "docx", "txt", "rtf"].includes(ext)) return <FileText size={22} className="text-red-500" />;
  return <FileIcon size={22} className="text-[var(--muted)]" />;
}

interface PreviewTarget { fileId: string; name: string; mime: string }

async function downloadAuthenticated(fileId: string, name: string): Promise<void> {
  const token = getToken();
  const response = await fetch(api.fileDownloadUrl(fileId), {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) throw new Error("Download failed");
  const url = URL.createObjectURL(await response.blob());
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function FilePreviewModal({ file, onClose }: { file: PreviewTarget; onClose: () => void }) {
  const [preview, setPreview] = useState<{ mode: "pdf" | "svg" | "text"; text: string } | null>(null);
  const [blobUrl, setBlobUrl] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    let cancelled = false;
    let createdUrl = "";
    (async () => {
      try {
        const info = await api.filePreview(file.fileId);
        if (cancelled) return;
        setPreview(info);
        if (info.mode === "pdf" || info.mode === "svg") {
          const headers: Record<string, string> = {};
          const token = getToken();
          if (token) headers.Authorization = `Bearer ${token}`;
          const response = await fetch(api.fileDownloadUrl(file.fileId), { headers });
          if (!response.ok) throw new Error("Preview download failed");
          createdUrl = URL.createObjectURL(await response.blob());
          if (!cancelled) setBlobUrl(createdUrl);
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Preview failed");
      }
    })();
    return () => { cancelled = true; if (createdUrl) URL.revokeObjectURL(createdUrl); };
  }, [file.fileId]);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onMouseDown={onClose}>
      <div className="flex h-[82vh] w-full max-w-5xl flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg)] shadow-2xl" onMouseDown={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-[var(--border)] px-4 py-3">
          <div className="min-w-0 truncate text-sm font-semibold">{file.name}</div>
          <button type="button" onClick={onClose} className="rounded-lg px-3 py-1.5 text-sm hover:bg-[var(--surface)]">Close</button>
        </div>
        <div className="min-h-0 flex-1 overflow-auto p-4">
          {error && <div className="text-sm text-red-500">{error}</div>}
          {!preview && !error && <div className="flex h-full items-center justify-center"><Spinner /></div>}
          {preview?.mode === "pdf" && blobUrl && <iframe title={file.name} src={blobUrl} className="h-full min-h-[65vh] w-full rounded-lg border border-[var(--border)]" />}
          {preview?.mode === "svg" && blobUrl && <img src={blobUrl} alt={file.name} className="mx-auto max-h-full max-w-full rounded-lg" />}
          {preview?.mode === "text" && (preview.text
            ? <pre className="whitespace-pre-wrap break-words text-sm leading-6">{preview.text}</pre>
            : <div className="text-sm text-[var(--muted)]">No browser preview is available for this file.</div>)}
        </div>
      </div>
    </div>
  );
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms} ms`;
  const seconds = ms / 1000;
  return seconds < 60 ? `${seconds.toFixed(seconds < 10 ? 1 : 0)} s` : `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
}

const TOOL_LABELS: Record<string, string> = {
  run_python: "Python",
};

export function ToolCard({
  name,
  args,
  status,
  result,
}: {
  name: string;
  args?: Record<string, unknown>;
  status: "running" | "done" | "failed";
  result?: Record<string, unknown>;
}) {
  const { locale } = useApp();
  const [open, setOpen] = useState(false);
  const label = TOOL_LABELS[name] ?? name;
  const code = typeof args?.code === "string" ? args.code : undefined;
  const stdout = typeof result?.stdout === "string" ? result.stdout : "";
  const stderr = typeof result?.stderr === "string" ? result.stderr : "";
  const errorText = typeof result?.error === "string" ? result.error : "";
  const files = Array.isArray(result?.files) ? (result.files as Record<string, unknown>[]) : [];
  const exitCode = typeof result?.exit_code === "number" ? result.exit_code : undefined;
  const ok = result?.ok === true;

  const title =
    status === "running"
      ? locale === "zh-CN" ? `正在运行 ${label}…` : `Running ${label} code...`
      : status === "failed" || !ok
        ? locale === "zh-CN" ? `${label} 运行失败` : `${label} code failed`
        : locale === "zh-CN" ? `${label} 已运行` : `Ran ${label} code`;

  return (
    <div className="my-2 overflow-hidden rounded-xl border border-[var(--border)]">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 bg-[var(--surface)] px-3.5 py-2 text-left text-sm"
      >
        {status === "running" ? (
          <Spinner className="h-3.5 w-3.5 text-[var(--muted)]" />
        ) : (
          <Terminal size={14} className={cn(ok ? "text-accent" : "text-red-500")} />
        )}
        <span className="flex-1 font-medium">{title}</span>
        {exitCode !== undefined && (
          <span className={cn("text-xs", ok ? "text-[var(--muted)]" : "text-red-500")}>
            exit {exitCode}
          </span>
        )}
        <ChevronDown size={14} className={cn("text-[var(--muted)] transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="space-y-2 px-3.5 py-3 text-xs">
          {code && (
            <pre className="max-h-64 overflow-auto rounded-lg bg-[#0d0d0d] p-3 text-gray-100">{code}</pre>
          )}
          {stdout && (
            <div>
              <div className="mb-1 font-semibold text-[var(--muted)]">stdout</div>
              <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-lg bg-[var(--surface)] p-2.5">{stdout}</pre>
            </div>
          )}
          {stderr && (
            <div>
              <div className="mb-1 font-semibold text-red-500">stderr</div>
              <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-lg bg-red-500/10 p-2.5 text-red-500">{stderr}</pre>
            </div>
          )}
          {errorText && <div className="text-red-500">{errorText}</div>}
          {files.length > 0 && (
            <div className="flex flex-wrap gap-2 pt-1">
              {files.map((f, i) =>
                f.file_id ? (
                  <button
                    type="button"
                    key={i}
                    onClick={() => void downloadAuthenticated(String(f.file_id), String(f.name ?? "download"))}
                    className="flex items-center gap-1.5 rounded-lg border border-[var(--border)] px-2.5 py-1.5 hover:bg-[var(--surface)]"
                  >
                    <Download size={13} className="text-[var(--muted)]" />
                    <span>{String(f.name)}</span>
                    <span className="text-[var(--muted)]">{fmtSize(Number(f.size ?? 0))}</span>
                  </button>
                ) : (
                  <span key={i} className="text-[var(--muted)]">
                    {String(f.name)} ({String(f.skipped ?? "")})
                  </span>
                ),
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function blockText(message: Message, type: string): string {
  return message.blocks
    .filter((b) => b.type === type)
    .map((b) => (b.data?.text as string) ?? "")
    .join("\n");
}

export function ThinkingDots({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1", className)}>
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-current" style={{ animationDelay: "0ms" }} />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-current" style={{ animationDelay: "150ms" }} />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-current" style={{ animationDelay: "300ms" }} />
    </span>
  );
}

function ReasoningBlock({ text, streaming, defaultOpen }: { text: string; streaming?: boolean; defaultOpen?: boolean }) {
  const { t } = useApp();
  const [open, setOpen] = useState(defaultOpen ?? false);
  if (!text && !streaming) return null;
  return (
    <div className="mb-2">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 rounded-lg px-2 py-1 text-sm text-[var(--muted)] hover:bg-[var(--surface)]"
      >
        {streaming ? <ThinkingDots className="text-accent" /> : <Lightbulb size={14} />}
        <span>{streaming ? t("thinking", "Thinking…") : t("thought", "Thought for a moment")}</span>
        <ChevronDown size={14} className={cn("transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="mt-1 max-h-72 overflow-y-auto overscroll-contain border-l-2 border-[var(--border)] pl-3 pr-2 text-sm text-[var(--muted)] whitespace-pre-wrap">
          {text}
        </div>
      )}
    </div>
  );
}

export interface LiveTool {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
  status: "running" | "done" | "failed";
  result?: Record<string, unknown>;
}

export function MessageView({
  message,
  streaming,
  streamingReasoning,
  streamingText,
  streamingTools,
  modelName,
  isLastAssistant,
  isLastUser,
  onRegenerate,
  onEditUser,
  busy,
  elapsedMs,
  branchPosition,
  branchCount,
  onPreviousBranch,
  onNextBranch,
}: {
  message: Message;
  streaming?: boolean;
  streamingReasoning?: string;
  streamingText?: string;
  streamingTools?: LiveTool[];
  modelName?: string;
  isLastAssistant?: boolean;
  isLastUser?: boolean;
  onRegenerate?: () => void;
  onEditUser?: (text: string) => Promise<void> | void;
  busy?: boolean;
  elapsedMs?: number;
  branchPosition?: number;
  branchCount?: number;
  onPreviousBranch?: () => void;
  onNextBranch?: () => void;
}) {
  const { t, locale } = useApp();
  const [copied, setCopied] = useState(false);
  const [savedArtifact, setSavedArtifact] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [previewFile, setPreviewFile] = useState<PreviewTarget | null>(null);
  const saveAsArtifact = async () => {
    if (!text || savedArtifact) return;
    try {
      await phase7Api.createArtifact({
        kind: "document",
        title: text.split("\n")[0].replace(/^#+\s*/, "").slice(0, 80) || (locale === "zh-CN" ? "已保存的回答" : "Saved response"),
        content: text,
        conversation_id: message.conversation_id,
        message_id: message.id,
      });
      setSavedArtifact(true);
    } catch {
      /* best effort */
    }
  };
  const reasoning = streaming && streamingReasoning !== undefined ? streamingReasoning : blockText(message, "reasoning");
  const text = streaming && streamingText !== undefined ? streamingText : blockText(message, "markdown") || blockText(message, "text");
  const errorText = message.status === "failed" ? ((message.error?.message as string) ?? "Something went wrong.") : null;

  const tools: LiveTool[] =
    streaming && streamingTools
      ? streamingTools
      : message.blocks
          .filter((b) => b.type === "tool_call")
          .map((b) => {
            const resultBlock = message.blocks.find(
              (r) => r.type === "tool_result" && r.data.tool_call_id === b.data.tool_call_id,
            );
            const failed = resultBlock ? resultBlock.data.ok === false : false;
            return {
              id: String(b.data.tool_call_id),
              name: String(b.data.name),
              arguments: (b.data.arguments as Record<string, unknown>) ?? {},
              status: resultBlock ? (failed ? "failed" : "done") : "running",
              result: resultBlock?.data,
            };
          });

  const copy = async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const sandboxFiles: Record<string, string> = {};
  for (const b of message.blocks) {
    if (b.type === "tool_result") {
      for (const f of (b.data.files as Record<string, unknown>[]) ?? []) {
        if (f?.file_id && f?.name) sandboxFiles[String(f.name)] = String(f.file_id);
      }
    } else if (b.type === "file" && b.data.file_id && b.data.name) {
      sandboxFiles[String(b.data.name)] = String(b.data.file_id);
    }
  }
  let renderedText = text;
  for (const name of Object.keys(sandboxFiles)) {
    renderedText = renderedText.split(`](${name})`).join(`](sandbox-file:${name})`);
  }

  const sources: Record<string, unknown>[] = [];
  for (const b of message.blocks) {
    if (b.type === "sources" && Array.isArray(b.data.sources)) {
      sources.push(...(b.data.sources as Record<string, unknown>[]));
    }
  }
  const imageBlocks = message.blocks.filter((b) => b.type === "image");
  const assistantFileBlocks = message.blocks.filter((b) => b.type === "file" && Boolean(b.data.file_id));
  const usage = message.usage ?? {};
  const tokenCount = Number(usage.total_tokens ?? 0) || Number(usage.input_tokens ?? usage.prompt_tokens ?? 0) + Number(usage.output_tokens ?? usage.completion_tokens ?? 0);
  const durationMs = Number(usage.duration_ms ?? 0) || elapsedMs || 0;
  const showTokenCount = !streaming && Boolean(message.model_id) && (message.status === "completed" || message.status === "failed");

  if (message.role === "user") {
    const fileBlocks = message.blocks.filter((b) => b.type === "file" || b.type === "image");
    return (
      <>
      <div className="group flex flex-col items-end gap-1.5 py-3">
        {fileBlocks.length > 0 && (
          <div className="flex max-w-[85%] flex-wrap justify-end gap-2">
            {fileBlocks.map((b) =>
              b.type === "image" ? (
                <div key={b.id} className="relative">
                  <AuthImage
                    src={(b.data.url as string) ?? ""}
                    alt={(b.data.name as string) ?? "image"}
                    className="h-32 w-32 rounded-xl border border-[var(--border)] object-cover"
                  />
                  {b.data.vision === "fallback" && (
                    <div className="mt-1 max-w-[128px] text-[10px] leading-tight text-[var(--muted)]">
                      Converted to description by {String(b.data.fallback_model ?? "vision model")} (fallback)
                    </div>
                  )}
                </div>
              ) : (
                <button type="button" onClick={() => setPreviewFile({ fileId: String(b.data.file_id), name: String(b.data.name ?? "file"), mime: String(b.data.mime ?? "") })} key={b.id} title={String(b.data.name ?? "file")} className="flex min-h-14 items-center gap-2 rounded-xl border border-[var(--border)] bg-[var(--surface)] px-2.5 py-2 text-xs hover:border-[var(--muted)]">
                  <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-[var(--bg)]"><MessageFileIcon name={String(b.data.name ?? "file")} mime={String(b.data.mime ?? "")} /></span>
                  <div className="max-w-[72px] truncate font-semibold">{fileExtension(String(b.data.name ?? "file"))}</div>
                </button>
              ),
            )}
          </div>
        )}
        {editing ? (
          <div className="w-full max-w-[85%] rounded-3xl bg-[var(--surface)] p-3">
            <textarea autoFocus value={draft} onChange={(e) => setDraft(e.target.value)} rows={3} className="w-full resize-y bg-transparent px-2 py-1 text-[15px] outline-none" />
            <div className="mt-2 flex justify-end gap-2">
              <button type="button" onClick={() => setEditing(false)} className="rounded-full border border-[var(--border)] px-3 py-1.5 text-xs">{t("cancel", "Cancel")}</button>
              <button type="button" disabled={!draft.trim() || busy} onClick={async () => { await onEditUser?.(draft.trim()); setEditing(false); }} className="rounded-full bg-[var(--fg)] px-3 py-1.5 text-xs text-[var(--bg)] disabled:opacity-40">{t("send", "Send")}</button>
            </div>
          </div>
        ) : text && (
          <div className="max-w-[85%] whitespace-pre-wrap rounded-3xl bg-[var(--surface)] px-5 py-2.5 text-[15px]">
            {text}
          </div>
        )}
        {!editing && (
          <div className="flex items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
            <IconBtn title={t("copy", "Copy")} onClick={copy}>{copied ? <Check size={15} /> : <Copy size={15} />}</IconBtn>
            {isLastUser && onEditUser && <IconBtn title={t("edit", "Edit")} onClick={() => { setDraft(text); setEditing(true); }}><Pencil size={15} /></IconBtn>}
          </div>
        )}
      </div>
      {previewFile && <FilePreviewModal file={previewFile} onClose={() => setPreviewFile(null)} />}
      </>
    );
  }

  return (
    <div className="group flex gap-3 py-4">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[var(--fg)] text-[var(--bg)]">
        <SparkleIcon />
      </div>
      <div className="min-w-0 flex-1">
        {reasoning !== undefined && reasoning !== "" && (
          <ReasoningBlock text={reasoning} streaming={streaming && !streamingText} defaultOpen={false} />
        )}
      {tools.map((t) => (
        <ToolCard key={t.id} name={t.name} args={t.arguments} status={t.status} result={t.result} />
      ))}
      {streaming && !text && !reasoning && tools.length === 0 && (
        <div className="flex items-center gap-2 py-2 text-[var(--muted)]">
          <ThinkingDots className="text-accent" />
        </div>
      )}
      {imageBlocks.length > 0 && (
        <div className="my-2 flex flex-wrap gap-2">
          {imageBlocks.map((b) => (
            <div key={b.id} className="max-w-full">
              <AuthImage
                src={(b.data.url as string) ?? ""}
                alt={(b.data.name as string) ?? "generated image"}
                className="max-h-[32rem] max-w-full rounded-xl border border-[var(--border)] object-contain"
              />
              {b.data.generated === true && (
                <div className="mt-1 max-w-64 text-[10px] leading-4 text-[var(--muted)]">
                  {t("generatedImage", "Generated image")}
                  {Boolean(b.data.aspect_ratio) && (
                    <span> · {String(b.data.aspect_ratio)}{b.data.width && b.data.height ? ` · ${String(b.data.width)}×${String(b.data.height)}` : ""}</span>
                  )}
                  {b.data.refined === true && Boolean(b.data.prompt_used) && (
                    <div className="mt-1 line-clamp-2" title={String(b.data.prompt_used)}>
                      {t("refinedPrompt", "Refined prompt")}: {String(b.data.prompt_used)}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      {assistantFileBlocks.length > 0 && (
        <div className="my-3 grid gap-2 sm:grid-cols-2">
          {assistantFileBlocks.map((block) => {
            const fileId = String(block.data.file_id);
            const name = String(block.data.name ?? "file");
            const mime = String(block.data.mime ?? "");
            const isSvg = mime === "image/svg+xml" || name.toLowerCase().endsWith(".svg");
            return (
              <div key={block.id} className="overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface)]">
                {isSvg && (
                  <button type="button" className="block w-full bg-[var(--bg)] p-2" onClick={() => setPreviewFile({ fileId, name, mime })}>
                    <AuthImage src={api.fileDownloadUrl(fileId)} alt={name} className="mx-auto h-56 w-full object-contain" />
                  </button>
                )}
                <div className="flex items-center gap-2 px-3 py-2.5">
                  <MessageFileIcon name={name} mime={mime} />
                  <div className="min-w-0 flex-1"><div className="truncate text-sm font-medium">{name}</div><div className="text-[11px] text-[var(--muted)]">{fmtSize(Number(block.data.size ?? 0))}</div></div>
                  <IconBtn title={t("preview", "Preview")} onClick={() => setPreviewFile({ fileId, name, mime })}><Eye size={15} /></IconBtn>
                  <IconBtn title={t("download", "Download")} onClick={() => void downloadAuthenticated(fileId, name)}><Download size={15} /></IconBtn>
                </div>
              </div>
            );
          })}
        </div>
      )}
      {text && (
        <div className={cn(streaming && !text.endsWith(" ") && "stream-cursor")}>
          <Markdown content={renderedText} sandboxFiles={sandboxFiles} />
        </div>
      )}
      {!streaming && sources.length > 0 && <SourcesBlock sources={sources} />}
      {errorText && (
        <div className="mt-2 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-500">
          {errorText}
        </div>
      )}
      {(durationMs > 0 || showTokenCount) && (
        <div className="mt-2 flex items-center gap-2 text-[11px] text-[var(--muted)]">
          {durationMs > 0 && <span>{formatDuration(durationMs)}</span>}
          {durationMs > 0 && showTokenCount && <span>·</span>}
          {showTokenCount && <span>{tokenCount.toLocaleString()} tokens</span>}
        </div>
      )}
      {!streaming && (message.status === "completed" || message.status === "failed") && (
        <div className="mt-1.5 flex items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
          {(branchCount ?? 0) > 1 && (
            <div className="mr-1 flex items-center gap-0.5">
              <IconBtn title={t("previousResponse", "Previous response")} onClick={onPreviousBranch} className={cn(!onPreviousBranch && "pointer-events-none opacity-30")}><ChevronLeft size={15} /></IconBtn>
              <span className="min-w-8 text-center text-xs text-[var(--muted)]">{branchPosition} / {branchCount}</span>
              <IconBtn title={t("nextResponse", "Next response")} onClick={onNextBranch} className={cn(!onNextBranch && "pointer-events-none opacity-30")}><ChevronRight size={15} /></IconBtn>
            </div>
          )}
          <IconBtn title={t("copy", "Copy")} onClick={copy}>
            {copied ? <Check size={16} /> : <Copy size={16} />}
          </IconBtn>
          {message.status === "completed" && text && (
            <IconBtn title={t("saveArtifact", "Save as artifact")} onClick={saveAsArtifact}>
              {savedArtifact ? <Check size={16} className="text-accent" /> : <Save size={16} />}
            </IconBtn>
          )}
          {isLastAssistant && onRegenerate && (
            <IconBtn title={t("regenerate", "Regenerate")} onClick={onRegenerate} className={cn(busy && "pointer-events-none opacity-50")}>
              <RefreshCw size={16} />
            </IconBtn>
          )}
          {message.status === "completed" && <IconBtn title={t("goodResponse", "Good response")}>
            <ThumbsUp size={16} />
          </IconBtn>}
          {message.status === "completed" && <IconBtn title={t("badResponse", "Bad response")}>
            <ThumbsDown size={16} />
          </IconBtn>}
          {modelName && <span className="ml-1 text-xs text-[var(--muted)]">{modelName}</span>}
        </div>
      )}
      </div>
      {previewFile && <FilePreviewModal file={previewFile} onClose={() => setPreviewFile(null)} />}
    </div>
  );
}

function SparkleIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M12 2l2.4 7.2L22 12l-7.6 2.8L12 22l-2.4-7.2L2 12l7.6-2.8L12 2z" />
    </svg>
  );
}

function SourcesBlock({ sources }: { sources: Record<string, unknown>[] }) {
  const { t } = useApp();
  const [openIdx, setOpenIdx] = useState<number | null>(null);
  return (
    <div className="mt-3">
      <div className="mb-1.5 text-xs font-semibold text-[var(--muted)]">{t("sources", "Sources")}</div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {sources.map((s, i) => {
          const url = String(s.url ?? "#");
          const title = String(s.title || url);
          const domain = String(s.domain || "");
          const num = Number(s.citation_number ?? i + 1);
          const text = String(s.text ?? "");
          return (
            <div key={i} className="relative">
              <button
                type="button"
                onClick={() => setOpenIdx(openIdx === i ? null : i)}
                className="flex w-full items-start gap-2 rounded-xl border border-[var(--border)] bg-[var(--surface)] px-2.5 py-2 text-left hover:border-accent"
              >
                <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded bg-accent/10 text-[10px] font-semibold text-accent">
                  {num}
                </span>
                <span className="min-w-0">
                  <span className="block truncate text-xs font-medium">{title}</span>
                  <span className="block truncate text-[10px] text-[var(--muted)]">{domain}</span>
                </span>
              </button>
              {openIdx === i && (
                <div className="absolute left-0 right-0 top-full z-20 mt-1 max-h-48 overflow-y-auto rounded-xl border border-[var(--border)] bg-[var(--bg)] p-3 shadow-xl">
                  <p className="whitespace-pre-wrap text-xs text-[var(--muted)]">{text || t("noExcerpt", "No excerpt available.")}</p>
                  <a
                    href={url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-2 inline-flex items-center gap-1 text-xs text-accent hover:underline"
                  >
                    <ExternalLink size={12} /> {t("openSource", "Open source")}
                  </a>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
