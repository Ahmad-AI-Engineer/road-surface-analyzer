import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { cancelJob, errorMessage, getDetections } from '../api/client';
import type { DetectionItem } from '../api/types';
import { useToast } from '../components/Toast';
import { useJobPolling } from '../hooks/useJobPolling';
import ProgressRing from '../three/ProgressRing';

function formatEta(seconds: number | null): string {
  if (seconds === null || Number.isNaN(seconds)) return '—';
  if (seconds < 1) return '<1s';
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-xl border border-white/5 bg-white/[0.03] px-4 py-3">
      <div className="stat-label">{label}</div>
      <div className="stat-value mt-1">{value}</div>
    </div>
  );
}

export default function ProcessingPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();
  const toast = useToast();
  const { job, error, loading, offline, refresh } = useJobPolling(jobId);
  const [ticker, setTicker] = useState<DetectionItem[]>([]);
  const [cancelling, setCancelling] = useState(false);
  const redirected = useRef(false);
  const status = job?.status;

  useEffect(() => {
    if (job?.status === 'done' && !redirected.current) {
      redirected.current = true;
      const timeout = window.setTimeout(
        () => navigate(`/jobs/${job.id}/dashboard`, { replace: true }),
        900,
      );
      return () => window.clearTimeout(timeout);
    }
  }, [job?.status, job?.id, navigate]);

  // Rolling preview of detections found so far.
  useEffect(() => {
    if (!jobId || status !== 'processing') return;
    let active = true;
    const load = () => {
      getDetections(jobId, 12, 0, 'desc')
        .then((page) => active && setTicker(page.items))
        .catch(() => undefined);
    };
    load();
    const id = window.setInterval(load, 3000);
    return () => {
      active = false;
      window.clearInterval(id);
    };
  }, [jobId, status]);

  const handleCancel = async () => {
    if (!jobId || cancelling) return;
    if (!window.confirm('Stop processing this video? Progress made so far will be lost.')) {
      return;
    }
    setCancelling(true);
    try {
      await cancelJob(jobId);
      toast.push('Stopping…', 'info');
      refresh();
    } catch (err) {
      toast.push(errorMessage(err), 'error');
    } finally {
      setCancelling(false);
    }
  };

  const progress = job?.progress ?? 0;
  const framesLabel = useMemo(() => {
    if (!job) return '—';
    const total = job.frames_total || 0;
    return total > 0
      ? `${job.frames_processed} / ${total}`      : String(job.frames_processed);
  }, [job]);

  if (loading) {
    return (
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,420px)]">
        <div className="skeleton h-[420px]" />
        <div className="skeleton h-[420px]" />
      </div>
    );
  }

  if (error && !job) {
    return (
      <div className="panel text-center">
        <p className="text-slate-300">{error}</p>
        <div className="mt-4 flex justify-center gap-3">
          <button className="btn-ghost" onClick={refresh}>
            Retry
          </button>
          <Link className="btn-primary" to="/">
            Back to upload
          </Link>
        </div>
      </div>
    );
  }

  if (!job) return null;

  if (job.status === 'failed') {
    return (
      <div className="panel mx-auto max-w-xl text-center">
        <div className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-red-500/15 text-red-400">
          !
        </div>
        <h2 className="mt-4 text-lg font-semibold text-slate-100">Processing failed</h2>
        <p className="mt-2 text-sm text-slate-400">{job.error ?? 'Unknown error.'}</p>
        <div className="mt-6 flex justify-center gap-3">
          <Link className="btn-primary" to="/">
            Try another video
          </Link>
          <Link className="btn-ghost" to="/history">
            History
          </Link>
        </div>
      </div>
    );
  }

  if (job.status === 'cancelled') {
    return (
      <div className="panel mx-auto max-w-xl text-center">
        <div className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-slate-500/15 text-slate-300">
          ■
        </div>
        <h2 className="mt-4 text-lg font-semibold text-slate-100">Processing stopped</h2>
        <p className="mt-2 text-sm text-slate-400">
          You stopped this job before it finished. No video was produced.
        </p>
        <div className="mt-6 flex justify-center gap-3">
          <Link className="btn-primary" to="/">
            Try another video
          </Link>
          <Link className="btn-ghost" to="/history">
            History
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,420px)]">
      <section className="panel relative flex flex-col items-center justify-center">
        <div className="absolute left-5 top-5 text-left">
          <div className="text-xs uppercase tracking-widest text-slate-500">
            {job.status === 'queued' ? 'Queued' : 'Processing'}
          </div>
          <div className="mt-1 max-w-[280px] truncate text-sm text-slate-300">
            {job.filename}
          </div>
        </div>
        {job.mocked && (
          <span className="absolute right-5 top-5 rounded-full border border-amber-500/40 bg-amber-500/10 px-3 py-1 text-[11px] text-amber-200">
            Mock detector
          </span>
        )}

        <ProgressRing
          progress={progress}
          label={job.status === 'queued' ? 'Queued' : 'Analyzing'}
          className="h-[340px] w-full"
        />

        {offline && (
          <div className="mt-2 rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1 text-xs text-amber-200">
            Backend unreachable — retrying
          </div>
        )}

        <div className="mt-4 grid w-full grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label="Frames" value={framesLabel} />
          <Stat label="ETA" value={formatEta(job.eta_sec)} />
          <Stat label="Roboflow calls" value={job.api_calls} />
          <Stat label="Detections" value={job.summary.total_detections} />
        </div>

        <button
          type="button"
          onClick={handleCancel}
          disabled={cancelling}
          className="btn-ghost mt-4 border border-red-500/30 text-red-300 hover:bg-red-500/10 disabled:opacity-50"
        >
          {cancelling ? 'Stopping…' : 'Stop processing'}
        </button>
      </section>

      <aside className="flex flex-col gap-6">
        <div className="panel">
          <div className="panel-title">Job configuration</div>
          <dl className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <dt className="stat-label">Frame stride</dt>
              <dd className="mt-1 font-mono text-slate-200">{job.frame_stride}</dd>
            </div>
            <div>
              <dt className="stat-label">Confidence</dt>
              <dd className="mt-1 font-mono text-slate-200">
                {job.conf_threshold.toFixed(2)}
              </dd>
            </div>
            <div>
              <dt className="stat-label">Resolution</dt>
              <dd className="mt-1 font-mono text-slate-200">
                {job.width && job.height ? `${job.width}×${job.height}` : '—'}
              </dd>
            </div>
            <div>
              <dt className="stat-label">Avg API latency</dt>
              <dd className="mt-1 font-mono text-slate-200">
                {job.api_latency_ms ? `${Math.round(job.api_latency_ms)} ms` : '—'}
              </dd>
            </div>
          </dl>
          {job.api_failures > 0 && (
            <p className="mt-4 rounded-lg bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
              {job.api_failures} frame(s) failed inference and reused previous boxes.
            </p>
          )}
        </div>

        <div className="panel flex-1">
          <div className="panel-title">Live detections</div>
          <div className="space-y-2">
            <AnimatePresence initial={false}>
              {ticker.length === 0 && (
                <p className="text-sm text-slate-500">Waiting for detections…</p>
              )}
              {ticker.map((det) => (
                <motion.div
                  key={`${det.frame_idx}-${det.class_name}-${det.confidence}`}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0 }}
                  className="flex items-center justify-between rounded-lg border border-white/5 bg-white/[0.03] px-3 py-2 text-sm"
                >
                  <span className="text-slate-300">{det.class_name}</span>
                  <span className="font-mono text-xs text-slate-500">
                    {det.timestamp_sec.toFixed(1)}s · {(det.confidence * 100).toFixed(0)}%
                  </span>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        </div>
      </aside>
    </div>
  );
}
