// ---------------------------------------------------------------------------
// ChatPage — ensures an active session exists, then renders the chat view
// ---------------------------------------------------------------------------
//
// Chat data now lives on the server. We wait for `hydrated` before deciding
// whether to create a new session, otherwise we'd spam the API with a fresh
// "New Chat" row every time the user visits `/` before hydrate finishes.

import { useEffect } from 'react';
import { useChatStore } from '@/stores/chat-store';
import { ChatView } from '@/components/chat/chat-view';

export function ChatPage() {
  const { activeSessionId, hydrated, sessions, createSession } = useChatStore();

  useEffect(() => {
    if (!hydrated) return;
    // Only create if the user has no sessions at all. After the first hydrate
    // the auto-select logic in the store picks the most recent session, so
    // normally we won't hit the create branch on page load.
    if (!activeSessionId && sessions.length === 0) {
      createSession();
    }
  }, [hydrated, activeSessionId, sessions.length, createSession]);

  if (!hydrated || !activeSessionId) return null;

  return <ChatView sessionId={activeSessionId} />;
}
