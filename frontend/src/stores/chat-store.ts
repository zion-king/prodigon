// ---------------------------------------------------------------------------
// Chat Store — sessions + messages, backed by the server
// ---------------------------------------------------------------------------
//
// The store's in-memory state is a cache of what lives in Postgres. On boot,
// `hydrate()` pulls the session list from /api/v1/chat/sessions. Session
// messages are lazy-loaded the first time a session becomes active, so the
// initial payload stays small even for users with many sessions.
//
// Writes are persisted through the chat API:
//   createSession        -> POST   /api/v1/chat/sessions
//   deleteSession        -> DELETE /api/v1/chat/sessions/:id
//   renameSession        -> PATCH  /api/v1/chat/sessions/:id
//   persistUserMessage   -> POST   /api/v1/chat/sessions/:id/messages
//   persistAssistantMessage -> same, called when streaming completes
//
// Streaming note
// --------------
// The assistant message gets a client-side temp id (`tmp-...`) while tokens
// are streaming in. Persistence happens once after `onDone`, and the server
// response's real UUID replaces the temp id in-place. If the user refreshes
// mid-stream, the in-flight assistant turn is lost — that's intentional;
// partial responses aren't useful to save.

import { create } from 'zustand';
import { chatApi, makeTempId } from '@/api/chat';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
  model?: string;
  latencyMs?: number;
  isStreaming?: boolean;
  error?: string;
}

export interface ChatSession {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  messages: ChatMessage[];
  /**
   * Whether the full message list for this session has been fetched.
   * List endpoint returns summaries only; detail endpoint populates messages.
   */
  messagesLoaded: boolean;
  /**
   * Total message count as reported by the server. Used by sidebar previews
   * and dashboard counters while `messages` is still empty (summary-only).
   */
  messageCount: number;
}

interface ChatState {
  sessions: ChatSession[];
  activeSessionId: string | null;
  hydrated: boolean;
  hydrating: boolean;

  // Derived helpers
  activeSession: () => ChatSession | undefined;

  // Lifecycle
  hydrate: () => Promise<void>;

  // Session actions (server-persisted)
  createSession: () => Promise<string>;
  setActiveSession: (id: string) => Promise<void>;
  deleteSession: (id: string) => Promise<void>;
  renameSession: (id: string, title: string) => Promise<void>;

  // Message actions
  // User turns persist immediately (content is final on send).
  persistUserMessage: (sessionId: string, content: string) => Promise<string>;
  // Assistant placeholder lives locally until the stream finishes; then
  // `persistAssistantMessage` saves it and swaps the temp id for the real one.
  addAssistantPlaceholder: (sessionId: string, model?: string) => string;
  appendToMessage: (sessionId: string, messageId: string, token: string) => void;
  updateMessage: (sessionId: string, messageId: string, updates: Partial<ChatMessage>) => void;
  persistAssistantMessage: (sessionId: string, tempMessageId: string) => Promise<void>;
}

