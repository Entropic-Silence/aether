"use client";

import { useEffect, useRef, useState } from "react";
import { Brain, Check, ChevronDown, Eye, Image as ImageIcon } from "lucide-react";
import type { ModelInfo } from "@/lib/types";
import { useApp } from "@/lib/hooks";

export function ModelSelector({
  models,
  selectedId,
  onSelect,
}: {
  models: ModelInfo[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const { t } = useApp();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const selected = models.find((m) => m.id === selectedId) ?? models.find((m) => m.is_default) ?? models[0];

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  if (!models.length) {
    return <div className="px-3 py-2 text-sm text-[var(--muted)]">{t("modelNone", "No models configured")}</div>;
  }

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[15px] font-semibold hover:bg-[var(--surface)]"
      >
        <span className="max-w-[180px] truncate">{selected?.display_name ?? t("selectModel", "Select model")}</span>
        <ChevronDown size={15} className="text-[var(--muted)]" />
      </button>
      {open && (
        <div className="absolute bottom-full left-0 z-30 mb-2 max-h-96 w-80 overflow-y-auto rounded-2xl border border-[var(--border)] bg-[var(--bg)] py-1.5 shadow-xl">
          {models.map((m) => {
            const caps = m.effective_capabilities || {};
            return (
              <button
                key={m.id}
                type="button"
                onClick={() => {
                  onSelect(m.id);
                  setOpen(false);
                }}
                className="flex w-full items-start justify-between gap-2 px-3.5 py-2.5 text-left hover:bg-[var(--surface)]"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5 text-sm font-medium">
                    <span className="truncate">{m.display_name}</span>
                    <span className="flex gap-1 text-[var(--muted)]">
                      {caps.reasoning === true && <Brain size={13} aria-label={t("reasoning", "Reasoning")} />}
                      {caps.image_input === true && <Eye size={13} aria-label={t("vision", "Vision")} />}
                      {caps.image_generation === true && <ImageIcon size={13} aria-label={t("imageGeneration", "Image generation")} />}
                    </span>
                  </div>
                  {m.description && (
                    <div className="mt-0.5 line-clamp-2 text-xs text-[var(--muted)]">{m.description}</div>
                  )}
                </div>
                {selected?.id === m.id && <Check size={16} className="mt-1 shrink-0 text-accent" />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function ReasoningSelector({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  const { t } = useApp();
  const levels = [
    { id: "auto", label: t("auto", "Auto") },
    { id: "low", label: t("low", "Low") },
    { id: "medium", label: t("medium", "Medium") },
    { id: "high", label: t("high", "High") },
  ];
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const selected = levels.find((level) => level.id === value) ?? levels[0];
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);
  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex h-8 items-center gap-1.5 rounded-lg px-2 text-xs font-medium text-[var(--muted)] hover:bg-[var(--surface)] hover:text-[var(--fg)]"
        title={t("reasoning", "Reasoning")}
      >
        <Brain size={14} /> <span className="hidden sm:inline">{selected.label}</span> <ChevronDown size={13} />
      </button>
      {open && (
        <div className="absolute bottom-full right-0 z-30 mb-2 w-40 rounded-2xl border border-[var(--border)] bg-[var(--bg)] py-1.5 shadow-xl">
          {levels.map((level) => (
            <button
              key={level.id}
              type="button"
              onClick={() => { onChange(level.id); setOpen(false); }}
              className="flex w-full items-center justify-between px-3.5 py-2 text-left text-sm hover:bg-[var(--surface)]"
            >
              {level.label}
              {value === level.id && <Check size={14} className="text-accent" />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
