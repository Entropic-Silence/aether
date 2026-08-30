"use client";

import { memo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import rehypeHighlight from "rehype-highlight";
import { Check, Copy, Download } from "lucide-react";
import { AuthImage } from "./AuthImage";
import { api, getToken } from "@/lib/api";

export const SANDBOX_FILE_SCHEME = "sandbox-file:";

function AuthDownloadLink({ fileId, name, children }: { fileId: string; name: string; children: React.ReactNode }) {
  const download = async () => {
    const token = getToken();
    const response = await fetch(api.fileDownloadUrl(fileId), { headers: token ? { Authorization: `Bearer ${token}` } : {} });
    if (!response.ok) return;
    const url = URL.createObjectURL(await response.blob());
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = name;
    anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return <button type="button" onClick={() => void download()} className="inline-flex items-center gap-1 text-accent underline"><Download size={13} />{children}</button>;
}

function CodeBlock({ children, language }: { children: React.ReactNode; language?: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    const text = String(children).replace(/\n$/, "");
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <div className="my-3 overflow-hidden rounded-xl border border-[var(--border)]">
      <div className="flex items-center justify-between bg-[#1a1a1a] px-4 py-1.5 text-xs text-gray-300">
        <span>{language || "code"}</span>
        <button type="button" onClick={copy} className="flex items-center gap-1 hover:text-white">
          {copied ? <Check size={13} /> : <Copy size={13} />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="!m-0 !rounded-none">{children}</pre>
    </div>
  );
}

export const Markdown = memo(function Markdown({
  content,
  sandboxFiles,
}: {
  content: string;
  sandboxFiles?: Record<string, string>;
}) {
  return (
    <div className="prose-chat text-[15px]">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex, rehypeHighlight]}
        components={{
          pre({ children }) {
            return <>{children}</>;
          },
          code({ className, children, ...rest }) {
            const match = /language-(\w+)/.exec(className || "");
            const text = String(children).replace(/\n$/, "");
            if (!match && !text.includes("\n")) {
              return (
                <code className={className} {...rest}>
                  {children}
                </code>
              );
            }
            return (
              <CodeBlock language={match?.[1]}>
                <code className={className}>{children}</code>
              </CodeBlock>
            );
          },
          a({ href, children }) {
            if (href?.startsWith(SANDBOX_FILE_SCHEME)) {
              const name = href.slice(SANDBOX_FILE_SCHEME.length);
              const fileId = sandboxFiles?.[name];
              if (fileId) return <AuthDownloadLink fileId={fileId} name={name}>{children}</AuthDownloadLink>;
            }
            return (
              <a href={href} target="_blank" rel="noopener noreferrer">
                {children}
              </a>
            );
          },
          img({ src, alt }) {
            if (src?.startsWith(SANDBOX_FILE_SCHEME)) {
              const name = src.slice(SANDBOX_FILE_SCHEME.length);
              const fileId = sandboxFiles?.[name];
              if (fileId) {
                return (
                  <AuthImage
                    src={`/api/v1/files/${fileId}/download`}
                    alt={alt ?? name}
                    className="my-2 max-h-96 rounded-xl border border-[var(--border)]"
                  />
                );
              }
              return <span className="text-xs text-[var(--muted)]">[image: {name}]</span>;
            }
            // eslint-disable-next-line @next/next/no-img-element
            return <img src={src} alt={alt ?? ""} className="my-2 max-h-96 rounded-xl" />;
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
});
