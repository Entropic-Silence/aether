"use client";

import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent",
        className,
      )}
      aria-label="Loading"
    />
  );
}

export function Button({
  children,
  onClick,
  variant = "secondary",
  className,
  disabled,
  type = "button",
  title,
}: {
  children: React.ReactNode;
  onClick?: () => void;
  variant?: "primary" | "secondary" | "ghost" | "danger";
  className?: string;
  disabled?: boolean;
  type?: "button" | "submit";
  title?: string;
}) {
  const base =
    "inline-flex items-center justify-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed";
  const variants = {
    primary: "bg-[var(--fg)] text-[var(--bg)] hover:opacity-90",
    secondary:
      "bg-[var(--surface)] text-[var(--fg)] hover:bg-[var(--border)]",
    ghost: "text-[var(--fg)] hover:bg-[var(--surface)]",
    danger: "bg-red-600 text-white hover:bg-red-700",
  } as const;
  return (
    <button type={type} title={title} disabled={disabled} onClick={onClick} className={cn(base, variants[variant], className)}>
      {children}
    </button>
  );
}

export function IconBtn({
  children,
  onClick,
  className,
  title,
  active,
}: {
  children: React.ReactNode;
  onClick?: () => void;
  className?: string;
  title?: string;
  active?: boolean;
}) {
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      className={cn(
        "inline-flex h-9 w-9 items-center justify-center rounded-lg text-[var(--muted)] transition-colors hover:bg-[var(--surface)] hover:text-[var(--fg)]",
        active && "bg-[var(--surface)] text-[var(--fg)]",
        className,
      )}
    >
      {children}
    </button>
  );
}
