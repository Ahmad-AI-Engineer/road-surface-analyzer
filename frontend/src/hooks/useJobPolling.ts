import { useCallback, useEffect, useRef, useState } from 'react';
import { errorMessage, getJob } from '../api/client';
import type { Job } from '../api/types';

interface PollingState {
  job: Job | null;
  error: string | null;
  loading: boolean;
  offline: boolean;
  refresh: () => void;
}

const BASE_INTERVAL = 1000;
const MAX_INTERVAL = 8000;

/**
 * Polls GET /api/v1/jobs/{id} roughly once per second.
 * Stops on `done` / `failed`, backs off exponentially on network errors.
 */
export function useJobPolling(jobId: string | undefined): PollingState {
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [offline, setOffline] = useState(false);

  const timer = useRef<number | null>(null);
  const backoff = useRef(BASE_INTERVAL);
  const cancelled = useRef(false);
  const [nonce, setNonce] = useState(0);

  const refresh = useCallback(() => {
    backoff.current = BASE_INTERVAL;
    setNonce((n) => n + 1);
  }, []);

  useEffect(() => {
    if (!jobId) {
      setLoading(false);
      return;
    }

    cancelled.current = false;
    backoff.current = BASE_INTERVAL;

    const tick = async () => {
      try {
        const data = await getJob(jobId);
        if (cancelled.current) return;

        setJob(data);
        setError(null);
        setOffline(false);
        setLoading(false);
        backoff.current = BASE_INTERVAL;

        if (data.status === 'done' || data.status === 'failed' || data.status === 'cancelled') {
          return;
        }
      } catch (err) {
        if (cancelled.current) return;
        setLoading(false);
        const message = errorMessage(err);
        if (message.includes('404')) {
          setError('Job not found.');
          return;
        }
        setOffline(true);
        setError(message);
        backoff.current = Math.min(backoff.current * 2, MAX_INTERVAL);
      }

      timer.current = window.setTimeout(tick, backoff.current);
    };

    void tick();

    return () => {
      cancelled.current = true;
      if (timer.current !== null) window.clearTimeout(timer.current);
    };
  }, [jobId, nonce]);

  return { job, error, loading, offline, refresh };
}
