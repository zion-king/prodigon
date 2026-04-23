// ---------------------------------------------------------------------------
// ContentViewer — displays workshop markdown with breadcrumb, nav, and actions
// ---------------------------------------------------------------------------

import { useEffect, useRef } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { ChevronRight, ChevronLeft, MessageSquare, Check } from 'lucide-react';
import { cn } from '@/lib/utils';
import { type WorkshopTask, type Subtopic } from '@/lib/topics-data';
import { useTopicsStore } from '@/stores/topics-store';
import { useSettingsStore } from '@/stores/settings-store';
import { useChatStore } from '@/stores/chat-store';
import { useToast } from '@/hooks/use-toast';
import { MarkdownRenderer } from '@/components/chat/markdown-renderer';
import { Skeleton } from '@/components/ui/skeleton';

type ViewerState = 'loading' | 'success' | 'not-found' | 'error';

interface ContentViewerProps {
  task: WorkshopTask;
  subtopic: Subtopic;
  state: ViewerState;
  content: string;
}

const DIFFICULTY_COLORS = {
  beginner: 'bg-green-500/10 text-green-600 dark:text-green-400',
  intermediate: 'bg-blue-500/10 text-blue-600 dark:text-blue-400',
  advanced: 'bg-purple-500/10 text-purple-600 dark:text-purple-400',
};

export function ContentViewer({ task, subtopic, state, content }: ContentViewerProps) {
  const navigate = useNavigate();
  const toast = useToast();
  const { markAsRead, isRead } = useTopicsStore();
  const { setTopicSystemPrompt } = useSettingsStore();
  const { createSession } = useChatStore();

  const sentinelRef = useRef<HTMLDivElement>(null);
  const read = isRead(task.id, subtopic.id);

  // Auto-mark as read when user scrolls to bottom
  useEffect(() => {
    if (state !== 'success' || read) return;
    const sentinel = sentinelRef.current;
    if (!sentinel) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          markAsRead(task.id, subtopic.id);
          observer.disconnect();
        }
      },
      { threshold: 0.5 },
    );

    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [state, read, task.id, subtopic.id, markAsRead]);

  const handleChatAboutThis = async () => {
    setTopicSystemPrompt(
      `You are discussing: ${task.title} — ${subtopic.label}. The user is studying production AI system design. Help with practical examples, trade-offs, and production considerations.`,
    );
    // createSession is async now (server round-trip); await so the new
    // session is selected before we navigate to the chat view.
    await createSession();
    navigate('/');
    toast.info('Opening chat with topic context');
  };

  const handleMarkAsRead = () => {
    markAsRead(task.id, subtopic.id);
    toast.success('Marked as read');
  };

  // Prev / next subtopic
  const currentIdx = task.subtopics.findIndex((s) => s.id === subtopic.id);
  const prevSubtopic = currentIdx > 0 ? task.subtopics[currentIdx - 1] : null;
  const nextSubtopic = currentIdx < task.subtopics.length - 1 ? task.subtopics[currentIdx + 1] : null;

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-3xl mx-auto px-6 py-8">
        {/* Breadcrumb */}
        <nav className="flex items-center gap-1.5 text-xs text-muted-foreground mb-6 flex-wrap">
          <Link to="/topics" className="hover:text-foreground transition-colors">
            Workshop
          </Link>
          <ChevronRight className="h-3 w-3 shrink-0" />
          <Link to={`/topics/${task.id}`} className="hover:text-foreground transition-colors">
            {task.title}
          </Link>
          <ChevronRight className="h-3 w-3 shrink-0" />
          <span className="text-foreground font-medium">{subtopic.label}</span>
        </nav>

        {/* Header */}
        <div className="mb-6">
          <div className="flex items-center gap-2 mb-2 flex-wrap">
            <span className="text-xs font-medium text-muted-foreground">
              Part {task.part} · Task {task.taskNumber}
            </span>
            <span
              className={cn(
                'text-[10px] px-1.5 py-0.5 rounded-full capitalize font-medium',
                DIFFICULTY_COLORS[task.difficulty],
              )}
            >
              {task.difficulty}
            </span>
          </div>
          <h1 className="text-2xl font-bold mb-1">{subtopic.label}</h1>
          <p className="text-muted-foreground text-sm">{subtopic.description}</p>
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-3 mb-8 flex-wrap">
          <button
            onClick={handleChatAboutThis}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
          >
            <MessageSquare className="h-4 w-4" />
            Chat About This
          </button>

          <button
            onClick={handleMarkAsRead}
            disabled={read}
            className={cn(
              'flex items-center gap-2 px-4 py-2 rounded-lg border text-sm font-medium transition-colors',
              read
                ? 'border-green-500/30 text-green-600 dark:text-green-400 bg-green-500/5 cursor-default'
                : 'border-border hover:bg-accent',
            )}
          >
            <Check className="h-4 w-4" />
            {read ? 'Read' : 'Mark as Read'}
          </button>
        </div>

        {/* Content */}
        {state === 'loading' && <LoadingSkeleton />}

        {state === 'success' && (
          <>
            <div className="prose-sm prose-gray dark:prose-invert max-w-none">
              <MarkdownRenderer content={content} />
            </div>
            {/* Read sentinel for IntersectionObserver */}
            <div ref={sentinelRef} className="h-4 mt-4" aria-hidden="true" />
          </>
        )}

        {state === 'not-found' && (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <p className="text-muted-foreground mb-2">Content not yet available.</p>
            <p className="text-sm text-muted-foreground">
              This section will be added in a future update.
            </p>
          </div>
        )}

        {state === 'error' && (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <p className="text-muted-foreground">Failed to load content.</p>
            <p className="text-sm text-muted-foreground mt-1">Please try again later.</p>
          </div>
        )}

        {/* Prev / Next navigation */}
        {state === 'success' && (prevSubtopic || nextSubtopic) && (
          <div className="flex items-center justify-between mt-12 pt-6 border-t border-border">
            <div>
              {prevSubtopic && (
                <Link
                  to={`/topics/${task.id}/${prevSubtopic.id}`}
                  className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors group"
                >
                  <ChevronLeft className="h-4 w-4 group-hover:-translate-x-0.5 transition-transform" />
                  <div>
                    <p className="text-[10px] uppercase tracking-wide">Previous</p>
                    <p className="font-medium">{prevSubtopic.label}</p>
                  </div>
                </Link>
              )}
            </div>
            <div className="text-right">
              {nextSubtopic && (
                <Link
                  to={`/topics/${task.id}/${nextSubtopic.id}`}
                  className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors group"
                >
                  <div>
                    <p className="text-[10px] uppercase tracking-wide">Next</p>
                    <p className="font-medium">{nextSubtopic.label}</p>
                  </div>
                  <ChevronRight className="h-4 w-4 group-hover:translate-x-0.5 transition-transform" />
                </Link>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ---- Loading skeleton -----------------------------------------------------

function LoadingSkeleton() {
  return (
    <div className="space-y-4" aria-label="Loading content">
      <Skeleton className="h-8 w-3/4" />
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-5/6" />
      <Skeleton className="h-4 w-full" />
      <div className="pt-2" />
      <Skeleton className="h-6 w-1/2" />
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-4/5" />
      <Skeleton className="h-32 w-full rounded-lg" />
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-3/4" />
    </div>
  );
}
