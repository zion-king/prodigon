// ---------------------------------------------------------------------------
// TopicsPage — /topics — Workshop task card grid grouped by Part
// ---------------------------------------------------------------------------

import { useNavigate } from 'react-router-dom';
import { Lock, Clock, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import { TASKS_BY_PART, PART_LABELS, type PartId } from '@/lib/topics-data';

const PARTS: PartId[] = ['0', 'I', 'II', 'III'];

const DIFFICULTY_COLORS = {
  beginner: 'bg-green-500/10 text-green-600 dark:text-green-400',
  intermediate: 'bg-blue-500/10 text-blue-600 dark:text-blue-400',
  advanced: 'bg-purple-500/10 text-purple-600 dark:text-purple-400',
};

export function TopicsPage() {
  const navigate = useNavigate();

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-4xl mx-auto px-6 py-8">
        {/* Page header */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold mb-2">Workshop Topics</h1>
          <p className="text-muted-foreground">
            11 hands-on tasks covering design patterns, scalability, and security for production AI
            systems.
          </p>
        </div>

        {PARTS.map((part) => {
          const tasks = TASKS_BY_PART[part];
          const isAvailable = tasks.some((t) => t.implemented);

          return (
            <div key={part} className="mb-10">
              {/* Part header */}
              <div className="flex items-center gap-3 mb-4">
                <h2 className="text-base font-semibold">{PART_LABELS[part]}</h2>
                {!isAvailable && (
                  <span className="flex items-center gap-1 text-xs text-muted-foreground bg-muted px-2 py-0.5 rounded-full">
                    <Lock className="h-3 w-3" />
                    Coming Soon
                  </span>
                )}
              </div>

              {/* Task cards */}
              <div className="grid gap-3 sm:grid-cols-2">
                {tasks.map((task) => {
                  const implemented = task.implemented;

                  return (
                    <button
                      key={task.id}
                      onClick={() => implemented && navigate(`/topics/${task.id}`)}
                      disabled={!implemented}
                      className={cn(
                        'group relative flex flex-col items-start text-left p-4 rounded-xl border transition-all duration-200',
                        implemented
                          ? 'bg-card border-border hover:border-primary/50 hover:shadow-md cursor-pointer'
                          : 'bg-muted/30 border-border/50 cursor-not-allowed opacity-60',
                      )}
                    >
                      {/* Task number */}
                      <div
                        className={cn(
                          'flex items-center justify-center w-7 h-7 rounded-lg text-xs font-bold mb-3',
                          implemented
                            ? 'bg-primary/10 text-primary'
                            : 'bg-muted text-muted-foreground',
                        )}
                      >
                        {task.taskNumber}
                      </div>

                      {/* Title */}
                      <h3 className="text-sm font-semibold mb-1.5 leading-snug">{task.title}</h3>

                      {/* Description */}
                      <p className="text-xs text-muted-foreground leading-relaxed line-clamp-2 mb-3">
                        {task.description}
                      </p>

                      {/* Footer */}
                      <div className="flex items-center gap-2 mt-auto w-full">
                        <span
                          className={cn(
                            'text-[10px] px-1.5 py-0.5 rounded-full capitalize font-medium',
                            DIFFICULTY_COLORS[task.difficulty],
                          )}
                        >
                          {task.difficulty}
                        </span>
                        <span className="flex items-center gap-1 text-[10px] text-muted-foreground">
                          <Clock className="h-3 w-3" />
                          {task.duration}
                        </span>

                        {implemented && (
                          <ChevronRight className="h-3.5 w-3.5 text-muted-foreground ml-auto opacity-0 group-hover:opacity-100 transition-opacity" />
                        )}
                        {!implemented && (
                          <Lock className="h-3 w-3 text-muted-foreground/50 ml-auto" />
                        )}
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
