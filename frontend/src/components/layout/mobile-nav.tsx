// ---------------------------------------------------------------------------
// MobileNav — slide-over sidebar for mobile/tablet viewports
// ---------------------------------------------------------------------------

import { useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  Plus,
  Trash2,
  MessageSquare,
  LayoutDashboard,
  Layers,
  X,
  BookOpen,
} from 'lucide-react';
import { cn, truncate } from '@/lib/utils';
import { useChatStore } from '@/stores/chat-store';
import { useSettingsStore } from '@/stores/settings-store';

const NAV_LINKS = [
  { path: '/', label: 'Chat', icon: MessageSquare },
  { path: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/jobs', label: 'Batch Jobs', icon: Layers },
  { path: '/topics', label: 'Workshop', icon: BookOpen },
] as const;

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

export function MobileNav() {
  const navigate = useNavigate();
  const location = useLocation();
  const { sessions, activeSessionId, setActiveSession, deleteSession, createSession } =
    useChatStore();
  const { sidebarOpen, setSidebarOpen } = useSettingsStore();

  // Close on route change
  useEffect(() => {
    setSidebarOpen(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname]);

  const close = () => setSidebarOpen(false);

  const handleNewChat = async () => {
    await createSession();
    navigate('/');
    close();
  };

  const handleSessionClick = (id: string) => {
    // setActiveSession is async (lazy-loads messages); navigate without waiting.
    void setActiveSession(id);
    navigate('/');
    close();
  };

  const handleNavClick = (path: string) => {
    navigate(path);
    close();
  };

  return (
    <>
      {/* Backdrop */}
      <div
        className={cn(
          'fixed inset-0 z-40 bg-black/50 transition-opacity md:hidden',
          sidebarOpen ? 'opacity-100' : 'opacity-0 pointer-events-none',
        )}
        onClick={close}
      />

      {/* Panel */}
      <div
        className={cn(
          'fixed inset-y-0 left-0 z-50 w-72 bg-card border-r border-border flex flex-col transition-transform duration-300 ease-in-out md:hidden',
          sidebarOpen ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-4 shrink-0">
          <div className="flex items-center gap-2">
            <div className="h-6 w-6 rounded-md bg-primary flex items-center justify-center shrink-0">
              <span className="text-primary-foreground text-xs font-bold">P</span>
            </div>
            <span className="text-lg font-bold tracking-tight gradient-text">Prodigon</span>
          </div>
          <button
            onClick={close}
            className="p-1.5 rounded-lg hover:bg-accent transition-colors"
            aria-label="Close menu"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* New Chat */}
        <div className="px-3 pb-2 shrink-0">
          <button
            onClick={handleNewChat}
            className="flex items-center gap-2 w-full px-3 py-2 rounded-lg border border-border text-sm font-medium hover:bg-accent transition-colors"
          >
            <Plus className="h-4 w-4" />
            New Chat
          </button>
        </div>

        {/* Session List */}
        <div className="flex-1 overflow-y-auto px-2">
          {sessions.map((session) => (
            <div key={session.id} className="group relative">
              <button
                onClick={() => handleSessionClick(session.id)}
                className={cn(
                  'flex flex-col items-start w-full px-3 py-2.5 rounded-lg text-left text-sm transition-colors',
                  session.id === activeSessionId
                    ? 'bg-accent text-accent-foreground'
                    : 'hover:bg-accent/50 text-foreground',
                )}
              >
                <span className="truncate w-full font-medium">
                  {truncate(session.title, 28)}
                </span>
                <span className="text-xs text-muted-foreground mt-0.5">
                  {formatRelativeTime(session.updatedAt)}
                </span>
              </button>

              <button
                onClick={(e) => {
                  e.stopPropagation();
                  void deleteSession(session.id);
                }}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded opacity-0 group-hover:opacity-100 hover:bg-destructive/10 hover:text-destructive transition-all"
                aria-label="Delete session"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>

        {/* Bottom Nav */}
        <nav className="border-t border-border px-2 py-2 shrink-0 space-y-0.5">
          {NAV_LINKS.map((link) => {
            const Icon = link.icon;
            const isActive =
              link.path === '/'
                ? location.pathname === '/'
                : location.pathname.startsWith(link.path);
            return (
              <button
                key={link.path}
                onClick={() => handleNavClick(link.path)}
                aria-current={isActive ? 'page' : undefined}
                className={cn(
                  'flex items-center gap-3 w-full px-3 py-2 rounded-lg text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-primary/10 text-primary'
                    : 'hover:bg-accent text-muted-foreground hover:text-foreground',
                )}
              >
                <Icon className="h-4 w-4" />
                {link.label}
              </button>
            );
          })}
        </nav>
      </div>
    </>
  );
}
