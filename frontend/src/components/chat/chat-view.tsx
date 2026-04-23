// ---------------------------------------------------------------------------
// ChatView — main chat orchestrator: handles send, stream, and layout
// ---------------------------------------------------------------------------

import { useCallback } from 'react';
import { useChatStore } from '@/stores/chat-store';
import { useSettingsStore } from '@/stores/settings-store';
import { useStream } from '@/hooks/use-stream';
import { useToast } from '@/hooks/use-toast';
import { MessageList } from './message-list';
import { MessageInput } from './message-input';
import { EmptyChat } from './empty-chat';
import { Square, Download } from 'lucide-react';

interface ChatViewProps {
  sessionId: string;
}

function formatRelativeTime(ts: number): string {
  const diff = Date.now() - ts;
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export function ChatView({ sessionId }: ChatViewProps) {
  const {
    activeSession,
    persistUserMessage,
    addAssistantPlaceholder,
    appendToMessage,
    updateMessage,
    persistAssistantMessage,
  } = useChatStore();
  const { model, temperature, maxTokens, topicSystemPrompt, systemPrompt, setTopicSystemPrompt } =
    useSettingsStore();
  const { isStreaming, start, stop } = useStream();
  const toast = useToast();

  const session = activeSession();
  const messages = session?.messages ?? [];

  const handleSend = useCallback(
    async (prompt: string) => {
      if (!prompt.trim() || isStreaming) return;

      // Consume topic system prompt if set
      const currentSystemPrompt = topicSystemPrompt ?? systemPrompt;
      if (topicSystemPrompt) setTopicSystemPrompt(null);

      // 1. Add + persist user message (fire-and-forget POST inside the store)
      void persistUserMessage(sessionId, prompt);

      // 2. Create assistant placeholder with a temp id; the store will swap
      //    the temp id for the server's real UUID once persistence succeeds.
      const assistantId = addAssistantPlaceholder(sessionId, model);

      const startTime = performance.now();

      // 3. Stream response
      await start(
        {
          prompt,
          model,
          temperature,
          max_tokens: maxTokens,
          ...(currentSystemPrompt ? { system_prompt: currentSystemPrompt } : {}),
        },
        {
          onToken: (token) => {
            appendToMessage(sessionId, assistantId, token);
          },
          onDone: () => {
            const latencyMs = Math.round(performance.now() - startTime);
            updateMessage(sessionId, assistantId, {
              isStreaming: false,
              latencyMs,
            });
            // Persist the completed assistant turn. Runs after local update
            // so the meta payload includes the finalized latency.
            void persistAssistantMessage(sessionId, assistantId);
          },
          onError: (error) => {
            // Mark the placeholder as failed but don't persist — a blank or
            // half-streamed turn isn't worth saving.
            updateMessage(sessionId, assistantId, {
              isStreaming: false,
              error,
            });
          },
        },
      );
    },
    [
      sessionId, model, temperature, maxTokens, isStreaming,
      topicSystemPrompt, systemPrompt,
      persistUserMessage, addAssistantPlaceholder, updateMessage, appendToMessage,
      persistAssistantMessage, start, setTopicSystemPrompt,
    ],
  );

  const handleExport = useCallback(() => {
    if (!session || messages.length === 0) return;

    const lines: string[] = [
      `# ${session.title}`,
      `*Exported from Prodigon · ${new Date().toLocaleString()}*`,
      '',
    ];

    for (const msg of messages) {
      lines.push(`## ${msg.role === 'user' ? '👤 You' : '🤖 Assistant'}`);
      lines.push(msg.content);
      lines.push('');
    }

    const blob = new Blob([lines.join('\n')], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${session.title.replace(/[^a-z0-9]/gi, '-').toLowerCase()}.md`;
    a.click();
    URL.revokeObjectURL(url);

    toast.success('Chat exported');
  }, [session, messages, toast]);

  // Session stats
  const totalTokens = messages.reduce((sum, m) => sum + Math.ceil(m.content.length / 4), 0);

  return (
    <div className="flex flex-col h-full">
      {messages.length === 0 ? (
        <EmptyChat onSelectPrompt={handleSend} />
      ) : (
        <>
          {/* Export button */}
          <div className="flex justify-end px-4 pt-2 shrink-0">
            <button
              onClick={handleExport}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground hover:bg-accent rounded-lg transition-colors"
              aria-label="Export chat as markdown"
            >
              <Download className="h-3.5 w-3.5" />
              Export
            </button>
          </div>

          <MessageList messages={messages} />

          {/* Stop button */}
          {isStreaming && (
            <div className="flex justify-center py-2 shrink-0">
              <button
                onClick={stop}
                className="flex items-center gap-2 px-4 py-1.5 text-sm rounded-full border border-border hover:bg-accent transition-colors"
              >
                <Square className="h-3 w-3 fill-current" />
                Stop generating
              </button>
            </div>
          )}
        </>
      )}

      <div className="px-4 pb-4 pt-2 shrink-0">
        {/* Session stats */}
        {messages.length > 0 && (
          <div className="flex items-center gap-2 text-[10px] text-muted-foreground mb-2 px-1">
            <span>{messages.length} messages</span>
            <span>·</span>
            <span>~{totalTokens.toLocaleString()} tokens</span>
            <span>·</span>
            <span>{session ? formatRelativeTime(session.createdAt) : ''}</span>
          </div>
        )}

        <MessageInput
          onSend={handleSend}
          isStreaming={isStreaming}
          onStop={stop}
        />
      </div>
    </div>
  );
}
