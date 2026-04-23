// ---------------------------------------------------------------------------
// App — root component that ties together global providers and routing
// ---------------------------------------------------------------------------

import { useCallback, useEffect, useState } from 'react';
import { AppRouter } from '@/router';
import ErrorBoundary from '@/components/shared/error-boundary';
import ConnectionBanner from '@/components/shared/connection-banner';
import { ToastContainer } from '@/components/ui/toast';
import { CommandPalette } from '@/components/ui/command-palette';
import { useTheme } from '@/hooks/use-theme';
import { useHealthPoll } from '@/hooks/use-health-poll';
import { useKeyboardShortcuts } from '@/hooks/use-keyboard-shortcuts';
import { useSettingsStore } from '@/stores/settings-store';
import { useChatStore } from '@/stores/chat-store';

export default function App() {
  const [commandOpen, setCommandOpen] = useState(false);

  // Apply theme (dark/light/system) on mount and on change
  useTheme();

  // Start polling service health globally
  useHealthPoll();

  const { toggleSidebar, toggleTopicsPanel } = useSettingsStore();
  const { activeSession, hydrate } = useChatStore();

  // Pull chat sessions from the server once on mount. The store guards
  // against duplicate hydrations, so re-renders don't re-fetch.
  useEffect(() => {
    hydrate();
  }, [hydrate]);

  const handleExportChat = useCallback(() => {
    const session = activeSession();
    if (!session || session.messages.length === 0) return;

    const lines: string[] = [
      `# ${session.title}`,
      `*Exported from Prodigon · ${new Date().toLocaleString()}*`,
      '',
    ];
    for (const msg of session.messages) {
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
  }, [activeSession]);

  // Global keyboard shortcuts
  useKeyboardShortcuts({
    'mod+k': () => setCommandOpen(true),
    'mod+/': () => toggleSidebar(),
    'mod+shift+t': () => toggleTopicsPanel(),
    'mod+shift+e': () => handleExportChat(),
  });

  return (
    <ErrorBoundary>
      <ConnectionBanner />
      <AppRouter />
      <ToastContainer />
      <CommandPalette open={commandOpen} onClose={() => setCommandOpen(false)} />
    </ErrorBoundary>
  );
}
