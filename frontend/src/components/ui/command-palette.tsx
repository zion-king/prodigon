// ---------------------------------------------------------------------------
// CommandPalette — Cmd+K modal for quick navigation and actions
// ---------------------------------------------------------------------------

import { useEffect, useRef, useState, useCallback, type ElementType, type KeyboardEvent as ReactKeyboardEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Search,
  MessageSquare,
  BookOpen,
  LayoutDashboard,
  Layers,
  Plus,
  Sun,
  Moon,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { WORKSHOP_TASKS } from '@/lib/topics-data';
import { useChatStore } from '@/stores/chat-store';
import { useSettingsStore } from '@/stores/settings-store';

interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
}

interface CommandItem {
  id: string;
  label: string;
  description?: string;
  icon: ElementType;
  group: string;
  action: () => void;
}

export function CommandPalette({ open, onClose }: CommandPaletteProps) {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [focusedIdx, setFocusedIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const { sessions, createSession, setActiveSession } = useChatStore();
  const { theme, setTheme } = useSettingsStore();

  // Auto-focus and reset on open
  useEffect(() => {
    if (open) {
      setQuery('');
      setFocusedIdx(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  const handleClose = useCallback(() => {
    onClose();
    setQuery('');
  }, [onClose]);

  // Build command list
  const buildCommands = useCallback((): CommandItem[] => {
    const q = query.toLowerCase();

    const actions: CommandItem[] = [
      {
        id: 'new-chat',
        label: 'New Chat',
        icon: Plus,
        group: 'Actions',
        action: () => {
          // createSession is async; fire-and-forget — navigation happens
          // immediately and ChatPage renders once activeSessionId is set.
          void createSession();
          navigate('/');
          handleClose();
        },
      },
      {
        id: 'go-dashboard',
        label: 'Go to Dashboard',
        icon: LayoutDashboard,
        group: 'Actions',
        action: () => { navigate('/dashboard'); handleClose(); },
      },
      {
        id: 'go-jobs',
        label: 'Go to Batch Jobs',
        icon: Layers,
        group: 'Actions',
        action: () => { navigate('/jobs'); handleClose(); },
      },
      {
        id: 'toggle-theme',
        label: theme === 'dark' ? 'Switch to Light Mode' : 'Switch to Dark Mode',
        icon: theme === 'dark' ? Sun : Moon,
        group: 'Actions',
        action: () => { setTheme(theme === 'dark' ? 'light' : 'dark'); handleClose(); },
      },
    ];

    const topics: CommandItem[] = WORKSHOP_TASKS.filter((t) => t.implemented).map((t) => ({
      id: `topic-${t.id}`,
      label: `Task ${t.taskNumber}: ${t.title}`,
      description: `Part ${t.part} — ${t.duration}`,
      icon: BookOpen,
      group: 'Workshop Topics',
      action: () => { navigate(`/topics/${t.id}`); handleClose(); },
    }));

    const sessionItems: CommandItem[] = sessions.slice(0, 5).map((s) => ({
      id: `session-${s.id}`,
      label: s.title,
      description: `${s.messageCount} messages`,
      icon: MessageSquare,
      group: 'Recent Sessions',
      action: () => {
        // setActiveSession is async (lazy-loads messages); don't block the
        // palette close on the round-trip.
        void setActiveSession(s.id);
        navigate('/');
        handleClose();
      },
    }));

    const all = [...actions, ...topics, ...sessionItems];
    if (!q) return all;
    return all.filter(
      (c) =>
        c.label.toLowerCase().includes(q) ||
        c.description?.toLowerCase().includes(q) ||
        c.group.toLowerCase().includes(q),
    );
  }, [query, sessions, theme, navigate, createSession, setActiveSession, setTheme, handleClose]);

  const commands = buildCommands();

  // Group commands
  const grouped = commands.reduce<Record<string, CommandItem[]>>((acc, cmd) => {
    (acc[cmd.group] ||= []).push(cmd);
    return acc;
  }, {});

  // Keyboard navigation
  const handleKeyDown = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Escape') {
      handleClose();
      return;
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setFocusedIdx((i) => Math.min(i + 1, commands.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setFocusedIdx((i) => Math.max(i - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      commands[focusedIdx]?.action();
    }
  };

  // Scroll focused item into view
  useEffect(() => {
    const el = listRef.current?.querySelector(`[data-idx="${focusedIdx}"]`);
    el?.scrollIntoView({ block: 'nearest' });
  }, [focusedIdx]);

  if (!open) return null;

  let flatIdx = 0;

  return (
    <div className="fixed inset-0 z-[100] flex items-start justify-center pt-[15vh] px-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={handleClose}
        aria-hidden="true"
      />

      {/* Panel */}
      <div
        className="relative w-full max-w-lg bg-card border border-border rounded-xl shadow-2xl overflow-hidden animate-scale-in"
        role="dialog"
        aria-label="Command palette"
        aria-modal="true"
        onKeyDown={handleKeyDown}
      >
        {/* Search input */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-border">
          <Search className="h-4 w-4 text-muted-foreground shrink-0" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => { setQuery(e.target.value); setFocusedIdx(0); }}
            placeholder="Search topics, sessions, actions…"
            className="flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
            aria-label="Search"
          />
          <kbd className="text-[10px] bg-muted px-1.5 py-0.5 rounded font-mono text-muted-foreground">
            Esc
          </kbd>
        </div>

        {/* Results */}
        <div
          ref={listRef}
          className="max-h-80 overflow-y-auto py-2"
          role="listbox"
          aria-live="polite"
          aria-label="Search results"
        >
          {commands.length === 0 ? (
            <p className="text-center text-sm text-muted-foreground py-6">No results for "{query}"</p>
          ) : (
            Object.entries(grouped).map(([group, items]) => (
              <div key={group}>
                <p className="px-4 py-1 text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">
                  {group}
                </p>
                {items.map((cmd) => {
                  const thisIdx = flatIdx++;
                  const Icon = cmd.icon;
                  const isFocused = thisIdx === focusedIdx;
                  return (
                    <button
                      key={cmd.id}
                      data-idx={thisIdx}
                      role="option"
                      aria-selected={isFocused}
                      onClick={cmd.action}
                      onMouseEnter={() => setFocusedIdx(thisIdx)}
                      className={cn(
                        'flex items-center gap-3 w-full px-4 py-2 text-sm transition-colors text-left',
                        isFocused ? 'bg-accent text-accent-foreground' : 'hover:bg-accent/50',
                      )}
                    >
                      <Icon className="h-4 w-4 shrink-0 text-muted-foreground" />
                      <div className="flex-1 min-w-0">
                        <span className="truncate block">{cmd.label}</span>
                        {cmd.description && (
                          <span className="text-xs text-muted-foreground truncate block">
                            {cmd.description}
                          </span>
                        )}
                      </div>
                    </button>
                  );
                })}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
