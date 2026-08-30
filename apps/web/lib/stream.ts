import { getToken } from "./api";

export interface StreamEvent {
  event: string;
  data: Record<string, unknown>;
}

export interface RunCallbacks {
  onEvent?: (event: StreamEvent) => void;
  onError?: (error: { code: string; message: string }) => void;
  onDone?: () => void;
}

export async function runResearch(
  conversationId: string,
  body: { goal: string; model_id?: string | null },
  callbacks: RunCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  const token = getToken();
  const res = await fetch(`/api/v1/conversations/${conversationId}/research`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) {
    let message = `Request failed (${res.status})`;
    let code = "INTERNAL_ERROR";
    try {
      const body = await res.json();
      message = body?.error?.message ?? message;
      code = body?.error?.code ?? code;
    } catch {
      /* ignore */
    }
    callbacks.onError?.({ code, message });
    return;
  }
  await consumeSse(res, callbacks);
}

async function consumeSse(res: Response, callbacks: RunCallbacks): Promise<void> {
  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let currentEvent = "message";
  const dispatch = async (eventName: string, rawData: string) => {
    try {
      const parsed = JSON.parse(rawData) as Record<string, unknown>;
      callbacks.onEvent?.({ event: eventName, data: parsed });
    } catch {
      /* ignore malformed */
    }
  };
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let index: number;
    for (;;) {
      index = buffer.indexOf("\n");
      if (index === -1) break;
      const line = buffer.slice(0, index).replace(/\r$/, "");
      buffer = buffer.slice(index + 1);
      if (line === "") {
        currentEvent = "message";
        continue;
      }
      if (line.startsWith("event:")) {
        currentEvent = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        await dispatch(currentEvent, line.slice(5).trim());
      }
    }
  }
  buffer += decoder.decode();
  if (buffer.trim().startsWith("data:")) {
    await dispatch(currentEvent, buffer.trim().slice(5).trim());
  }
  callbacks.onDone?.();
}

export async function runConversation(
  conversationId: string,
  body: {
    content: string;
    parent_id?: string | null;
    model_id?: string | null;
    reasoning_effort?: string;
    file_ids?: string[];
    web_search?: boolean;
  },
  callbacks: RunCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  const token = getToken();
  const res = await fetch(`/api/v1/conversations/${conversationId}/runs`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) {
    let message = `Request failed (${res.status})`;
    let code = "INTERNAL_ERROR";
    try {
      const body = await res.json();
      message = body?.error?.message ?? message;
      code = body?.error?.code ?? code;
    } catch {
      /* ignore */
    }
    callbacks.onError?.({ code, message });
    return;
  }
  await consumeSse(res, callbacks);
}

export async function streamGet(
  url: string,
  callbacks: RunCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  const token = getToken();
  const res = await fetch(url, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    signal,
  });
  if (!res.ok || !res.body) {
    callbacks.onError?.({ code: "INTERNAL_ERROR", message: `Request failed (${res.status})` });
    return;
  }
  await consumeSse(res, callbacks);
}
