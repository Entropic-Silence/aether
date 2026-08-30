"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowUp, File as FileIcon, FileArchive, FileAudio, FileCode, FileSpreadsheet, FileText, FileVideo, Globe, Image as ImageIcon, Loader2, Mic, Paperclip, Plus, Presentation, Puzzle, Sparkles, Square, Wand2, X } from "lucide-react";
import type { FileMeta, ImageAspectRatio, PluginInfo } from "@/lib/types";
import { phase7Api } from "@/lib/api";
import { useApp } from "@/lib/hooks";
import { AuthImage } from "./AuthImage";
import { cn } from "./ui";

function extension(name: string): string {
  const value = name.includes(".") ? name.split(".").pop() || "FILE" : "FILE";
  return value.slice(0, 8).toUpperCase();
}

function AttachmentIcon({ name, mime }: { name: string; mime: string }) {
  const ext = extension(name).toLowerCase();
  const cls = "h-6 w-6";
  if (["xls", "xlsx", "csv", "ods"].includes(ext)) return <FileSpreadsheet className={`${cls} text-emerald-600`} />;
  if (["ppt", "pptx", "key"].includes(ext)) return <Presentation className={`${cls} text-orange-500`} />;
  if (["zip", "rar", "7z", "tar", "gz"].includes(ext)) return <FileArchive className={`${cls} text-amber-600`} />;
  if (mime.startsWith("audio/") || ["mp3", "wav", "m4a", "flac"].includes(ext)) return <FileAudio className={`${cls} text-violet-500`} />;
  if (mime.startsWith("video/") || ["mp4", "mov", "mkv", "webm"].includes(ext)) return <FileVideo className={`${cls} text-fuchsia-500`} />;
  if (["js", "ts", "tsx", "jsx", "py", "json", "html", "css", "md"].includes(ext)) return <FileCode className={`${cls} text-sky-600`} />;
  if (["pdf", "doc", "docx", "txt", "rtf"].includes(ext)) return <FileText className={`${cls} text-red-500`} />;
  return <FileIcon className={`${cls} text-[var(--muted)]`} />;
}

