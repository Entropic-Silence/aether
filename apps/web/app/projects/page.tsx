"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, FolderKanban, Plus, Trash2, X } from "lucide-react";
import { api, getToken } from "@/lib/api";
import type { ProjectMeta } from "@/lib/types";
import { Button, IconBtn, Spinner } from "@/components/ui";

export default function ProjectsPage() {
  const [projects, setProjects] = useState<ProjectMeta[] | null>(null);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  const load = useCallback(() => {
    api.listProjects().then(setProjects).catch(() => setProjects([]));
  }, []);

  useEffect(() => {
    if (!getToken()) {
      window.location.href = "/login";
      return;
    }
    load();
  }, [load]);

  const create = async () => {
    if (!name.trim()) return;
    await api.createProject({ name: name.trim(), description });
    setName("");
    setDescription("");
    setCreating(false);
    load();
  };

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-8">
      <Link href="/" className="mb-6 inline-flex items-center gap-1.5 text-sm text-[var(--muted)] hover:text-[var(--fg)]">
        <ArrowLeft size={15} /> Back to chat
      </Link>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold">Projects</h1>
        <Button variant="primary" onClick={() => setCreating(true)}>
          <Plus size={15} /> New project
        </Button>
      </div>

      {creating && (
        <div className="mb-6 rounded-xl border border-[var(--border)] p-4">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold">New project</h2>
            <IconBtn onClick={() => setCreating(false)}><X size={16} /></IconBtn>
          </div>
          <div className="space-y-3">
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Project name"
              className="w-full rounded-lg border border-[var(--border)] bg-transparent px-3 py-2 text-sm outline-none focus:border-accent" />
            <input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Description (optional)"
              className="w-full rounded-lg border border-[var(--border)] bg-transparent px-3 py-2 text-sm outline-none focus:border-accent" />
          </div>
          <div className="mt-3 flex gap-2">
            <Button variant="primary" onClick={create} disabled={!name.trim()}>Create</Button>
            <Button onClick={() => setCreating(false)}>Cancel</Button>
          </div>
        </div>
      )}

      {!projects ? (
        <Spinner className="h-6 w-6 text-[var(--muted)]" />
      ) : projects.length === 0 && !creating ? (
        <div className="rounded-2xl border border-dashed border-[var(--border)] p-10 text-center text-sm text-[var(--muted)]">
          <FolderKanban className="mx-auto mb-2" size={22} />
          No projects yet. Group chats, files, and instructions into a project.
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {projects.map((p) => (
            <div key={p.id} className="group flex items-start justify-between rounded-xl border border-[var(--border)] p-4 transition-colors hover:bg-[var(--surface)]">
              <Link href={`/projects/${p.id}`} className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-lg">{p.icon || "📁"}</span>
                  <span className="truncate font-medium">{p.name}</span>
                </div>
                {p.description && <div className="mt-1 line-clamp-2 text-xs text-[var(--muted)]">{p.description}</div>}
                <div className="mt-2 text-xs text-[var(--muted)]">{p.chat_count} chats · {p.file_count} files</div>
              </Link>
              <IconBtn title="Delete" className="opacity-0 group-hover:opacity-100"
                onClick={async () => { await api.deleteProject(p.id); load(); }}>
                <Trash2 size={15} />
              </IconBtn>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
