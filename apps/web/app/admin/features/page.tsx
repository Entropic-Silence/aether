"use client";

import { useEffect, useMemo, useState } from "react";
import { Check, LockKeyhole, Save, SlidersHorizontal } from "lucide-react";
import { api } from "@/lib/api";
import type { FeatureControls, FeatureFlags } from "@/lib/types";
import { useApp } from "@/lib/hooks";
import { Button, Spinner, cn } from "@/components/ui";

const GROUPS: Array<{ title: string; zh: string; items: Array<{ key: keyof FeatureFlags; label: string; zh: string; description: string; zhDescription: string }> }> = [
  {
    title: "Core experiences", zh: "核心体验", items: [
      { key: "chat", label: "Chat", zh: "对话", description: "Allow standard model conversations and regeneration.", zhDescription: "允许普通模型对话、编辑与重新生成。" },
      { key: "work", label: "Work mode", zh: "工作模式", description: "Allow long-running agent tasks, tools and steering.", zhDescription: "允许长任务、工具调用、过程指令与任务终止。" },
      { key: "image_generation", label: "Image generation", zh: "图片生成", description: "Enable automatic and explicit image generation.", zhDescription: "启用自动判断与显式选择的图片生成。" },
      { key: "deep_research", label: "Deep research", zh: "深度研究", description: "Enable multi-step web research reports.", zhDescription: "启用多步骤网页研究与报告生成。" },
    ],
  },
  {
    title: "Workspace", zh: "工作空间", items: [
      { key: "projects", label: "Projects", zh: "项目", description: "Show project workspaces and project instructions.", zhDescription: "显示项目空间、项目文件与项目指令。" },
      { key: "tasks", label: "Scheduled tasks", zh: "定时任务", description: "Allow one-time, interval and cron tasks.", zhDescription: "允许一次性、间隔和 Cron 定时任务。" },
      { key: "library", label: "File library", zh: "资料库", description: "Show the personal file library and previews.", zhDescription: "显示个人资料库、文件检索与预览。" },
      { key: "file_uploads", label: "File uploads", zh: "文件上传", description: "Allow files to be attached or added to the library.", zhDescription: "允许在对话和资料库中上传文件。" },
      { key: "plugins", label: "User plugins", zh: "用户插件", description: "Allow users to enable administrator-approved plugins.", zhDescription: "允许用户启用管理员提供的插件。" },
    ],
  },
  {
    title: "Assistant capabilities", zh: "助手能力", items: [
      { key: "web_search", label: "Web search", zh: "网页搜索", description: "Expose search tools to compatible models.", zhDescription: "向支持工具调用的模型开放网页搜索。" },
      { key: "memory", label: "Memory", zh: "记忆", description: "Allow saved memories and automatic memory capture.", zhDescription: "允许保存记忆、引用记忆和自动捕获。" },
      { key: "custom_instructions", label: "Custom instructions", zh: "自定义指令", description: "Allow personal profile and response-style instructions.", zhDescription: "允许用户设置个人信息与回复风格。" },
      { key: "audio", label: "Voice", zh: "语音", description: "Enable speech-to-text and text-to-speech when configured.", zhDescription: "在服务已配置时启用语音输入与语音输出。" },
    ],
  },
];

