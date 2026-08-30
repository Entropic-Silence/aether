"use client";

import { useEffect, useState } from "react";
import { phase8Api } from "@/lib/api";
import { Markdown } from "@/components/Markdown";
import { Spinner } from "@/components/ui";

export default function SharePage({ params }: { params: { token: string } }) {
  const [data, setData] = useState<{ id: string; title: string; messages: { id: string; role: string; blocks: { type: string; data: Record<string, unknown> }[] }[] } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    phase8Api.getSharedConversation(params.token).then(setData).catch((e) =>
      setError(e instanceof Error ? e.message : "Not found"));
  }, [params.token]);

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center text-[var(--muted)]">
        <div className="text-center">
          <div className="text-lg font-medium">This share isn&apos;t available</div>
          <div className="mt-1 text-sm">{error}</div>
        </div>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner className="h-6 w-6 text-[var(--muted)]" />
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-10">
      <h1 className="mb-6 text-xl font-semibold">{data.title}</h1>
      <div className="space-y-6">
        {data.messages.map((m) => (
          <div key={m.id} className={m.role === "user" ? "flex justify-end" : ""}>
            {m.role === "user" ? (
              <div className="max-w-[85%] whitespace-pre-wrap rounded-3xl bg-[var(--surface)] px-5 py-2.5 text-[15px]">
                {m.blocks.filter((b) => b.type === "text").map((b) => (b.data.text as string) ?? "").join("\n")}
              </div>
            ) : (
              <div className="w-full">
                {m.blocks.map((b, i) => {
                  if (b.type === "markdown") return <Markdown key={i} content={(b.data.text as string) ?? ""} />;
                  if (b.type === "reasoning") {
                    return <div key={i} className="mb-2 text-sm italic text-[var(--muted)]">Thought for a moment</div>;
                  }
                  return null;
                })}
              </div>
            )}
          </div>
        ))}
      </div>
      <p className="mt-10 text-center text-xs text-[var(--muted)]">Shared conversation</p>
    </div>
  );
}
