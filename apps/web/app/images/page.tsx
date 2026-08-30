"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Download, Image as ImageIcon, Trash2 } from "lucide-react";
import { api, getToken } from "@/lib/api";
import type { FileMeta } from "@/lib/types";
import { AuthImage } from "@/components/AuthImage";
import { IconBtn, Spinner } from "@/components/ui";

export default function ImagesPage() {
  const [files, setFiles] = useState<FileMeta[] | null>(null);
  const [q, setQ] = useState("");

  const load = useCallback(() => {
    api.listFiles(q).then((all) => setFiles(all.filter((f) => f.kind === "image")));
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

  return (
    <div className="mx-auto w-full max-w-4xl px-4 py-8">
      <Link href="/" className="mb-6 inline-flex items-center gap-1.5 text-sm text-[var(--muted)] hover:text-[var(--fg)]">
        <ArrowLeft size={15} /> Back to chat
      </Link>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold">Images</h1>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search by name"
          className="rounded-xl border border-[var(--border)] bg-transparent px-3 py-1.5 text-sm outline-none focus:border-accent"
        />
      </div>

      {!files ? (
        <Spinner className="h-6 w-6 text-[var(--muted)]" />
      ) : files.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-[var(--border)] p-12 text-center text-sm text-[var(--muted)]">
          <ImageIcon className="mx-auto mb-2" size={22} />
          No images yet. Use “Create image” in the composer.
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
          {files.map((f) => (
            <div key={f.id} className="group overflow-hidden rounded-xl border border-[var(--border)]">
              <div className="relative aspect-square bg-[var(--surface)]">
                <AuthImage src={api.fileDownloadUrl(f.id)} alt={f.name} className="h-full w-full object-cover" />
                <div className="absolute inset-x-0 bottom-0 flex justify-end gap-0.5 bg-gradient-to-t from-black/60 to-transparent p-1.5 opacity-0 transition-opacity group-hover:opacity-100">
                  <IconBtn title="Download" onClick={() => download(f)} className="h-7 w-7 bg-black/30 text-white hover:bg-black/50">
                    <Download size={14} />
                  </IconBtn>
                  <IconBtn title="Delete" onClick={async () => { await api.deleteFile(f.id); load(); }} className="h-7 w-7 bg-black/30 text-white hover:bg-black/50">
                    <Trash2 size={14} />
                  </IconBtn>
                </div>
              </div>
              <div className="truncate px-2.5 py-1.5 text-xs">{f.name}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
