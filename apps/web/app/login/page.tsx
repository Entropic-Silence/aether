"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, setToken } from "@/lib/api";
import { useApp } from "@/lib/hooks";
import { Button, Spinner } from "@/components/ui";

export default function LoginPage() {
  const router = useRouter();
  const { setUser, branding, t, user, authReady } = useApp();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    if (!authReady) return;
    if (user) {
      router.replace("/");
      return;
    }
    setChecking(false);
  }, [router, user, authReady]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res =
        mode === "login"
          ? await api.login(email, password)
          : await api.register(email, password, name);
      setToken(res.access_token);
      setUser(res.user);
      router.replace("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : t("authFailed", "Authentication failed"));
    } finally {
      setBusy(false);
    }
  };

  if (checking) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner className="h-6 w-6 text-[var(--muted)]" />
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-accent text-lg font-bold text-white">
            {(branding?.product_name ?? "A").slice(0, 1)}
          </div>
          <h1 className="text-2xl font-semibold">{branding?.product_name ?? "Aether"}</h1>
        </div>

        <form onSubmit={submit} className="space-y-3">
          {mode === "register" && (
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("name", "Name")}
              className="w-full rounded-xl border border-[var(--border)] bg-transparent px-4 py-2.5 text-sm outline-none focus:border-accent"
            />
          )}
          <input
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            type="email"
            required
            placeholder={t("email", "Email")}
            aria-label={t("email", "Email")}
            className="w-full rounded-xl border border-[var(--border)] bg-transparent px-4 py-2.5 text-sm outline-none focus:border-accent"
          />
          <input
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            type="password"
            required
            minLength={8}
            placeholder={t("password", "Password")}
            aria-label={t("password", "Password")}
            className="w-full rounded-xl border border-[var(--border)] bg-transparent px-4 py-2.5 text-sm outline-none focus:border-accent"
          />
          {error && <div className="text-sm text-red-500">{error}</div>}
          <Button type="submit" variant="primary" className="w-full" disabled={busy}>
            {busy ? <Spinner /> : mode === "login" ? t("continue", "Continue") : t("createAccount", "Create account")}
          </Button>
        </form>

        <button
          type="button"
          onClick={() => {
            setMode(mode === "login" ? "register" : "login");
            setError(null);
          }}
          className="mt-4 w-full text-center text-sm text-[var(--muted)] hover:text-[var(--fg)]"
        >
          {mode === "login"
            ? t("firstTime", "First time here? Create the owner account")
            : t("alreadyAccount", "Already have an account? Log in")}
        </button>
        <p className="mt-6 text-center text-xs text-[var(--muted)]">
          {t("firstOwner", "The first registered account becomes the workspace owner.")}
        </p>
      </div>
    </div>
  );
}
