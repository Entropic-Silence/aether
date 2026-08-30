"use client";

import { useEffect, useState } from "react";
import { Mic2, Save, Volume2 } from "lucide-react";
import { api } from "@/lib/api";
import { useApp } from "@/lib/hooks";
import { Button, Spinner } from "@/components/ui";

type AudioSide = { kind?: string; base_url?: string; api_key?: string; has_api_key?: boolean; model?: string; voice?: string };
const inputClass = "w-full rounded-xl border border-[var(--border)] bg-transparent px-3.5 py-2.5 text-sm outline-none focus:border-[var(--fg)]";

export default function AudioAdminPage() {
  const { locale } = useApp();
  const zh = locale === "zh-CN";
  const [stt, setStt] = useState<AudioSide | null>(null);
  const [tts, setTts] = useState<AudioSide | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => { api.audioSettings().then((data) => { setStt(data.stt as AudioSide); setTts(data.tts as AudioSide); }).catch(() => { setStt({}); setTts({}); }); }, []);
  if (!stt || !tts) return <Spinner className="h-6 w-6 text-[var(--muted)]" />;

  const save = async () => {
    setSaving(true);
    try {
      await api.updateAudioSettings({
        stt: stt.kind === "disabled" ? {} : { kind: "openai_compatible", base_url: stt.base_url ?? "", api_key: stt.api_key ?? "", model: stt.model ?? "" },
        tts: tts.kind === "disabled" ? {} : { kind: "openai_compatible", base_url: tts.base_url ?? "", api_key: tts.api_key ?? "", model: tts.model ?? "", voice: tts.voice ?? "alloy" },
      });
      setSaved(true); window.setTimeout(() => setSaved(false), 1800);
    } finally { setSaving(false); }
  };

  return (
    <div className="mx-auto max-w-5xl">
      <div className="mb-7 flex flex-wrap items-end justify-between gap-4"><div><div className="mb-2 flex items-center gap-2 text-xs font-medium uppercase tracking-[0.16em] text-[var(--muted)]"><Mic2 size={14} /> {zh ? "多模态能力" : "Multimodal capability"}</div><h1 className="text-2xl font-semibold tracking-tight">{zh ? "语音服务" : "Voice services"}</h1><p className="mt-1.5 text-sm text-[var(--muted)]">{zh ? "配置 OpenAI 兼容格式的语音识别与语音合成接口。API Key 留空会保留已保存的密钥。" : "Configure OpenAI-compatible speech recognition and synthesis. Leave API keys blank to preserve saved secrets."}</p></div><Button variant="primary" onClick={save} disabled={saving}><Save size={15} /> {saved ? (zh ? "已保存" : "Saved") : saving ? (zh ? "保存中" : "Saving") : (zh ? "保存配置" : "Save settings")}</Button></div>
      <div className="grid gap-5 lg:grid-cols-2">
        <AudioCard title={zh ? "语音转文字" : "Speech to text"} description={zh ? "为输入框提供录音转写能力。" : "Powers microphone transcription in the composer."} icon={<Mic2 size={18} />} value={stt} onChange={setStt} zh={zh} defaults={{ model: "whisper-1" }} />
        <AudioCard title={zh ? "文字转语音" : "Text to speech"} description={zh ? "为助手回复提供朗读能力。" : "Powers spoken playback for assistant responses."} icon={<Volume2 size={18} />} value={tts} onChange={setTts} zh={zh} defaults={{ model: "tts-1", voice: "alloy" }} showVoice />
      </div>
      <div className="mt-5 rounded-2xl border border-[var(--border)] bg-[var(--surface)]/55 px-5 py-4 text-xs leading-5 text-[var(--muted)]">{zh ? "此页负责连接底层语音服务；用户端是否显示语音入口仍由“功能与权限 → 语音”总开关控制。" : "This page configures providers. User-facing voice controls remain governed by Features & access → Voice."}</div>
    </div>
  );
}

function AudioCard({ title, description, icon, value, onChange, zh, defaults, showVoice = false }: { title: string; description: string; icon: React.ReactNode; value: AudioSide; onChange: (value: AudioSide) => void; zh: boolean; defaults: AudioSide; showVoice?: boolean }) {
  const enabled = value.kind !== "disabled" && Boolean(value.kind || value.base_url || value.model);
  const setEnabled = (next: boolean) => onChange(next ? { ...defaults, ...value, kind: "openai_compatible" } : { ...value, kind: "disabled" });
  return <section className="rounded-2xl border border-[var(--border)] p-5"><div className="mb-5 flex items-start justify-between gap-3"><div className="flex gap-3"><span className="flex h-9 w-9 items-center justify-center rounded-xl bg-[var(--surface)]">{icon}</span><div><h2 className="text-sm font-semibold">{title}</h2><p className="mt-0.5 text-xs leading-5 text-[var(--muted)]">{description}</p></div></div><button type="button" onClick={() => setEnabled(!enabled)} className={`relative h-6 w-11 shrink-0 rounded-full ${enabled ? "bg-[var(--fg)]" : "bg-[var(--border)]"}`}><span className={`absolute left-0 top-1 h-4 w-4 rounded-full bg-[var(--bg)] shadow-sm transition-transform ${enabled ? "translate-x-6" : "translate-x-1"}`} /></button></div><div className={`space-y-3 ${enabled ? "" : "pointer-events-none opacity-45"}`}><Field label="Base URL"><input className={inputClass} value={value.base_url ?? ""} onChange={(e) => onChange({ ...value, base_url: e.target.value, kind: "openai_compatible" })} placeholder="https://api.example.com/v1" /></Field><Field label={zh ? "模型 ID" : "Model ID"}><input className={inputClass} value={value.model ?? defaults.model ?? ""} onChange={(e) => onChange({ ...value, model: e.target.value, kind: "openai_compatible" })} placeholder={defaults.model} /></Field>{showVoice && <Field label={zh ? "默认音色" : "Default voice"}><input className={inputClass} value={value.voice ?? defaults.voice ?? ""} onChange={(e) => onChange({ ...value, voice: e.target.value })} placeholder="alloy" /></Field>}<Field label={`API Key${value.has_api_key ? (zh ? "（已保存）" : " (saved)") : ""}`}><input type="password" autoComplete="new-password" className={inputClass} value={value.api_key ?? ""} onChange={(e) => onChange({ ...value, api_key: e.target.value })} placeholder={value.has_api_key ? "••••••••" : "sk-…"} /></Field></div></section>;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) { return <label><span className="mb-1.5 block text-xs font-medium text-[var(--muted)]">{label}</span>{children}</label>; }
