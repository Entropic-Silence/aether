export interface User {
  id: string;
  email: string;
  name: string;
  role: string;
  created_at: string;
}

export interface Branding {
  product_name: string;
  logo_url: string | null;
  accent_color: string;
  icon_set: string;
  tagline: string;
}

export interface Provider {
  id: string;
  kind: string;
  name: string;
  base_url: string;
  proxy: string;
  timeout_ms: number;
  retry: { max?: number; backoff_ms?: number };
  concurrency: number;
  organization: string;
  project: string;
  enabled: boolean;
  has_api_key: boolean;
  created_at: string;
}

export interface Capabilities {
  [key: string]: boolean | number | string[] | undefined;
}

export interface ModelInfo {
  id: string;
  provider_id: string;
  model_id: string;
  display_name: string;
  description: string;
  icon: string;
  model_family: string;
  model_type: string;
  category: string;
  context_window: number;
  max_output_tokens: number;
  enabled: boolean;
  is_default: boolean;
  priority: number;
  weight: number;
  generation_defaults: Record<string, unknown>;
  extra_body: Record<string, unknown>;
  capabilities: Capabilities;
  capability_overrides: Capabilities;
  effective_capabilities: Capabilities;
  probe_status: string;
  probed_at: string | null;
  created_at: string;
  provider_name: string;
}

export interface Conversation {
  id: string;
  title: string;
  mode: string;
  model_id: string | null;
  pinned: boolean;
  archived: boolean;
  temporary: boolean;
  project_id: string | null;
  created_at: string;
  updated_at: string;
  preview: string;
}

export interface Block {
  id: string;
  seq: number;
  type: string;
  data: Record<string, unknown>;
}

export interface Message {
  id: string;
  conversation_id: string;
  parent_id: string | null;
  role: "user" | "assistant";
  model_id: string | null;
  status: string;
  error: Record<string, unknown> | null;
  usage: Record<string, unknown> | null;
  created_at: string;
  blocks: Block[];
}

export interface MessageBranch {
  parent_user_message_id: string;
  active_message_id: string;
  alternatives: Array<{ message_id: string; status: string; created_at: string }>;
}

export interface ComputeInfo {
  kind: string;
  backend: string;
  driver: string;
  dtk_version: string;
  hip_version: string;
  torch_version: string;
  device_count: number;
  devices: {
    index: number;
    name: string;
    memory_total_mb: number;
    memory_used_mb: number;
    memory_free_mb: number;
    temperature_c?: number;
    power_w?: number;
    power_cap_w?: number;
    utilization_pct?: number;
    vram_used_pct?: number;
  }[];
}

export interface FileMeta {
  id: string;
  name: string;
  mime: string;
  kind: string;
  size: number;
  sha256?: string;
  status: string;
  error: string;
  project_id: string | null;
  created_at: string;
  extraction: {
    pages: number;
    text_chars: number;
    notices: string[];
    indexed_chunks: number;
  };
}

export interface ProjectMeta {
  id: string;
  name: string;
  description: string;
  icon: string;
  instructions: string;
  memory_mode: string;
  pinned: boolean;
  created_at: string;
  chat_count: number;
  file_count: number;
}

export interface UiSettings {
  retrieval_configured: boolean;
  vision_fallback_configured: boolean;
  search_configured: boolean;
  stt_configured: boolean;
  tts_configured: boolean;
  features: FeatureFlags;
  policies: FeaturePolicies;
  public_sharing_enabled: boolean;
}

export interface FeatureFlags {
  chat: boolean;
  work: boolean;
  image_generation: boolean;
  projects: boolean;
  tasks: boolean;
  library: boolean;
  file_uploads: boolean;
  plugins: boolean;
  web_search: boolean;
  deep_research: boolean;
  memory: boolean;
  custom_instructions: boolean;
  audio: boolean;
}

export interface FeaturePolicies {
  registration_enabled: boolean;
  max_upload_mb: number;
}

export interface FeatureControls {
  features: FeatureFlags;
  policies: FeaturePolicies;
}

export interface ImageModelInfo {
  id: string;
  provider_kind: string;
  name: string;
  model_ref: string;
  base_url: string;
  has_api_key: boolean;
  capabilities: Record<string, unknown>;
  defaults: Record<string, number>;
  limits: Record<string, number>;
  skill_text: string;
  enabled: boolean;
  is_default: boolean;
  created_at: string;
}

export interface ImageGenerationResult {
  file_id: string;
  url: string;
  width: number;
  height: number;
  mode: string;
  seed: number | null;
  duration_ms: number;
  prompt_used: string;
  negative_prompt_used: string;
  optimized: boolean;
  aspect_ratio: ImageAspectRatio;
  model: { id: string; name: string };
}

export type ImageAspectRatio = "1:1" | "16:9" | "9:16" | "3:2" | "2:3" | "4:3" | "3:4" | "5:4" | "4:5" | "21:9" | "9:21";

export interface ImagePromptOptimization {
  original_prompt: string;
  prompt: string;
  negative_prompt: string;
  optimized: boolean;
  aspect_ratio: ImageAspectRatio;
  model: { id: string; name: string };
}

export interface McpServerInfo {
  id: string;
  name: string;
  transport: string;
  enabled: boolean;
  last_status: string;
  last_error: string;
  last_tool_count: number;
  created_at: string;
}

export interface SkillInfo {
  id: string;
  name: string;
  version: string;
  description: string;
  instructions: string;
  trigger: string;
  capabilities: string[];
  allowed_models: string[];
  allowed_tools: string[];
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  priority: number;
  scope: string;
  source: string;
  enabled: boolean;
  created_at: string;
}

export interface PluginInfo {
  plugin_id: string;
  name: string;
  version: string;
  status: string;
  problems: string[];
  capabilities: string[];
  permissions: string[];
  description: string;
  format: string;
  enabled: boolean;
  installed_at: string;
}

export interface MemoryInfo {
  id: string;
  kind: string;
  content: string;
  category: string;
  project_id: string | null;
  source: string;
  confidence: number;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface UserPrefInfo {
  about_me: string;
  response_style: string;
  memory_enabled: boolean;
  memory_reference: boolean;
  memory_auto_capture: boolean;
  daily_message_limit: number;
  daily_token_limit: number;
  daily_image_limit: number;
  daily_search_limit: number;
}

export interface TaskInfo {
  id: string;
  name: string;
  prompt: string;
  schedule_type: string;
  schedule_value: string;
  timezone: string;
  model_id: string | null;
  project_id: string | null;
  enabled: boolean;
  last_run: string | null;
  next_run: string | null;
  created_at: string;
}

export interface TaskRunInfo {
  id: string;
  status: string;
  conversation_id: string | null;
  result_summary: string;
  error: string;
  started_at: string;
  finished_at: string | null;
}

export interface ArtifactInfo {
  id: string;
  kind: string;
  title: string;
  content: string;
  file_id: string | null;
  conversation_id: string | null;
  message_id: string | null;
  created_at: string;
}

export interface PromptInfo {
  id: string;
  name: string;
  text: string;
  version: number;
  status: string;
  is_active: boolean;
  created_at: string;
}
