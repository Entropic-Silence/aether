import { spawn } from "child_process";
import { mkdirSync, writeFileSync } from "fs";
import path from "path";

const API = process.env.E2E_API_URL || "http://127.0.0.1:8123";
const BASE = process.env.E2E_BASE_URL || "http://127.0.0.1:3000";
const MOCK_PORT = Number(process.env.E2E_MOCK_PORT || 8300);
// Dev owner credentials (created by earlier setup on this host). Falls back to
// registering a fresh owner if these are unavailable.
const EMAIL = process.env.E2E_EMAIL || "admin@example.com";
const PASSWORD = process.env.E2E_PASSWORD || "adminpass123";

async function waitFor(url: string, tries = 60): Promise<void> {
  for (let i = 0; i < tries; i++) {
    try {
      const res = await fetch(url);
      if (res.ok) return;
    } catch {
      /* retry */
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`Timed out waiting for ${url}`);
}

async function api(path: string, token: string | null, method = "GET", body?: unknown) {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${API}/api/v1${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  return { status: res.status, body: text ? JSON.parse(text) : null };
}

export default async function globalSetup() {
  // Start the mock LLM.
  const mock = spawn("python3", [path.resolve(__dirname, "../../../scripts/e2e_mock_llm.py"), "--port", String(MOCK_PORT)], {
    stdio: "ignore",
    detached: true,
  });
  mock.unref();
  process.env.E2E_MOCK_PID = String(mock.pid);

  await waitFor(`${API}/api/health`);

  // Login as the dev owner; register first if not present.
  let token: string;
  let login = await api("/auth/login", null, "POST", { email: EMAIL, password: PASSWORD });
  if (login.status === 200) {
    token = login.body.access_token;
  } else {
    const reg = await api("/auth/register", null, "POST", { email: EMAIL, password: PASSWORD, name: "E2E Owner" });
    if (reg.status !== 200) throw new Error(`register failed: ${JSON.stringify(reg.body)}`);
    token = reg.body.access_token;
  }

  // Ensure a mock provider + tool-capable model exist.
  const providers = await api("/providers", token);
  let provider = (providers.body as Array<{ id: string; name: string }>).find((p) => p.name === "E2E Mock");
  if (!provider) {
    const created = await api("/providers", token, "POST", {
      name: "E2E Mock",
      base_url: `http://127.0.0.1:${MOCK_PORT}/v1`,
      kind: "openai_compatible",
    });
    provider = created.body;
  }
  const models = await api("/models", token);
  const existing = (models.body as Array<{ id: string; model_id: string }>).find((m) => m.model_id === "mock-tool");
  if (!existing) {
    await api("/models", token, "POST", {
      provider_id: provider!.id,
      model_id: "mock-tool",
      display_name: "E2E Mock Model",
      is_default: true,
      enabled: true,
      capabilities: {
        text_input: true, text_output: true, streaming: true,
        system_prompt: true, tool_calling: true, reasoning: true,
      },
    });
  } else {
    // Ensure the E2E model is enabled and the default for deterministic E2E runs.
    await api(`/models/${existing.id}`, token, "PATCH", { is_default: true, enabled: true });
  }

  // Keep an enabled image model in the catalog so image-related prompts take
  // the AI intent-routing path during browser tests. No generation is invoked.
  const imageModels = await api("/images/models", token);
  const imageRouter = (imageModels.body as Array<{ id: string; name: string }>).find((m) => m.name === "E2E Image Router");
  if (!imageRouter) {
    await api("/images/models", token, "POST", {
      provider_kind: "diffusers_local",
      name: "E2E Image Router",
      model_ref: "/nonexistent/e2e-image-model",
      is_default: true,
      enabled: true,
    });
  }

  // Persist auth as storage state (token in localStorage).
  const dir = path.resolve(__dirname, ".auth");
  mkdirSync(dir, { recursive: true });
  writeFileSync(
    path.join(dir, "state.json"),
    JSON.stringify({
      cookies: [],
      origins: [
        {
          origin: BASE,
          localStorage: [{ name: "aether_token", value: token }],
        },
      ],
    }),
  );
}
