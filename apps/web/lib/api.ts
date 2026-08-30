import type { ArtifactInfo, Branding, Conversation, FeatureControls, FileMeta, ImageGenerationResult, ImageModelInfo, ImagePromptOptimization, McpServerInfo, MemoryInfo, Message, MessageBranch, ModelInfo, PluginInfo, ProjectMeta, PromptInfo, Provider, SkillInfo, TaskInfo, TaskRunInfo, UiSettings, User, UserPrefInfo } from "./types";

export const TOKEN_KEY = "aether_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (typeof window === "undefined") return;
  if (token) window.localStorage.setItem(TOKEN_KEY, token);
  else window.localStorage.removeItem(TOKEN_KEY);
  window.dispatchEvent(new Event("aether:auth-changed"));
}

export class ApiError extends Error {
  status: number;
  code: string;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`/api/v1${path}`, { ...options, headers });
  if (res.status === 401 && typeof window !== "undefined") {
    setToken(null);
    window.location.href = "/login";
    throw new ApiError(401, "AUTH_ERROR", "Not authenticated");
  }
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const err = body?.error;
    throw new ApiError(res.status, err?.code ?? "INTERNAL_ERROR", err?.message ?? `Request failed (${res.status})`);
  }
  return body as T;
}

export const api = {
  register: (email: string, password: string, name: string) =>
    request<{ access_token: string; user: User }>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, name }),
    }),
  login: (email: string, password: string) =>
    request<{ access_token: string; user: User }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  me: () => request<User>("/auth/me"),

  branding: () => request<Branding>("/branding"),
  updateBranding: (patch: Partial<Branding>) =>
    request<Branding>("/branding", { method: "PATCH", body: JSON.stringify(patch) }),

  listProviders: () => request<Provider[]>("/providers"),
  createProvider: (body: unknown) =>
    request<Provider>("/providers", { method: "POST", body: JSON.stringify(body) }),
  updateProvider: (id: string, body: unknown) =>
    request<Provider>(`/providers/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteProvider: (id: string) => request<void>(`/providers/${id}`, { method: "DELETE" }),
  testProvider: (id: string) => request<{ ok: boolean; models?: string[]; error?: unknown }>(`/providers/${id}/test`, { method: "POST" }),
  remoteModels: (id: string) => request<string[]>(`/providers/${id}/remote-models`),

  listModels: () => request<ModelInfo[]>("/models"),
  catalogModels: () => request<ModelInfo[]>("/catalog/models"),
  createModel: (body: unknown) => request<ModelInfo>("/models", { method: "POST", body: JSON.stringify(body) }),
  updateModel: (id: string, body: unknown) =>
    request<ModelInfo>(`/models/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteModel: (id: string) => request<void>(`/models/${id}`, { method: "DELETE" }),
  probeModel: (id: string) => request<ModelInfo>(`/models/${id}/probe`, { method: "POST" }),
  testModel: (id: string, prompt: string) =>
    request<{ ok: boolean; text?: string; error?: unknown; latency_ms?: number; usage?: unknown }>(
      `/models/${id}/test?prompt=${encodeURIComponent(prompt)}`,
      { method: "POST" },
    ),

  listConversations: () => request<Conversation[]>("/conversations"),
  createConversation: (body: Partial<Conversation>) =>
    request<Conversation>("/conversations", { method: "POST", body: JSON.stringify(body) }),
  getConversation: (id: string) => request<Conversation>(`/conversations/${id}`),
  updateConversation: (id: string, patch: Partial<Conversation>) =>
    request<Conversation>(`/conversations/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
  deleteConversation: (id: string) => request<void>(`/conversations/${id}`, { method: "DELETE" }),
  getMessages: (id: string) => request<Message[]>(`/conversations/${id}/messages?active_only=true`),
  getMessageBranches: (id: string) => request<MessageBranch[]>(`/conversations/${id}/branches`),
  activateMessageBranch: (conversationId: string, messageId: string) =>
    request<{ ok: boolean }>(`/conversations/${conversationId}/branches/${messageId}/activate`, { method: "POST" }),
  updateMessageText: (conversationId: string, messageId: string, text: string) =>
    request<{ ok: boolean }>(`/conversations/${conversationId}/messages/${messageId}`, {
      method: "PATCH", body: JSON.stringify({ text }),
    }),
  recordConversationError: (conversationId: string, body: {
    content: string; message: string; code?: string; retry_kind?: string;
    model_id?: string | null; parent_user_message_id?: string | null; duration_ms?: number;
  }) => request<{ ok: boolean; assistant_message_id: string }>(`/conversations/${conversationId}/errors`, {
    method: "POST", body: JSON.stringify(body),
  }),
  cancelConversationRun: (conversationId: string, messageId: string) =>
    request<{ ok: boolean; active: boolean }>(`/conversations/${conversationId}/runs/${messageId}/cancel`, { method: "POST" }),

  uploadFile: async (file: File): Promise<FileMeta> => {
    const form = new FormData();
    form.append("upload", file);
    const headers: Record<string, string> = {};
    const token = getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
    const res = await fetch("/api/v1/files", { method: "POST", headers, body: form });
    const body = await res.json().catch(() => null);
    if (!res.ok) {
      throw new ApiError(res.status, body?.error?.code ?? "FILE_ERROR", body?.error?.message ?? "Upload failed");
    }
    return body as FileMeta;
  },
  listFiles: (q = "") => request<FileMeta[]>(`/files?q=${encodeURIComponent(q)}`),
  getFile: (id: string) => request<FileMeta>(`/files/${id}`),
  filePreview: (id: string) => request<{ id: string; name: string; mime: string; mode: "pdf" | "svg" | "text"; text: string }>(`/files/${id}/preview`),
  renameFile: (id: string, name: string) =>
    request<FileMeta>(`/files/${id}`, { method: "PATCH", body: JSON.stringify({ name }) }),
  deleteFile: (id: string) => request<void>(`/files/${id}`, { method: "DELETE" }),
  fileDownloadUrl: (id: string) => `/api/v1/files/${id}/download`,

  listProjects: () => request<ProjectMeta[]>("/projects"),
  createProject: (body: { name: string; description?: string; instructions?: string }) =>
    request<ProjectMeta>("/projects", { method: "POST", body: JSON.stringify(body) }),
  getProject: (id: string) => request<ProjectMeta>(`/projects/${id}`),
  updateProject: (id: string, patch: Partial<ProjectMeta>) =>
    request<ProjectMeta>(`/projects/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
  deleteProject: (id: string) => request<void>(`/projects/${id}`, { method: "DELETE" }),
  projectConversations: (id: string) =>
    request<{ id: string; title: string; updated_at: string; pinned: boolean }[]>(`/projects/${id}/conversations`),
  projectFiles: (id: string) => request<FileMeta[]>(`/projects/${id}/files`),
  addFileToProject: (projectId: string, fileId: string) =>
    request<{ ok: boolean }>(`/projects/${projectId}/files/${fileId}`, { method: "POST" }),

  uiSettings: () => request<UiSettings>("/settings/ui"),
  featureControls: () => request<FeatureControls>("/settings/features"),
  updateFeatureControls: (patch: Partial<FeatureControls>) =>
    request<FeatureControls>("/settings/features", { method: "PATCH", body: JSON.stringify(patch) }),
  audioSettings: () => request<{ stt: Record<string, unknown>; tts: Record<string, unknown> }>("/audio/settings"),
  updateAudioSettings: (patch: { stt?: Record<string, unknown>; tts?: Record<string, unknown> }) =>
    request<{ ok: boolean }>("/audio/settings", { method: "PATCH", body: JSON.stringify(patch) }),
  sharingSettings: () => request<{ public_enabled: boolean }>("/shares/settings"),
  updateSharingSettings: (public_enabled: boolean) =>
    request<{ public_enabled: boolean }>("/shares/settings", { method: "PATCH", body: JSON.stringify({ public_enabled }) }),
  searchSettings: () => request<{ providers: Array<Record<string, unknown>> }>("/settings/search"),
  updateSearchSettings: (providers: Array<Record<string, unknown>>) =>
    request<{ ok: boolean; configured: boolean }>("/settings/search", {
      method: "PATCH",
      body: JSON.stringify({ providers }),
    }),
  testSearch: () =>
    request<{ ok: boolean; provider?: string; results?: { url: string; title: string }[]; error?: string }>(
      "/settings/search/test",
      { method: "POST" },
    ),
  retrievalSettings: () => request<Record<string, unknown>>("/settings/retrieval"),
  updateRetrievalSettings: (patch: Record<string, unknown>) =>
    request<Record<string, unknown>>("/settings/retrieval", { method: "PATCH", body: JSON.stringify(patch) }),
  visionFallback: () => request<{ model_id: string | null; display_name: string | null }>("/settings/vision-fallback"),
  updateVisionFallback: (model_id: string | null) =>
    request<unknown>("/settings/vision-fallback", { method: "PATCH", body: JSON.stringify({ model_id }) }),

  compute: () => request<import("./types").ComputeInfo>("/system/compute"),

  listImageModels: () => request<ImageModelInfo[]>("/images/models"),
  createImageModel: (body: Record<string, unknown>) =>
    request<ImageModelInfo>("/images/models", { method: "POST", body: JSON.stringify(body) }),
  updateImageModel: (id: string, patch: Record<string, unknown>) =>
    request<ImageModelInfo>(`/images/models/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
  deleteImageModel: (id: string) => request<void>(`/images/models/${id}`, { method: "DELETE" }),
  optimizeImagePrompt: (body: { prompt: string; model_id?: string | null; optimizer_model_id?: string | null; aspect_ratio?: string | null }) =>
    request<ImagePromptOptimization>("/images/prompts/optimize", { method: "POST", body: JSON.stringify(body) }),
  classifyImageIntent: (content: string, model_id?: string | null) =>
    request<{ image_request: boolean; source: string }>("/images/intents/classify", {
      method: "POST", body: JSON.stringify({ content, model_id }),
    }),
  generateImage: (body: {
    prompt: string;
    model_id?: string | null;
    width?: number;
    height?: number;
    steps?: number;
    cfg?: number;
    seed?: number | null;
    negative_prompt?: string;
    optimize?: boolean;
    mode?: string;
    source_file_id?: string | null;
    mask_file_id?: string | null;
    strength?: number;
    aspect_ratio?: string | null;
    admin_test?: boolean;
  }) => request<ImageGenerationResult>("/images/generations", { method: "POST", body: JSON.stringify(body) }),
  attachImageToConversation: (conversationId: string, fileId: string, prompt: string, details?: {
    prompt_used?: string; negative_prompt_used?: string; model_name?: string; parent_user_message_id?: string;
    aspect_ratio?: string; width?: number; height?: number;
  }) =>
    request<{ ok: boolean }>(`/images/conversations/${conversationId}/message`, {
      method: "POST",
      body: JSON.stringify({ file_id: fileId, prompt, ...details }),
    }),
};

export const phase6Api = {
  // MCP
  listMcpServers: () => request<McpServerInfo[]>("/mcp/servers"),
  createMcpServer: (body: Record<string, unknown>) =>
    request<McpServerInfo>("/mcp/servers", { method: "POST", body: JSON.stringify(body) }),
  updateMcpServer: (id: string, patch: Record<string, unknown>) =>
    request<McpServerInfo>(`/mcp/servers/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
  deleteMcpServer: (id: string) => request<void>(`/mcp/servers/${id}`, { method: "DELETE" }),
  testMcpServer: (id: string) =>
    request<{ ok: boolean; tool_count?: number; tools?: { name: string; description: string }[]; error?: string }>(
      `/mcp/servers/${id}/test`, { method: "POST" }),

  // Skills
  listSkills: () => request<SkillInfo[]>("/skills"),
  createSkill: (body: Record<string, unknown>) =>
    request<SkillInfo>("/skills", { method: "POST", body: JSON.stringify(body) }),
  updateSkill: (id: string, patch: Record<string, unknown>) =>
    request<SkillInfo>(`/skills/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
  deleteSkill: (id: string) => request<void>(`/skills/${id}`, { method: "DELETE" }),
  exportSkill: (id: string) => request<{ skill: Record<string, unknown> }>(`/skills/${id}/export`),
  importSkill: (skill: Record<string, unknown>) =>
    request<SkillInfo>("/skills/import", { method: "POST", body: JSON.stringify({ skill }) }),
  importMarkdownSkill: (filename: string, content: string) =>
    request<SkillInfo>("/skills/import-markdown", { method: "POST", body: JSON.stringify({ filename, content }) }),
  syncDeepSeekSkills: () =>
    request<{ ok: boolean; found: number; skills: string[] }>("/skills/sync-deepseek", { method: "POST" }),

  // Plugins
  listPlugins: () => request<{ plugins_dir: string; plugins: PluginInfo[] }>("/plugins"),
  setPluginEnabled: (id: string, enabled: boolean) =>
    request<{ ok: boolean }>("/plugins/enabled", { method: "PUT", body: JSON.stringify({ plugin_id: id, enabled }) }),
  importPlugin: async (file: File) => {
    const form = new FormData();
    form.append("upload", file);
    const headers: Record<string, string> = {};
    const token = getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
    const response = await fetch("/api/v1/plugins/import", { method: "POST", headers, body: form });
    const body = await response.json().catch(() => null);
    if (!response.ok) throw new ApiError(response.status, body?.error?.code ?? "PLUGIN_ERROR", body?.error?.message ?? "Plugin import failed");
    return body as { ok: boolean; plugin_id: string };
  },
  rescanPlugins: () =>
    request<{ ok: boolean; found: number }>("/plugins/rescan", { method: "POST" }),

  // Work mode
  startWork: (conversationId: string, body: { task: string; runtime?: string; model_id?: string | null; file_ids?: string[]; plugin_ids?: string[] }) =>
    request<{ run_id: string; assistant_message_id: string; status: string }>(
      `/conversations/${conversationId}/work`, { method: "POST", body: JSON.stringify(body) }),
  steerWork: (runId: string, content: string) =>
    request<{ ok: boolean }>(`/work/runs/${runId}/steer`, { method: "POST", body: JSON.stringify({ content }) }),
  cancelWork: (runId: string) =>
    request<{ ok: boolean }>(`/work/runs/${runId}/cancel`, { method: "POST" }),
  approveWorkTool: (runId: string, approvalId: string, decision: string, rule: string) =>
    request<{ ok: boolean }>(`/work/runs/${runId}/approvals`, {
      method: "POST", body: JSON.stringify({ approval_id: approvalId, decision, rule }) }),
  approveChatTool: (conversationId: string, approvalId: string, decision: string, rule: string) =>
    request<{ ok: boolean }>(`/conversations/${conversationId}/approvals`, {
      method: "POST", body: JSON.stringify({ approval_id: approvalId, decision, rule }) }),
  workRuns: (conversationId: string) =>
    request<{ id: string; task: string; status: string; runtime: string; assistant_message_id?: string | null }[]>(`/conversations/${conversationId}/work-runs`),
};

export const phase7Api = {
  // Memory
  listMemories: () => request<MemoryInfo[]>("/memories"),
  createMemory: (body: { content: string; category?: string; project_id?: string | null }) =>
    request<MemoryInfo>("/memories", { method: "POST", body: JSON.stringify(body) }),
  updateMemory: (id: string, patch: Record<string, unknown>) =>
    request<MemoryInfo>(`/memories/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
  deleteMemory: (id: string) => request<void>(`/memories/${id}`, { method: "DELETE" }),
  clearMemories: () => request<void>("/memories", { method: "DELETE" }),

  // User settings (custom instructions + memory toggles)
  getMySettings: () => request<UserPrefInfo>("/settings/me"),
  patchMySettings: (patch: Partial<UserPrefInfo>) =>
    request<UserPrefInfo>("/settings/me", { method: "PATCH", body: JSON.stringify(patch) }),

  // Tasks
  listTasks: () => request<TaskInfo[]>("/tasks"),
  createTask: (body: Record<string, unknown>) =>
    request<TaskInfo>("/tasks", { method: "POST", body: JSON.stringify(body) }),
  updateTask: (id: string, patch: Record<string, unknown>) =>
    request<TaskInfo>(`/tasks/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
  deleteTask: (id: string) => request<void>(`/tasks/${id}`, { method: "DELETE" }),
  runTask: (id: string) => request<{ ok: boolean }>(`/tasks/${id}/run`, { method: "POST" }),
  taskRuns: (id: string) => request<TaskRunInfo[]>(`/tasks/${id}/runs`),

  // Artifacts
  listArtifacts: (kind?: string) => request<ArtifactInfo[]>(kind ? `/artifacts?kind=${kind}` : "/artifacts"),
  createArtifact: (body: Record<string, unknown>) =>
    request<ArtifactInfo>("/artifacts", { method: "POST", body: JSON.stringify(body) }),
  deleteArtifact: (id: string) => request<void>(`/artifacts/${id}`, { method: "DELETE" }),
  artifactDownloadUrl: (id: string) => `/api/v1/artifacts/${id}/download`,

  // Audio
  transcribe: async (blob: Blob, filename: string): Promise<string> => {
    const form = new FormData();
    form.append("upload", blob, filename);
    const headers: Record<string, string> = {};
    const token = getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
    const res = await fetch("/api/v1/audio/transcribe", { method: "POST", headers, body: form });
    const body = await res.json().catch(() => null);
    if (!res.ok) throw new ApiError(res.status, body?.error?.code ?? "AUDIO_ERROR", body?.error?.message ?? "Transcription failed");
    return body.text as string;
  },
};

export const phase8Api = {
  // Sharing
  createShare: (conversationId: string, mode: string) =>
    request<{ id: string; mode: string; token: string; url: string }>("/shares", {
      method: "POST", body: JSON.stringify({ conversation_id: conversationId, mode }) }),
  listShares: () => request<{ id: string; conversation_id: string; mode: string; url: string }[]>("/shares"),
  deleteShare: (id: string) => request<void>(`/shares/${id}`, { method: "DELETE" }),
  getSharedConversation: (token: string) =>
    request<{ id: string; title: string; messages: { id: string; role: string; blocks: { type: string; data: Record<string, unknown> }[] }[] }>(
      `/shares/public/${token}`),
  sharingSettings: () => request<{ public_enabled: boolean }>("/shares/settings"),
  patchSharingSettings: (public_enabled: boolean) =>
    request<{ public_enabled: boolean }>("/shares/settings", { method: "PATCH", body: JSON.stringify({ public_enabled }) }),

  // Usage / quota
  myUsage: (days = 7) => request<Record<string, unknown>>(`/usage/me?days=${days}`),
  usageDashboard: (days = 1) => request<Record<string, unknown>>(`/usage/dashboard?days=${days}`),

  // Logs
  logs: (limit = 100) => request<Record<string, unknown>[]>(`/logs?limit=${limit}`),

  // Global search
  globalSearch: (q: string) => request<Record<string, unknown>>(`/search?q=${encodeURIComponent(q)}`),

  // System prompts
  listPrompts: () => request<PromptInfo[]>("/system-prompts"),
  createPrompt: (body: { name: string; text: string }) =>
    request<PromptInfo>("/system-prompts", { method: "POST", body: JSON.stringify(body) }),
  updatePrompt: (id: string, patch: Record<string, unknown>) =>
    request<PromptInfo>(`/system-prompts/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
  activatePrompt: (id: string) => request<{ ok: boolean; active_id: string }>(`/system-prompts/${id}/activate`, { method: "POST" }),
  deletePrompt: (id: string) => request<void>(`/system-prompts/${id}`, { method: "DELETE" }),
};
