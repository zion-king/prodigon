// ---------------------------------------------------------------------------
// ContentPage — /topics/:taskId/:subtopicId — fetches and displays markdown
// ---------------------------------------------------------------------------

import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getTask, getSubtopic } from '@/lib/topics-data';
import { fetchWorkshopContent } from '@/api/workshop';
import { ApiRequestError } from '@/api/types';
import { ContentViewer } from '@/components/topics/content-viewer';

type State = 'loading' | 'success' | 'not-found' | 'error';

export function ContentPage() {
  const { taskId = '', subtopicId = '' } = useParams<{ taskId: string; subtopicId: string }>();
  const navigate = useNavigate();

  const [state, setState] = useState<State>('loading');
  const [content, setContent] = useState('');

  const task = getTask(taskId);
  const subtopic = getSubtopic(taskId, subtopicId);

  useEffect(() => {
    if (!task || !subtopic) {
      setState('not-found');
      return;
    }

    if (!subtopic.filePath) {
      setState('not-found');
      return;
    }

    setState('loading');
    setContent('');

    fetchWorkshopContent(subtopic.filePath)
      .then((md) => {
        setContent(md);
        setState('success');
      })
      .catch((err) => {
        // if (err instanceof ApiRequestError && err.status === 404) {
        //   setState('not-found');
        // } else {
        //   setState('error');
        // }
        if (err instanceof ApiRequestError || err.status === 404) { 
          // using this in the meantime - `content not found` in either case, ignoring error loading content
          setState('not-found');
        }
      });
  }, [task, subtopic]);

  // Redirect if task or subtopic completely unknown
  if (!task) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center">
          <p className="text-muted-foreground mb-2">Task not found.</p>
          <button
            onClick={() => navigate('/topics')}
            className="text-sm text-primary hover:underline"
          >
            Back to Workshop
          </button>
        </div>
      </div>
    );
  }

  if (!subtopic) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center">
          <p className="text-muted-foreground mb-2">Subtopic not found.</p>
          <button
            onClick={() => navigate(`/topics/${taskId}`)}
            className="text-sm text-primary hover:underline"
          >
            Back to {task.title}
          </button>
        </div>
      </div>
    );
  }

  return (
    <ContentViewer
      task={task}
      subtopic={subtopic}
      state={state}
      content={content}
    />
  );
}
