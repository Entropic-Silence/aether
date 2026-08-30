"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Check, MessageSquare, Pencil, Plus } from "lucide-react";
import { api, getToken } from "@/lib/api";
import type { FileMeta, ProjectMeta } from "@/lib/types";
import { AuthImage } from "@/components/AuthImage";
import { Button, IconBtn, Spinner } from "@/components/ui";

export default function ProjectDetailPage({ params }: { params: { id: string } }) {
  const [project, setProject] = useState<ProjectMeta | null>(null);
  const [files, setFiles] = useState<FileMeta[]>([]);
  const [chats, setChats] = useState<{ id: string; title: string; updated_at: string; pinned: boolean }[]>([]);
  const [library, setLibrary] = useState<FileMeta[]>([]);
  const [editingInstructions, setEditingInstructions] = useState(false);
  const [instructions, setInstructions] = useState("");
  const [addingFiles, setAddingFiles] = useState(false);
  const [allChats, setAllChats] = useState<{ id: string; title: string; project_id: string | null }[]>([]);
  const [movingChat, setMovingChat] = useState(false);

  const load = useCallback(async () => {
    try {
      const [p, f, c] = await Promise.all([
        api.getProject(params.id),
        api.projectFiles(params.id),
        api.projectConversations(params.id),
      ]);
      setProject(p);
      setInstructions(p.instructions);
      setFiles(f);
      setChats(c);
    } catch {
      /* not found */
    }
  }, [params.id]);

  useEffect(() => {
    if (!getToken()) {
      window.location.href = "/login";
      return;
    }
    load();
  }, [load]);

  const saveInstructions = async () => {
    if (!project) return;
    const updated = await api.updateProject(project.id, { instructions });
    setProject(updated);
    setEditingInstructions(false);
  };

  const openAddFiles = async () => {
    setLibrary(await api.listFiles());
    setAddingFiles(true);
  };

  const openMoveChat = async () => {
    const list = await api.listConversations();
    setAllChats(list.filter((c) => c.project_id !== params.id));
    setMovingChat(true);
  };

  if (!project) {
    return <div className="p-8"><Spinner className="h-6 w-6 text-[var(--muted)]" /></div>;
  }

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-8">
      <Link href="/projects" className="mb-6 inline-flex items-center gap-1.5 text-sm text-[var(--muted)] hover:text-[var(--fg)]">
        <ArrowLeft size={15} /> Projects
      </Link>

      <div className="mb-1 flex items-center gap-2">
        <span className="text-2xl">{project.icon || "📁"}</span>
        <h1 className="text-xl font-semibold">{project.name}</h1>
      </div>
      {project.description && <p className="mb-4 text-sm text-[var(--muted)]">{project.description}</p>}

      <section className="mb-6 rounded-xl border border-[var(--border)] p-4">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold">Project instructions</h2>
          {!editingInstructions ? (
            <IconBtn title="Edit" onClick={() => setEditingInstructions(true)}><Pencil size={15} /></IconBtn>
          ) : (
            <Button variant="primary" onClick={saveInstructions} className="!px-2 !py-1"><Check size={14} /> Save</Button>
          )}
        </div>
        {editingInstructions ? (
          <textarea value={instructions} onChange={(e) => setInstructions(e.target.value)} rows={4}
            placeholder="Injected into every chat in this project…"
            className="w-full rounded-lg border border-[var(--border)] bg-transparent px-3 py-2 text-sm outline-none focus:border-accent" />
        ) : (
          <p className="whitespace-pre-wrap text-sm text-[var(--muted)]">
            {project.instructions || "No instructions yet. Instructions are added to the system prompt of every chat in this project."}
          </p>
        )}
      </section>

      <section className="mb-6">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold">Files ({files.length})</h2>
          <Button onClick={openAddFiles}><Plus size={14} /> Add from Library</Button>
        </div>
        {files.length === 0 ? (
          <div className="rounded-xl border border-dashed border-[var(--border)] p-6 text-center text-sm text-[var(--muted)]">
            No files in this project.
          </div>
        ) : (
          <div className="space-y-2">
            {files.map((f) => (
              <div key={f.id} className="flex items-center justify-between rounded-lg border border-[var(--border)] px-3 py-2">
                <div className="flex min-w-0 items-center gap-2">
                  {f.kind === "image" ? (
                    <AuthImage src={api.fileDownloadUrl(f.id)} alt="" className="h-8 w-8 rounded object-cover" />
                  ) : (
                    <span className="text-[var(--muted)]">📄</span>
                  )}
                  <span className="truncate text-sm">{f.name}</span>
                </div>
                <span className="text-xs text-[var(--muted)]">{f.status}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      <section>
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold">Chats ({chats.length})</h2>
          <Button onClick={openMoveChat}><Plus size={14} /> Move chat here</Button>
        </div>
        {chats.length === 0 ? (
          <div className="rounded-xl border border-dashed border-[var(--border)] p-6 text-center text-sm text-[var(--muted)]">
            No chats yet. Use "Move chat here" or start a new chat and assign it.
          </div>
        ) : (
          <div className="space-y-1">
            {chats.map((c) => (
              <Link key={c.id} href={`/c/${c.id}`}
                className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm hover:bg-[var(--surface)]">
                <MessageSquare size={14} className="text-[var(--muted)]" />
                <span className="truncate">{c.title}</span>
              </Link>
            ))}
          </div>
        )}
      </section>

      {addingFiles && (
        <Modal onClose={() => setAddingFiles(false)} title="Add files from Library">
          {library.length === 0 ? (
            <p className="text-sm text-[var(--muted)]">Library is empty.</p>
          ) : (
            <div className="max-h-72 space-y-1 overflow-y-auto">
              {library.map((f) => (
                <button key={f.id} type="button"
                  onClick={async () => { await api.addFileToProject(project.id, f.id); setAddingFiles(false); load(); }}
                  className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm hover:bg-[var(--surface)]">
                  <span className="truncate">{f.name}</span>
                </button>
              ))}
            </div>
          )}
        </Modal>
      )}

      {movingChat && (
        <Modal onClose={() => setMovingChat(false)} title="Move a chat to this project">
          {allChats.length === 0 ? (
            <p className="text-sm text-[var(--muted)]">No other chats available.</p>
          ) : (
            <div className="max-h-72 space-y-1 overflow-y-auto">
              {allChats.map((c) => (
                <button key={c.id} type="button"
                  onClick={async () => { await api.updateConversation(c.id, { project_id: project.id }); setMovingChat(false); load(); }}
                  className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm hover:bg-[var(--surface)]">
                  <span className="truncate">{c.title || "New chat"}</span>
                </button>
              ))}
            </div>
          )}
        </Modal>
      )}
    </div>
  );
}

function Modal({ children, onClose, title }: { children: React.ReactNode; onClose: () => void; title: string }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div className="w-full max-w-md rounded-2xl bg-[var(--bg)] p-5" onClick={(e) => e.stopPropagation()}>
        <h2 className="mb-3 text-sm font-semibold">{title}</h2>
        {children}
      </div>
    </div>
  );
}