export const useChatStore = create<ChatState>((set, get) => ({
  sessions: [],
  activeSessionId: null,
  hydrated: false,
  hydrating: false,

  activeSession: () => {
    const { sessions, activeSessionId } = get();
    return sessions.find((s) => s.id === activeSessionId);
  },

  // --- lifecycle ---------------------------------------------------------

  hydrate: async () => {
    if (get().hydrated || get().hydrating) return;
    set({ hydrating: true });
    try {
      const sessions = await chatApi.listSessions();
      set({
        sessions,
        hydrated: true,
        hydrating: false,
        // Auto-select the most recent session so the chat view isn't empty
        // on return visits. The list is already sorted updated_at DESC.
        activeSessionId: sessions.length > 0 ? sessions[0].id : null,
      });

      // Eagerly fetch messages for the auto-selected session so the first
      // paint of ChatView shows history instead of an empty state.
      if (sessions.length > 0) {
        await get().setActiveSession(sessions[0].id);
      }
    } catch (err) {
      // Don't throw — keep the app usable even if the server is down.
      // A ConnectionBanner is already rendered at the app root to surface this.
      console.error('chat hydrate failed', err);
      set({ hydrating: false, hydrated: true });
    }
  },

  // --- sessions ----------------------------------------------------------

  createSession: async () => {
    const created = await chatApi.createSession();
    set((state) => ({
      sessions: [created, ...state.sessions],
      activeSessionId: created.id,
    }));
    return created.id;
  },

  setActiveSession: async (id) => {
    set({ activeSessionId: id });

    // Lazy-load messages the first time this session becomes active.
    const session = get().sessions.find((s) => s.id === id);
    if (session && !session.messagesLoaded) {
      try {
        const detail = await chatApi.getSession(id);
        set((state) => ({
          sessions: state.sessions.map((s) => (s.id === id ? detail : s)),
        }));
      } catch (err) {
        console.error('failed to load session messages', err);
      }
    }
  },

  deleteSession: async (id) => {
    // Optimistic: remove from the UI immediately, then confirm on the server.
    // If the server call fails we could re-insert, but a stale row is a worse
    // UX than a silent retry on next hydrate.
    const prev = get().sessions;
    set((state) => {
      const remaining = state.sessions.filter((s) => s.id !== id);
      const newActiveId =
        state.activeSessionId === id
          ? remaining.length > 0
            ? remaining[0].id
            : null
          : state.activeSessionId;
      return { sessions: remaining, activeSessionId: newActiveId };
    });
    try {
      await chatApi.deleteSession(id);
    } catch (err) {
      console.error('failed to delete session', err);
      set({ sessions: prev });
    }
  },

  renameSession: async (id, title) => {
    // Optimistic rename — server PATCH happens in the background.
    set((state) => ({
      sessions: state.sessions.map((s) => (s.id === id ? { ...s, title } : s)),
    }));
    try {
      await chatApi.updateSession(id, { title });
    } catch (err) {
      console.error('failed to rename session', err);
    }
  },

  // --- messages ----------------------------------------------------------

  persistUserMessage: async (sessionId, content) => {
    // Optimistic add with a temp id — we swap in the real server id once POST
    // returns so subsequent updates reference the canonical row.
    const tempId = makeTempId();
    const now = Date.now();
    const optimistic: ChatMessage = {
      id: tempId,
      role: 'user',
      content,
      timestamp: now,
    };

    set((state) => ({
      sessions: state.sessions.map((s) => {
        if (s.id !== sessionId) return s;
        // Auto-title from the first user message (mirrors the old behaviour).
        const title =
          s.messages.length === 0 && s.title === 'New Chat'
            ? content.slice(0, 50) || 'New Chat'
            : s.title;
        return {
          ...s,
          title,
          updatedAt: now,
          messages: [...s.messages, optimistic],
          messageCount: s.messageCount + 1,
        };
      }),
    }));

    // Fire-and-forget persistence plus first-message title sync.
    try {
      const saved = await chatApi.appendMessage(sessionId, {
        role: 'user',
        content,
      });
      // Replace temp id with server id
      set((state) => ({
        sessions: state.sessions.map((s) => {
          if (s.id !== sessionId) return s;
          return {
            ...s,
            messages: s.messages.map((m) => (m.id === tempId ? saved : m)),
          };
        }),
      }));

      // If we auto-titled, push that to the server too so the sidebar on
      // another device shows the same name.
      const session = get().sessions.find((s) => s.id === sessionId);
      if (session && session.messages.length === 1 && session.title !== 'New Chat') {
        chatApi
          .updateSession(sessionId, { title: session.title })
          .catch((err) => console.error('title sync failed', err));
      }

      return saved.id;
    } catch (err) {
      console.error('failed to persist user message', err);
      return tempId;
    }
  },

  addAssistantPlaceholder: (sessionId, model) => {
    const id = makeTempId();
    const now = Date.now();
    const placeholder: ChatMessage = {
      id,
      role: 'assistant',
      content: '',
      timestamp: now,
      model,
      isStreaming: true,
    };
    set((state) => ({
      sessions: state.sessions.map((s) =>
        s.id === sessionId
          ? {
              ...s,
              updatedAt: now,
              messages: [...s.messages, placeholder],
              messageCount: s.messageCount + 1,
            }
          : s,
      ),
    }));
    return id;
  },

  appendToMessage: (sessionId, messageId, token) => {
    set((state) => ({
      sessions: state.sessions.map((s) => {
        if (s.id !== sessionId) return s;
        return {
          ...s,
          messages: s.messages.map((m) =>
            m.id === messageId ? { ...m, content: m.content + token } : m,
          ),
        };
      }),
    }));
  },

  updateMessage: (sessionId, messageId, updates) => {
    set((state) => ({
      sessions: state.sessions.map((s) => {
        if (s.id !== sessionId) return s;
        return {
          ...s,
          updatedAt: Date.now(),
          messages: s.messages.map((m) =>
            m.id === messageId ? { ...m, ...updates } : m,
          ),
        };
      }),
    }));
  },

  persistAssistantMessage: async (sessionId, tempMessageId) => {
    const session = get().sessions.find((s) => s.id === sessionId);
    const message = session?.messages.find((m) => m.id === tempMessageId);
    if (!message || !message.content) return;

    try {
      const saved = await chatApi.appendMessage(sessionId, {
        role: 'assistant',
        content: message.content,
        meta: {
          model: message.model,
          latency_ms: message.latencyMs,
        },
      });
      // Swap temp id for server id while preserving any local-only fields
      // (latencyMs, model) that the server doesn't round-trip through meta
      // for free.
      set((state) => ({
        sessions: state.sessions.map((s) => {
          if (s.id !== sessionId) return s;
          return {
            ...s,
            messages: s.messages.map((m) =>
              m.id === tempMessageId
                ? {
                    ...m,
                    id: saved.id,
                    timestamp: saved.timestamp,
                    isStreaming: false,
                  }
                : m,
            ),
          };
        }),
      }));
    } catch (err) {
      console.error('failed to persist assistant message', err);
      // Leave the message in the UI with its temp id; it will be gone on
      // next hydrate, which is fine — a failed save is a failed save.
    }
  },
}));
