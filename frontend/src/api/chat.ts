// ---------------------------------------------------------------------------
// Chat persistence API — typed wrappers around /api/v1/chat/*
// ---------------------------------------------------------------------------
//
// The server is the source of truth. The chat store calls these functions to
// read and write sessions/messages; no chat data lives in localStorage.
//
// Shape translation: server timestamps arrive as ISO 8601 strings; the store
// works with numeric epoch ms so relative-time rendering is cheap. The
// `mapSession*` helpers sit here so the rest of the app never has to think
// about that boundary.

import { client } from './client';
import { nanoid } from '@/lib/utils';
import type { ChatMessage, ChatSession } from '@/stores/chat-store';

// ---- Server-side DTOs (what the FastAPI endpoints return) ------------------

export type ServerRole = 'user' | 'assistant' | 'system';

export interface ServerChatMessage {
  id: string;
  session_id: string;
  role: ServerRole;
  content: string;
  meta: Record<string, unknown> | null;
  created_at: string; // ISO 8601
}

export interface ServerChatSession {
  id: string;
  user_id: string;
  title: string;
  system_prompt: string | null;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface ServerChatSessionDetail extends ServerChatSession {
  messages: ServerChatMessage[];
}

// ---- DTO -> store-shape mappers -------------------------------------------

function toTimestamp(iso: string): number {
  const n = Date.parse(iso);
  // Date.parse can return NaN for malformed input — fall back to now so UI
  // relative-time math never produces `NaNm ago`.
  return Number.isFinite(n) ? n : Date.now();
}

function mapMessage(m: ServerChatMessage): ChatMessage {
  const meta = m.meta ?? {};
  return {
    id: m.id,
    // The store's type is narrower ('user' | 'assistant'). 'system' messages
    // aren't surfaced in the UI today; fall through to 'assistant' if we ever
    // store one so it still renders rather than blowing up.
    role: m.role === 'system' ? 'assistant' : m.role,
    content: m.content,
    timestamp: toTimestamp(m.created_at),
    model: typeof meta.model === 'string' ? (meta.model as string) : undefined,
    latencyMs: typeof meta.latency_ms === 'number' ? (meta.latency_ms as number) : undefined,
  };
}

export function mapSessionSummary(s: ServerChatSession): ChatSession {
  return {
    id: s.id,
    title: s.title,
    createdAt: toTimestamp(s.created_at),
    updatedAt: toTimestamp(s.updated_at),
    messages: [], // summary endpoint doesn't include messages
    // Empty sessions have nothing to lazy-load; treat them as loaded so
    // ChatView skips the fetch round-trip on first select.
    messagesLoaded: s.message_count === 0,
    messageCount: s.message_count,
  };
}

export function mapSessionDetail(s: ServerChatSessionDetail): ChatSession {
  return {
    id: s.id,
    title: s.title,
    createdAt: toTimestamp(s.created_at),
    updatedAt: toTimestamp(s.updated_at),
    messages: s.messages.map(mapMessage),
    messagesLoaded: true,
    messageCount: s.messages.length,
  };
}

// ---- Endpoint wrappers -----------------------------------------------------

async function listSessions(): Promise<ChatSession[]> {
  const data = await client.get<ServerChatSession[]>('/api/v1/chat/sessions');
  return data.map(mapSessionSummary);
}

async function getSession(id: string): Promise<ChatSession> {
  const data = await client.get<ServerChatSessionDetail>(`/api/v1/chat/sessions/${id}`);
  return mapSessionDetail(data);
}

async function createSession(payload?: {
  title?: string;
  system_prompt?: string;
}): Promise<ChatSession> {
  const data = await client.post<ServerChatSession>('/api/v1/chat/sessions', payload ?? {});
  return mapSessionSummary(data);
}

async function updateSession(
  id: string,
  payload: { title?: string; system_prompt?: string },
): Promise<ChatSession> {
  const data = await client.patch<ServerChatSession>(`/api/v1/chat/sessions/${id}`, payload);
  return mapSessionSummary(data);
}

async function deleteSession(id: string): Promise<void> {
  await client.del(`/api/v1/chat/sessions/${id}`);
}

async function appendMessage(
  sessionId: string,
  payload: {
    role: ServerRole;
    content: string;
    meta?: Record<string, unknown> | null;
  },
): Promise<ChatMessage> {
  const data = await client.post<ServerChatMessage>(
    `/api/v1/chat/sessions/${sessionId}/messages`,
    payload,
  );
  return mapMessage(data);
}

export const chatApi = {
  listSessions,
  getSession,
  createSession,
  updateSession,
  deleteSession,
  appendMessage,
} as const;

// Exported for components that need a throwaway client-side id while a
// real server id is being minted (e.g. a streaming assistant placeholder).
export const makeTempId = () => `tmp-${nanoid()}`;