export default function AdminFeaturesPage() {
  const { locale } = useApp();
  const zh = locale === "zh-CN";
  const [controls, setControls] = useState<FeatureControls | null>(null);
  const [publicSharing, setPublicSharing] = useState(true);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    Promise.all([api.featureControls(), api.sharingSettings()])
      .then(([next, sharing]) => { setControls(next); setPublicSharing(sharing.public_enabled); })
      .catch(() => setControls(null));
  }, []);

  const enabledCount = useMemo(() => controls ? Object.values(controls.features).filter(Boolean).length : 0, [controls]);
  if (!controls) return <Spinner className="h-6 w-6 text-[var(--muted)]" />;

  const toggle = (key: keyof FeatureFlags) => setControls((current) => current ? ({ ...current, features: { ...current.features, [key]: !current.features[key] } }) : current);
  const save = async () => {
    setSaving(true);
    try {
      const [next] = await Promise.all([
        api.updateFeatureControls(controls),
        api.updateSharingSettings(publicSharing),
      ]);
      setControls(next);
      setSaved(true);
      window.setTimeout(() => setSaved(false), 1800);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mx-auto max-w-5xl">
      <div className="mb-7 flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="mb-2 flex items-center gap-2 text-xs font-medium uppercase tracking-[0.16em] text-[var(--muted)]"><SlidersHorizontal size={14} /> {zh ? "产品控制" : "Product controls"}</div>
          <h1 className="text-2xl font-semibold tracking-tight">{zh ? "功能与权限" : "Features & access"}</h1>
          <p className="mt-1.5 max-w-2xl text-sm text-[var(--muted)]">{zh ? "集中控制用户端可见功能和关键访问策略。关闭后的功能会从导航与操作入口隐藏，并由服务器拒绝后续用户端调用；已开始的任务不会中断。" : "Control visible product capabilities and access policies. Disabled features are hidden and new user-facing requests are rejected; work already in progress is not interrupted."}</p>
        </div>
        <Button variant="primary" onClick={save} disabled={saving}><Save size={15} /> {saving ? (zh ? "保存中" : "Saving") : saved ? (zh ? "已保存" : "Saved") : (zh ? "保存更改" : "Save changes")}</Button>
      </div>

      <div className="mb-6 flex items-center gap-3 rounded-2xl border border-[var(--border)] bg-[var(--surface)]/55 px-4 py-3 text-sm">
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-[var(--fg)] text-[var(--bg)]"><Check size={16} /></span>
        <div><span className="font-medium">{enabledCount} / {Object.keys(controls.features).length}</span> {zh ? "项产品能力已开放" : "product capabilities enabled"}</div>
      </div>

      <div className="space-y-5">
        {GROUPS.map((group) => (
          <section key={group.title} className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg)]">
            <div className="border-b border-[var(--border)] px-5 py-3.5 text-sm font-semibold">{zh ? group.zh : group.title}</div>
            <div className="divide-y divide-[var(--border)]">
              {group.items.map((item) => (
                <button key={item.key} type="button" onClick={() => toggle(item.key)} className="flex w-full items-center justify-between gap-6 px-5 py-4 text-left hover:bg-[var(--surface)]/65">
                  <span><span className="block text-sm font-medium">{zh ? item.zh : item.label}</span><span className="mt-0.5 block text-xs leading-5 text-[var(--muted)]">{zh ? item.zhDescription : item.description}</span></span>
                  <Switch checked={controls.features[item.key]} />
                </button>
              ))}
            </div>
          </section>
        ))}

        <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg)]">
          <div className="flex items-center gap-2 border-b border-[var(--border)] px-5 py-3.5 text-sm font-semibold"><LockKeyhole size={15} /> {zh ? "访问策略" : "Access policies"}</div>
          <div className="divide-y divide-[var(--border)]">
            <button type="button" onClick={() => setControls({ ...controls, policies: { ...controls.policies, registration_enabled: !controls.policies.registration_enabled } })} className="flex w-full items-center justify-between gap-6 px-5 py-4 text-left hover:bg-[var(--surface)]/65">
              <span><span className="block text-sm font-medium">{zh ? "允许注册" : "Open registration"}</span><span className="mt-0.5 block text-xs text-[var(--muted)]">{zh ? "允许新用户自行创建账号；首位所有者不受此开关影响。" : "Allow new users to create accounts; the first owner is unaffected."}</span></span>
              <Switch checked={controls.policies.registration_enabled} />
            </button>
            <button type="button" onClick={() => setPublicSharing(!publicSharing)} className="flex w-full items-center justify-between gap-6 px-5 py-4 text-left hover:bg-[var(--surface)]/65">
              <span><span className="block text-sm font-medium">{zh ? "公开分享链接" : "Public share links"}</span><span className="mt-0.5 block text-xs text-[var(--muted)]">{zh ? "允许无需登录即可查看公开分享的对话。" : "Allow public conversation links to be viewed without signing in."}</span></span>
              <Switch checked={publicSharing} />
            </button>
            <label className="flex items-center justify-between gap-6 px-5 py-4">
              <span><span className="block text-sm font-medium">{zh ? "单文件上传上限" : "Maximum upload size"}</span><span className="mt-0.5 block text-xs text-[var(--muted)]">{zh ? "范围 1–500 MB，对对话附件和资料库上传同时生效。" : "1–500 MB, applied to chat attachments and library uploads."}</span></span>
              <span className="flex items-center gap-2"><input aria-label={zh ? "上传上限" : "Upload limit"} type="number" min={1} max={500} value={controls.policies.max_upload_mb} onChange={(e) => setControls({ ...controls, policies: { ...controls.policies, max_upload_mb: Math.max(1, Math.min(500, Number(e.target.value) || 1)) } })} className="w-24 rounded-xl border border-[var(--border)] bg-transparent px-3 py-2 text-right text-sm" /><span className="text-xs text-[var(--muted)]">MB</span></span>
            </label>
          </div>
        </section>
      </div>
    </div>
  );
}

function Switch({ checked }: { checked: boolean }) {
  return <span aria-hidden="true" className={cn("relative h-6 w-11 shrink-0 rounded-full transition-colors", checked ? "bg-[var(--fg)]" : "bg-[var(--border)]")}><span className={cn("absolute top-1 h-4 w-4 rounded-full bg-[var(--bg)] shadow-sm transition-transform", checked ? "translate-x-6" : "translate-x-1")} /></span>;
}
