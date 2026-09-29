import { useCallback, useEffect, useState, type MouseEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { deleteJob, errorMessage, getStats, listJobs } from '../api/client';
import type { Job, Stats } from '../api/types';
import { useToast } from '../components/Toast';

const STATUS_STYLE: Record<Job['status'], string> = {
  queued: 'bg-slate-500/15 text-slate-300',
  processing: 'bg-accent/15 text-accent',
  done: 'bg-emerald-500/15 text-emerald-300',
  failed: 'bg-red-500/15 text-red-300',
  cancelled: 'bg-slate-500/15 text-slate-400',
};

function formatDate(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString();
}

export default function HistoryPage() {
  const navigate = useNavigate();
  const toast = useToast();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([listJobs(24), getStats()])
      .then(([list, s]) => {
        setJobs(list.items);
        setStats(s);
      })
      .catch((err) => toast.push(errorMessage(err), 'error'))
      .finally(() => setLoading(false));
  }, [toast]);

  useEffect(load, [load]);

  const remove = useCallback(
    async (job: Job, event: MouseEvent) => {
      event.stopPropagation();
      try {
        await deleteJob(job.id);
        setJobs((prev) => prev.filter((j) => j.id !== job.id));
        toast.push('Job deleted', 'success');
      } catch (err) {
        toast.push(errorMessage(err), 'error');
      }
    },
    [toast],
  );

  const openJob = useCallback(
    (job: Job) => {
      navigate(job.status === 'done' ? `/jobs/${job.id}/dashboard` : `/jobs/${job.id}`);
    },
    [navigate],
  );

  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {[
          { label: 'Jobs', value: stats?.jobs_total ?? '—' },
          { label: 'Completed', value: stats?.jobs_done ?? '—' },
          { label: 'Failed', value: stats?.jobs_failed ?? '—' },
          { label: 'Detections', value: stats?.detections_total ?? '—' },
          { label: 'Roboflow calls', value: stats?.api_calls_total ?? '—' },
        ].map((s) => (
          <div key={s.label} className="panel py-4">
            <div className="stat-label">{s.label}</div>
            <div className="stat-value mt-1">{s.value}</div>
          </div>
        ))}
      </div>

      <section>
        <div className="mb-4 flex items-center gap-3">
          <h2 className="text-sm font-semibold uppercase tracking-[0.18em] text-slate-400">
            Past analyses
          </h2>
          <button className="btn-ghost ml-auto px-3 py-1 text-xs" onClick={load}>
            Refresh
          </button>
        </div>

        {loading ? (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {[0, 1, 2].map((i) => (
              <div key={i} className="skeleton h-56" />
            ))}
          </div>
        ) : jobs.length === 0 ? (
          <div className="panel flex flex-col items-center gap-3 py-12 text-center">
            <p className="text-slate-400">No analyses yet.</p>
            <Link className="btn-primary" to="/">
              Analyze a video
            </Link>
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {jobs.map((job, i) => (
              <motion.button
                key={job.id}
                type="button"
                onClick={() => openJob(job)}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: Math.min(i * 0.04, 0.3) }}
                className="group overflow-hidden rounded-2xl border border-white/5 bg-ink-800/70 text-left transition hover:border-accent/40 hover:shadow-glow"
              >
                <div className="relative aspect-video bg-ink-700">
                  {job.thumb_url ? (
                    <img
                      src={job.thumb_url}
                      alt=""
                      loading="lazy"
                      className="h-full w-full object-cover opacity-90 transition group-hover:opacity-100"
                    />
                  ) : (
                    <div className="grid h-full place-items-center text-xs text-slate-600">
                      No preview
                    </div>
                  )}
                  <span
                    className={`absolute left-3 top-3 rounded-full px-2.5 py-1 text-[11px] font-medium ${STATUS_STYLE[job.status]}`}
                  >
                    {job.status}
                  </span>
                  {job.mocked && (
                    <span className="absolute right-3 top-3 rounded-full bg-amber-500/20 px-2 py-0.5 text-[10px] text-amber-200">
                      mock
                    </span>
                  )}
                </div>

                <div className="p-4">
                  <div className="truncate text-sm font-medium text-slate-200">
                    {job.filename}
                  </div>
                  <div className="mt-1 text-[11px] text-slate-500">
                    {formatDate(job.created_at)}
                  </div>

                  <div className="mt-3 flex items-center justify-between text-xs text-slate-400">
                    <span className="font-mono">
                      {job.summary.total_detections} detections
                    </span>
                    <span
                      role="button"
                      tabIndex={0}
                      onClick={(e) => void remove(job, e)}
                      onKeyDown={(e) => e.stopPropagation()}
                      className="rounded px-2 py-1 text-slate-500 transition hover:bg-red-500/10 hover:text-red-300"
                    >
                      Delete
                    </span>
                  </div>
                </div>
              </motion.button>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
