'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import { createClient } from '@/lib/supabase';

type StreamStatus = 'idle' | 'connecting' | 'streaming' | 'complete' | 'error';

interface Progress {
  step?: string;
  stepNum?: number;
  text?: string;
}

interface UseJobStreamReturn {
  status: StreamStatus;
  progress: Progress;
  result: unknown;
  error: string | null;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export function useJobStream(jobId: string | null): UseJobStreamReturn {
  const [status, setStatus] = useState<StreamStatus>('idle');
  const [progress, setProgress] = useState<Progress>({});
  const [result, setResult] = useState<unknown>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const reset = useCallback(() => {
    setStatus('idle');
    setProgress({});
    setResult(null);
    setError(null);
  }, []);

  useEffect(() => {
    if (!jobId) {
      reset();
      return;
    }

    const controller = new AbortController();
    abortRef.current = controller;

    let currentEventType = 'message';

    async function connect() {
      setStatus('connecting');
      setProgress({});
      setResult(null);
      setError(null);

      try {
        const supabase = createClient();
        const { data: sessionData } = await supabase.auth.getSession();
        const token = sessionData?.session?.access_token;

        const headers: Record<string, string> = {
          Accept: 'text/event-stream',
        };
        if (token) {
          headers['Authorization'] = `Bearer ${token}`;
        }

        const response = await fetch(`${API_URL}/api/jobs/${jobId}/stream`, {
          headers,
          signal: controller.signal,
        });

        if (!response.ok) {
          throw new Error(`Stream request failed: ${response.status}`);
        }

        if (!response.body) {
          throw new Error('Response body is null');
        }

        setStatus('streaming');

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (line.startsWith('event:')) {
              currentEventType = line.slice(6).trim();
            } else if (line.startsWith('data:')) {
              const dataStr = line.slice(5).trim();
              if (!dataStr) continue;

              let payload: Record<string, unknown>;
              try {
                payload = JSON.parse(dataStr);
              } catch {
                continue;
              }

              switch (currentEventType) {
                case 'progress':
                  setStatus('streaming');
                  setProgress((prev) => ({ ...prev, ...payload }));
                  break;
                case 'complete':
                  setStatus('complete');
                  setResult(payload);
                  break;
                case 'error':
                  setStatus('error');
                  setError(
                    (payload.error as string) || 'Unknown stream error'
                  );
                  break;
              }

              currentEventType = 'message';
            }
          }
        }
      } catch (err: unknown) {
        if (err instanceof DOMException && err.name === 'AbortError') {
          return;
        }
        setStatus('error');
        setError(
          err instanceof Error ? err.message : 'Failed to connect to stream'
        );
      }
    }

    connect();

    return () => {
      controller.abort();
      abortRef.current = null;
    };
  }, [jobId, reset]);

  return { status, progress, result, error };
}