export function Composer({
  onSend,
  onStop,
  streaming,
  placeholder = "Message",
  autoFocus,
  attachments = [],
  uploading = 0,
  onFiles,
  onRemoveAttachment,
  canImages = true,
  webSearch = false,
  onToggleWebSearch,
  searchAvailable = false,
  onDeepResearch,
  imageAvailable = false,
  onCreateImage,
  sttAvailable = false,
  controls,
  imageCreation = false,
  onCancelImageCreation,
  imageAspectRatio = "auto",
  onImageAspectRatioChange,
  workPlugins = [],
  selectedPluginIds = [],
  onTogglePlugin,
}: {
  onSend: (content: string) => void;
  onStop?: () => void;
  streaming?: boolean;
  placeholder?: string;
  autoFocus?: boolean;
  attachments?: FileMeta[];
  uploading?: number;
  onFiles?: (files: File[]) => void;
  onRemoveAttachment?: (id: string) => void;
  canImages?: boolean;
  webSearch?: boolean;
  onToggleWebSearch?: () => void;
  searchAvailable?: boolean;
  onDeepResearch?: () => void;
  imageAvailable?: boolean;
  onCreateImage?: () => void;
  sttAvailable?: boolean;
  controls?: React.ReactNode;
  imageCreation?: boolean;
  onCancelImageCreation?: () => void;
  imageAspectRatio?: ImageAspectRatio | "auto";
  onImageAspectRatioChange?: (ratio: ImageAspectRatio | "auto") => void;
  workPlugins?: PluginInfo[];
  selectedPluginIds?: string[];
  onTogglePlugin?: (id: string) => void;
}) {
  const { t } = useApp();
  const [value, setValue] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [micError, setMicError] = useState<string | null>(null);
  const mediaRecorder = useRef<MediaRecorder | null>(null);
  const audioChunks = useRef<Blob[]>([]);
  const ref = useRef<HTMLTextAreaElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const imageInput = useRef<HTMLInputElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const composingRef = useRef(false);

  const resize = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 200) + "px";
  }, []);

  useEffect(() => {
    resize();
  }, [value, resize]);

  useEffect(() => {
    if (autoFocus) ref.current?.focus();
  }, [autoFocus]);

  const toggleMic = useCallback(async () => {
    setMicError(null);
    if (recording) {
      mediaRecorder.current?.stop();
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunks.current = [];
      const rec = new MediaRecorder(stream);
      rec.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunks.current.push(e.data);
      };
      rec.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        setRecording(false);
        const blob = new Blob(audioChunks.current, { type: rec.mimeType || "audio/webm" });
        if (blob.size === 0) return;
        setTranscribing(true);
        try {
          const text = await phase7Api.transcribe(blob, "voice.webm");
          if (text.trim()) setValue((v) => (v ? v + " " : "") + text.trim());
        } catch (e) {
          setMicError(e instanceof Error ? e.message : t("transcriptionFailed", "Transcription failed"));
        } finally {
          setTranscribing(false);
        }
      };
      mediaRecorder.current = rec;
      rec.start();
      setRecording(true);
    } catch {
      setMicError(t("microphoneUnavailable", "Microphone unavailable"));
    }
  }, [recording, t]);

  const submit = () => {
    const text = value.trim();
    if ((!text && attachments.length === 0) || streaming) return;
    setValue("");
    onSend(text);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !composingRef.current && !e.nativeEvent.isComposing && e.nativeEvent.keyCode !== 229) {
      e.preventDefault();
      submit();
    }
  };

  const onPaste = (e: React.ClipboardEvent) => {
    if (!onFiles) return;
    const files = Array.from(e.clipboardData.files ?? []);
    if (files.length) {
      e.preventDefault();
      onFiles(files);
    }
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    if (!onFiles) return;
    const files = Array.from(e.dataTransfer.files ?? []);
    if (files.length) onFiles(files);
  };

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={onDrop}
      className={cn(
        "composer-shell rounded-[28px] border bg-[var(--composer)] shadow-sm transition-colors",
        dragOver ? "border-accent" : "border-[var(--border)]",
      )}
    >
      {(attachments.length > 0 || uploading > 0) && (
        <div className="flex flex-wrap gap-2 px-4 pt-3">
          {attachments.map((a) => (
            <div key={a.id} title={a.name} className="flex min-h-14 items-center gap-2 rounded-xl border border-[var(--border)] bg-[var(--surface)] py-1.5 pl-2 pr-1.5 text-xs">
              {a.kind === "image" ? (
                <AuthImage src={`/api/v1/files/${a.id}/download`} alt="" className="h-11 w-11 rounded-lg object-cover" />
              ) : (
                <span className="flex h-11 w-11 items-center justify-center rounded-lg bg-[var(--bg)]"><AttachmentIcon name={a.name} mime={a.mime} /></span>
              )}
              <span className="max-w-[72px] truncate font-semibold">{a.kind === "image" ? a.name : extension(a.name)}</span>
              {a.status === "failed" && <span className="text-red-500" title={a.error}>{t("uploadFailed", "failed")}</span>}
              <button
                type="button"
                onClick={() => onRemoveAttachment?.(a.id)}
                className="flex h-5 w-5 items-center justify-center rounded-full text-[var(--muted)] hover:bg-[var(--border)]"
              >
                <X size={12} />
              </button>
            </div>
          ))}
          {Array.from({ length: uploading }).map((_, i) => (
            <div key={`up-${i}`} className="flex items-center gap-2 rounded-xl border border-[var(--border)] bg-[var(--surface)] px-2.5 py-2 text-xs text-[var(--muted)]">
              <Loader2 size={14} className="animate-spin" /> {t("uploading", "Uploading...")}
            </div>
          ))}
        </div>
      )}
      <textarea
        ref={ref}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={onKeyDown}
        onCompositionStart={() => { composingRef.current = true; }}
        onCompositionEnd={() => { composingRef.current = false; }}
        onPaste={onPaste}
        placeholder={placeholder}
        rows={1}
        className="min-h-[52px] max-h-[200px] w-full resize-none overflow-y-auto bg-transparent px-5 py-3.5 text-[15px] leading-6 outline-none placeholder:text-[var(--muted)]"
      />
      <div className="flex items-center justify-between px-3 pb-2.5">
        <div className="relative flex items-center gap-1" ref={menuRef}>
          {onFiles && (
            <>
              <input ref={fileInput} type="file" multiple className="hidden"
                onChange={(e) => {
                  const files = Array.from(e.target.files ?? []);
                  if (files.length) onFiles(files);
                  e.target.value = "";
                }} />
              <input ref={imageInput} type="file" multiple accept="image/*" className="hidden"
                onChange={(e) => {
                  const files = Array.from(e.target.files ?? []);
                  if (files.length) onFiles(files);
                  e.target.value = "";
                }} />
            </>
          )}
          <button
            type="button"
            onClick={() => setMenuOpen(!menuOpen)}
            disabled={streaming}
            title={t("add", "Add")}
            className="flex h-9 w-9 items-center justify-center rounded-full text-[var(--muted)] hover:bg-[var(--surface)] hover:text-[var(--fg)] disabled:opacity-40"
          >
            <Plus size={18} />
          </button>
          {menuOpen && (
            <div className="absolute bottom-full left-0 z-30 mb-2 w-60 rounded-2xl border border-[var(--border)] bg-[var(--bg)] py-1.5 shadow-xl">
              {onFiles && (
                <>
                  <MenuItem icon={<Paperclip size={15} />} label={t("uploadFile", "Upload file")}
                    onClick={() => { setMenuOpen(false); fileInput.current?.click(); }} />
                  <MenuItem icon={<ImageIcon size={15} />} label={canImages ? t("uploadImage", "Upload image") : t("imageUnavailable", "Image input unavailable")}
                    disabled={!canImages}
                    onClick={() => { setMenuOpen(false); imageInput.current?.click(); }} />
                </>
              )}
              {searchAvailable && onToggleWebSearch && (
                <MenuItem
                  icon={<Globe size={15} />}
                  label={webSearch ? t("webSearchOn", "Web search: on") : t("webSearch", "Web search")}
                  active={webSearch}
                  onClick={() => { onToggleWebSearch(); setMenuOpen(false); }}
                />
              )}
              {onDeepResearch && searchAvailable && (
                <MenuItem icon={<Sparkles size={15} />} label={t("deepResearch", "Deep research")}
                  onClick={() => { setMenuOpen(false); onDeepResearch(); }} />
              )}
              {onCreateImage && imageAvailable && (
                <MenuItem icon={<Wand2 size={15} />} label={t("createImage", "Create image")}
                  onClick={() => { setMenuOpen(false); onCreateImage(); }} />
              )}
              {workPlugins.map((plugin) => (
                <MenuItem key={plugin.plugin_id} icon={<Puzzle size={15} />} label={plugin.name}
                  active={selectedPluginIds.includes(plugin.plugin_id)}
                  onClick={() => onTogglePlugin?.(plugin.plugin_id)} />
              ))}
            </div>
          )}
          {webSearch && (
            <button
              type="button"
              onClick={onToggleWebSearch}
              title={t("webSearchOn", "Web search enabled — click to disable")}
              className="flex h-8 items-center gap-1.5 rounded-full bg-accent/10 px-3 text-xs font-medium text-accent"
            >
              <Globe size={13} /> {t("webSearch", "Search")}
              <X size={12} />
            </button>
          )}
          {imageCreation && (
            <>
              <button
                type="button"
                onClick={onCancelImageCreation}
                className="flex h-8 items-center gap-1.5 rounded-full bg-[var(--surface)] px-3 text-xs font-medium"
              >
                <Wand2 size={13} /> {t("createImage", "Create image")} <X size={12} />
              </button>
              <select
                aria-label={t("imageRatio", "Image ratio")}
                value={imageAspectRatio}
                onChange={(event) => onImageAspectRatioChange?.(event.target.value as ImageAspectRatio | "auto")}
                className="h-8 rounded-full border border-[var(--border)] bg-[var(--bg)] px-2.5 text-xs outline-none"
              >
                <option value="auto">{t("autoRatio", "Auto ratio")}</option>
                <option value="1:1">1:1</option>
                <option value="16:9">16:9</option>
                <option value="9:16">9:16</option>
                <option value="3:2">3:2</option>
                <option value="2:3">2:3</option>
                <option value="4:3">4:3</option>
                <option value="3:4">3:4</option>
                <option value="5:4">5:4</option>
                <option value="4:5">4:5</option>
                <option value="21:9">21:9</option>
                <option value="9:21">9:21</option>
              </select>
            </>
          )}
          {workPlugins.filter((plugin) => selectedPluginIds.includes(plugin.plugin_id)).map((plugin) => (
            <button key={plugin.plugin_id} type="button" onClick={() => onTogglePlugin?.(plugin.plugin_id)} className="flex h-8 items-center gap-1.5 rounded-full bg-[var(--surface)] px-3 text-xs font-medium">
              <Puzzle size={13} /> {plugin.name} <X size={12} />
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1">
          {controls}
          {sttAvailable && (
            <button
              type="button"
              onClick={toggleMic}
              disabled={transcribing}
              title={recording ? t("stopRecording", "Stop recording") : t("voiceInput", "Voice input")}
              className={cn(
                "flex h-9 w-9 items-center justify-center rounded-full transition-colors",
                recording
                  ? "bg-red-500 text-white"
                  : "text-[var(--muted)] hover:bg-[var(--surface)] hover:text-[var(--fg)]",
                transcribing && "opacity-50",
              )}
            >
              {transcribing ? <Loader2 size={17} className="animate-spin" /> : <Mic size={17} />}
            </button>
          )}
          <button
            type="button"
            onClick={streaming ? onStop : submit}
            disabled={!streaming && !value.trim() && attachments.length === 0}
            className={cn(
              "flex h-9 w-9 items-center justify-center rounded-full transition-colors",
              streaming
                ? "bg-[var(--fg)] text-[var(--bg)]"
                : value.trim() || attachments.length
                  ? "bg-[var(--fg)] text-[var(--bg)]"
                  : "bg-[var(--surface)] text-[var(--muted)]",
            )}
            title={streaming ? t("stop", "Stop generating") : t("send", "Send")}
          >
            {streaming ? <Square size={14} fill="currentColor" /> : <ArrowUp size={18} />}
          </button>
        </div>
      </div>
      {micError && <div className="px-5 pb-2 text-xs text-red-500">{micError}</div>}
    </div>
  );
}

function MenuItem({
  icon,
  label,
  onClick,
  disabled,
  active,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  active?: boolean;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "flex w-full items-center gap-2.5 px-3.5 py-2 text-left text-sm hover:bg-[var(--surface)] disabled:opacity-40",
        active && "text-accent",
      )}
    >
      {icon}
      {label}
    </button>
  );
}
