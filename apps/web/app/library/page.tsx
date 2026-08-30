"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Download, FileText, Film, Image as ImageIcon, Loader2, Music, Pencil, Search, Trash2 } from "lucide-react";
import { api, getToken } from "@/lib/api";
import type { FileMeta } from "@/lib/types";
import { AuthImage } from "@/components/AuthImage";
import { IconBtn, Spinner } from "@/components/ui";

function kindIcon(kind: string) {
  if (kind === "image") return <ImageIcon size={18} />;
  if (kind === "audio") return <Music size={18} />;
  if (kind === "video") return <Film size={18} />;
  return <FileText size={18} />;
}

function fmtSize(bytes: number): string {
  if (!bytes) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export default function LibraryPage() {
  const [files, setFiles] = useState<FileMeta[] | null>(null);
  const [q, setQ] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [renaming, setRenaming] = useState<{ id: string; name: string } | null>(null);

  const load = useCallback(() => {
    api.listFiles(q).then(setFiles).catch(() => setFiles([]));
  }, [q]);

  useEffect(() => {
    if (!getToken()) {
      window.location.href = "/login";
      return;
    }
    const t = setTimeout(load, 200);
    return () => clearTimeout(t);
  }, [load]);

  const download = async (f: FileMeta) => {
    const token = getToken();
    const res = await fetch(api.fileDownloadUrl(f.id), { headers: { Authorization: `Bearer ${token}` } });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = f.name;
    a.click();
    URL.revokeObjectURL(url);
  };

  const saveRename = async () => {
    if (!renaming) return;
    setBusyId(renaming.id);
    try {
      await api.renameFile(renaming.id, renaming.name);
      setRenaming(null);
      load();
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-8">
      <Link href="/" className="mb-6 inline-flex items-center gap-1.5 text-sm text-[var(--muted)] hover:text-[var(--fg)]">
        <ArrowLeft size={15} /> Back to chat
      </Link>
      <div className="mb-4 flex items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">Library</h1>
        <div className="flex items-center gap-2 rounded-xl border border-[var(--border)] px-3 py-1.5">
          <Search size={14} className="text-[var(--muted)]" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search files" className="bg-transparent text-sm outline-none" />
        </div>
      </div>

      {!files ? (
        <Spinner className="h-6 w-6 text-[var(--muted)]" />
      ) : files.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-[var(--border)] p-10 text-center text-sm text-[var(--muted)]">
          No files yet. Attach files in a chat — they are stored here automatically.
        </div>
      ) : (
        <div className="space-y-2">
          {files.map((f) => (
            <div key={f.id} className="flex items-center justify-between rounded-xl border border-[var(--border)] px-4 py-3">
              <div className="flex min-w-0 items-center gap-3">
                {f.kind === "image" ? (
                  <AuthImage src={api.fileDownloadUrl(f.id)} alt="" className="h-10 w-10 rounded-lg object-cover" />
                ) : (
                  <span className="text-[var(--muted)]">{kindIcon(f.kind)}</span>
                )}
                <div className="min-w-0">
                  {renaming?.id === f.id ? (
                    <input
                      autoFocus
                      value={renaming.name}
                      onChange={(e) => setRenaming({ id: f.id, name: e.target.value })}
                      onKeyDown={(e) => e.key === "Enter" && saveRename()}
                      onBlur={saveRename}
                      className="rounded border border-[var(--border)] bg-transparent px-2 py-0.5 text-sm outline-none"
                    />
                  ) : (
                    <div className="truncate text-sm font-medium">{f.name}</div>
                  )}
                  <div className="text-xs text-[var(--muted)]">
                    {fmtSize(f.size)} · {f.status}
                    {f.extraction.indexed_chunks > 0 && ` · ${f.extraction.indexed_chunks} chunks indexed`}
                  </div>
                  {f.extraction.notices.map((n, i) => (
                    <div key={i} className="text-xs text-amber-600">{n}</div>
                  ))}
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-0.5">
                {busyId === f.id ? (
                  <Loader2 size={16} className="animate-spin text-[var(--muted)]" />
                ) : (
                  <>
                    <IconBtn title="Download" onClick={() => download(f)}><Download size={15} /></IconBtn>
                    <IconBtn title="Rename" onClick={() => setRenaming({ id: f.id, name: f.name })}><Pencil size={15} /></IconBtn>
                    <IconBtn title="Delete" onClick={async () => { setBusyId(f.id); await api.deleteFile(f.id); setBusyId(null); load(); }}>
                      <Trash2 size={15} />
                    </IconBtn>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
