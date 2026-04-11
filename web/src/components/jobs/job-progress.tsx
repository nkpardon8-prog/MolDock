'use client';

import ReactMarkdown from 'react-markdown';

type StreamStatus = 'idle' | 'connecting' | 'streaming' | 'complete' | 'error';

interface Progress {
  step?: string;
  stepNum?: number;
  totalSteps?: number;
  text?: string;
}

interface JobProgressProps {
  status: StreamStatus;
  progress: Progress;
  error: string | null;
}

export function JobProgress({ status, progress, error }: JobProgressProps) {
  if (status === 'idle' || status === 'complete') {
    return null;
  }

  if (status === 'connecting') {
    return (
      <div className="flex items-center gap-3 rounded-lg border border-zinc-700 bg-zinc-900 p-4">
        <div className="h-4 w-4 animate-spin rounded-full border-2 border-teal-400 border-t-transparent" />
        <span className="text-sm text-zinc-300">Connecting...</span>
      </div>
    );
  }

  if (status === 'error') {
    return (
      <div className="rounded-lg border border-red-500/50 bg-red-950/30 p-4">
        <p className="text-sm font-medium text-red-400">
          {error || 'An error occurred'}
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-zinc-700 bg-zinc-900 p-4">
      {progress.step && (
        <div className="mb-2 flex items-center gap-3">
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-teal-400 border-t-transparent" />
          <span className="text-sm text-zinc-300">
            {progress.stepNum != null && (
              <span className="font-mono text-teal-400">
                Step {progress.stepNum}
                {progress.totalSteps != null && `/${progress.totalSteps}`}
                :{' '}
              </span>
            )}
            {progress.step}
          </span>
        </div>
      )}
      {progress.text && (
        <div className="prose prose-sm prose-invert max-w-none">
          <ReactMarkdown>{progress.text}</ReactMarkdown>
        </div>
      )}
    </div>
  );
}
