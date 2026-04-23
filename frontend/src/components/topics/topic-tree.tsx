// ---------------------------------------------------------------------------
// TopicTree — accordion Part → Task list inside the Topics Panel
// ---------------------------------------------------------------------------

import { useRef, useCallback, type KeyboardEvent as ReactKeyboardEvent } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { ChevronDown, ChevronRight, Lock } from 'lucide-react';
import { cn } from '@/lib/utils';
import { TASKS_BY_PART, PART_LABELS, type PartId } from '@/lib/topics-data';
import { useTopicsStore } from '@/stores/topics-store';

const PARTS: PartId[] = ['0', 'I', 'II', 'III'];

function ProgressBar({ value, max }: { value: number; max: number }) {
  const pct = max === 0 ? 0 : Math.round((value / max) * 100);
  return (
    <div className="flex items-center gap-1.5 ml-auto">
      <span className="text-[10px] text-muted-foreground tabular-nums">
        {value}/{max}
      </span>
      <div className="w-12 h-1.5 rounded-full bg-muted overflow-hidden">
        <div
          className="h-full rounded-full bg-primary transition-all duration-300"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

export function TopicTree() {
  const navigate = useNavigate();
  const location = useLocation();
  const { expandedParts, togglePart, getReadCountForPart } = useTopicsStore();
  const listRef = useRef<HTMLDivElement>(null);

  const getRowEls = useCallback(() => {
    if (!listRef.current) return [];
    return Array.from(
      listRef.current.querySelectorAll<HTMLElement>('[data-row]'),
    );
  }, []);

  const handleKeyDown = useCallback(
    (e: ReactKeyboardEvent<HTMLButtonElement>, partId?: PartId, taskId?: string) => {
      const rows = getRowEls();
      const current = e.currentTarget as HTMLElement;
      const idx = rows.indexOf(current);

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        rows[Math.min(idx + 1, rows.length - 1)]?.focus();
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        rows[Math.max(idx - 1, 0)]?.focus();
      } else if (e.key === 'ArrowLeft' && partId) {
        e.preventDefault();
        if (expandedParts.includes(partId)) togglePart(partId);
      } else if (e.key === 'ArrowRight' && partId) {
        e.preventDefault();
        if (!expandedParts.includes(partId)) togglePart(partId);
      } else if (e.key === 'Enter' && taskId) {
        e.preventDefault();
        navigate(`/topics/${taskId}`);
      }
    },
    [getRowEls, expandedParts, togglePart, navigate],
  );

  return (
    <div ref={listRef} className="py-2">
      {PARTS.map((part) => {
        const tasks = TASKS_BY_PART[part];
        const isExpanded = expandedParts.includes(part);
        const taskIds = tasks.map((t) => t.id);
        const readCount = getReadCountForPart(part, taskIds);
        const totalSubtopics = tasks.length * 4; // 4 subtopics per task
        const shortLabel = PART_LABELS[part].split(' — ')[1]; // e.g. "Design Patterns"

        return (
          <div key={part}>
            {/* Part header */}
            <button
              data-row
              onClick={() => togglePart(part)}
              onKeyDown={(e) => handleKeyDown(e, part)}
              aria-expanded={isExpanded}
              className="flex items-center w-full px-3 py-2 text-xs font-semibold text-muted-foreground hover:text-foreground hover:bg-accent/50 rounded-lg transition-colors gap-1.5 group"
            >
              {isExpanded ? (
                <ChevronDown className="h-3.5 w-3.5 shrink-0" />
              ) : (
                <ChevronRight className="h-3.5 w-3.5 shrink-0" />
              )}
              <span className="truncate text-left">Part {part} — {shortLabel}</span>
              <ProgressBar value={readCount} max={totalSubtopics} />
            </button>

            {/* Task rows */}
            {isExpanded && (
              <div className="mb-1">
                {tasks.map((task) => {
                  const isActive = location.pathname.startsWith(`/topics/${task.id}`);

                  if (!task.implemented) {
                    return (
                      <div
                        key={task.id}
                        className="flex items-center gap-2 px-4 py-2 mx-1 rounded-lg text-sm text-muted-foreground/50 cursor-not-allowed"
                      >
                        <Lock className="h-3 w-3 shrink-0" />
                        <span className="truncate flex-1">{task.title}</span>
                        <span className="text-[10px] bg-muted text-muted-foreground px-1.5 py-0.5 rounded shrink-0">
                          Soon
                        </span>
                      </div>
                    );
                  }

                  return (
                    <button
                      key={task.id}
                      data-row
                      onClick={() => navigate(`/topics/${task.id}`)}
                      onKeyDown={(e) => handleKeyDown(e, undefined, task.id)}
                      aria-current={isActive ? 'page' : undefined}
                      className={cn(
                        'flex items-center gap-2 w-full px-4 py-2 mx-0 rounded-lg text-sm transition-colors text-left',
                        isActive
                          ? 'bg-primary/10 text-primary font-medium'
                          : 'hover:bg-accent text-foreground hover:text-foreground',
                      )}
                    >
                      <span className="text-muted-foreground text-xs tabular-nums w-4 shrink-0">
                        {task.taskNumber}
                      </span>
                      <span className="truncate">{task.title}</span>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
