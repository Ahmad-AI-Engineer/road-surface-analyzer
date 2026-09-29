import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  Bar,
  BarChart,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  detectionsExportUrl,
  errorMessage,
  getDetections,
  getJob,
} from '../api/client';
import type { DetectionItem, Job } from '../api/types';
import { useToast } from '../components/Toast';
import SeverityField from '../three/SeverityField';

const CLASS_COLOR: Record<string, string> = {
  pothole: '#ef4444',
  crack: '#f1c40f',
  'alligator-cracking': '#9b5cb0',
  'alligator cracking': '#9b5cb0',
  alligator_cracking: '#9b5cb0',
};

function colorFor(name: string): string {
  return CLASS_COLOR[name.toLowerCase()] ?? '#38bdf8';
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

const tooltipStyle = {
  background: '#121826',
  border: '1px solid rgba(255,255,255,0.08)',
  borderRadius: 8,
  fontSize: 12,
  color: '#e2e8f0',
};

export default function DashboardPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const toast = useToast();
  const videoRef = useRef<HTMLVideoElement>(null);

  const [job, setJob] = useState<Job | null>(null);
  const [detections, setDetections] = useState<DetectionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState<string | null>(null);
  const [currentTime, setCurrentTime] = useState(0);

  useEffect(() => {
    if (!jobId) return;
    let active = true;
    setLoading(true);
    Promise.all([getJob(jobId), getDetections(jobId, 5000)])
      .then(([jobData, page]) => {
        if (!active) return;
        setJob(jobData);
        setDetections(page.items);
        setFailed(null);
      })
      .catch((err) => active && setFailed(errorMessage(err)))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [jobId]);

  const duration = job?.duration_sec ?? 0;

  const seek = useCallback((seconds: number) => {
    if (videoRef.current) {
      videoRef.current.currentTime = seconds;
      void videoRef.current.play().catch(() => undefined);
    }
  }, []);

  const classData = useMemo(
    () =>
      (job?.summary.by_class ?? []).map((c) => ({
        name: c.class_name,
        value: c.count,
        avg: Math.round(c.avg_confidence * 100),
      })),
    [job],
  );

  const timelineData = useMemo(() => {
    if (detections.length === 0 || duration <= 0) return [];
    const bucketSec = 10;
    const buckets = new Map<number, number>();
    const count = Math.ceil(duration / bucketSec);
    for (let i = 0; i < count; i += 1) buckets.set(i, 0);
    for (const det of detections) {
      const idx = Math.floor(det.timestamp_sec / bucketSec);
      buckets.set(idx, (buckets.get(idx) ?? 0) + 1);
    }
    return Array.from(buckets.entries())
      .sort((a, b) => a[0] - b[0])
      .map(([idx, value]) => ({ label: `${idx * bucketSec}s`, count: value }));
  }, [detections, duration]);

  const histogramData = useMemo(() => {
    const bins = new Array(10).fill(0);
    for (const det of detections) {
      bins[Math.min(9, Math.max(0, Math.floor(det.confidence * 10)))] += 1;
    }
    return bins.map((count, i) => ({
      label: `${i * 10}–${(i + 1) * 10}%`,
      count,
    }));
  }, [detections]);

  const markers = useMemo(() => {
    if (duration <= 0) return [];
    const seen = new Set<number>();
    const out: { pct: number; det: DetectionItem }[] = [];
    for (const det of detections) {
      const key = Math.round(det.timestamp_sec * 2);
      if (seen.has(key)) continue;
      seen.add(key);
      out.push({ pct: (det.timestamp_sec / duration) * 100, det });
    }
    return out;
  }, [detections, duration]);

  const download = useCallback(
    (format: 'json' | 'csv') => {
      if (!jobId) return;
      window.open(detectionsExportUrl(jobId, format), '_blank', 'noopener,noreferrer');
      toast.push(`Exporting ${format.toUpperCase()}…`);
    },
    [jobId, toast],
  );

  if (loading) {
    return (
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <div className="skeleton h-[480px]" />
        <div className="skeleton h-[480px]" />
      </div>
    );
  }

  if (failed || !job) {
    return (
      <div className="panel text-center">
        <p className="text-slate-300">{failed ?? 'Job not found.'}</p>
        <Link className="btn-primary mt-4" to="/history">
          Back to history
        </Link>
      </div>
    );
  }

  if (job.status !== 'done') {
    return (
      <div className="panel text-center">
        <p className="text-slate-300">This job is not finished yet.</p>
        <Link className="btn-primary mt-4" to={`/jobs/${job.id}`}>
          View progress
        </Link>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center gap-4">
        <div className="min-w-0">
          <h1 className="truncate text-lg font-semibold text-slate-100">
            {job.filename}
          </h1>
          <p className="text-xs text-slate-500">
            {job.width}×{job.height} · {job.fps_in?.toFixed(1)} fps ·{' '}
            {formatTime(duration)} · stride {job.frame_stride}
            {job.mocked ? ' · mock detector' : ''}
          </p>
        </div>
        <div className="ml-auto flex gap-2">
          <button className="btn-ghost" onClick={() => download('json')}>
            Export JSON
          </button>
          <button className="btn-ghost" onClick={() => download('csv')}>
            Export CSV
          </button>
          <Link className="btn-primary" to="/">
            New analysis
          </Link>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <section className="panel">
          <div className="overflow-hidden rounded-xl bg-black">
            {job.video_url ? (
              <video
                ref={videoRef}
                src={job.video_url}
                poster={job.thumb_url ?? undefined}
                controls
                playsInline
                preload="metadata"
                className="aspect-video w-full"
                onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)}
              />
            ) : (
              <div className="grid aspect-video place-items-center text-sm text-slate-500">
                Processed video unavailable.
              </div>
            )}
          </div>

          <div className="mt-4">
            <div className="mb-2 flex items-center justify-between text-xs text-slate-500">
              <span>Detection timeline — click a marker to seek</span>
              <span className="font-mono">
                {formatTime(currentTime)} / {formatTime(duration)}
              </span>
            </div>
            <div className="relative h-10 rounded-lg border border-white/5 bg-white/[0.03]">
              <div
                className="absolute top-0 h-full w-0.5 bg-accent"
                style={{
                  left: `${duration > 0 ? (currentTime / duration) * 100 : 0}%`,
                }}
              />
              {markers.map(({ pct, det }, i) => (
                <button
                  key={`${det.frame_idx}-${i}`}
                  type="button"
                  title={`${det.class_name} ${(det.confidence * 100).toFixed(0)}% @ ${det.timestamp_sec.toFixed(1)}s`}
                  onClick={() => seek(det.timestamp_sec)}
                  className="absolute top-1/2 h-4 w-1 -translate-y-1/2 rounded-sm opacity-80 transition hover:h-6 hover:opacity-100"
                  style={{
                    left: `${pct}%`,
                    backgroundColor: colorFor(det.class_name),
                  }}
                />
              ))}
              {markers.length === 0 && (
                <span className="absolute inset-0 grid place-items-center text-xs text-slate-600">
                  No detections
                </span>
              )}
            </div>
          </div>

          <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              { label: 'Detections', value: job.summary.total_detections },
              { label: 'Frames', value: job.frames_total },
              { label: 'Roboflow calls', value: job.api_calls },
              {
                label: 'Avg latency',
                value: job.api_latency_ms ? `${Math.round(job.api_latency_ms)}ms` : '—',
              },
            ].map((s) => (
              <div
                key={s.label}
                className="rounded-xl border border-white/5 bg-white/[0.03] px-4 py-3"
              >
                <div className="stat-label">{s.label}</div>
                <div className="stat-value mt-1">{s.value}</div>
              </div>
            ))}
          </div>
        </section>

        <section className="panel">
          <div className="panel-title">Class distribution</div>
          {classData.length === 0 ? (
            <p className="text-sm text-slate-500">No detections recorded.</p>
          ) : (
            <ResponsiveContainer width="100%" height={240}>
              <PieChart>
                <Pie
                  data={classData}
                  dataKey="value"
                  nameKey="name"
                  innerRadius={58}
                  outerRadius={92}
                  paddingAngle={3}
                  stroke="none"
                >
                  {classData.map((entry) => (
                    <Cell key={entry.name} fill={colorFor(entry.name)} />
                  ))}
                </Pie>
                <Tooltip contentStyle={tooltipStyle} />
                <Legend
                  verticalAlign="bottom"
                  iconType="circle"
                  formatter={(value) => (
                    <span className="text-xs text-slate-400">{value}</span>
                  )}
                />
              </PieChart>
            </ResponsiveContainer>
          )}

          <div className="mt-4 space-y-2">
            {job.summary.by_class.map((c) => (
              <div
                key={c.class_name}
                className="flex items-center justify-between rounded-lg bg-white/[0.03] px-3 py-2 text-sm"
              >
                <span className="flex items-center gap-2 text-slate-300">
                  <span
                    className="h-2.5 w-2.5 rounded-sm"
                    style={{ backgroundColor: colorFor(c.class_name) }}
                  />
                  {c.class_name}
                </span>
                <span className="font-mono text-xs text-slate-500">
                  {c.count} · avg {(c.avg_confidence * 100).toFixed(0)}%
                </span>
              </div>
            ))}
          </div>
        </section>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="panel">
          <div className="panel-title">Detections per 10 seconds</div>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={timelineData}>
              <XAxis dataKey="label" tick={{ fill: '#64748b', fontSize: 11 }} tickLine={false} axisLine={false} />
              <YAxis tick={{ fill: '#64748b', fontSize: 11 }} tickLine={false} axisLine={false} allowDecimals={false} />
              <Tooltip contentStyle={tooltipStyle} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
              <Bar dataKey="count" fill="#38bdf8" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </section>

        <section className="panel">
          <div className="panel-title">Confidence distribution</div>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={histogramData}>
              <XAxis dataKey="label" tick={{ fill: '#64748b', fontSize: 10 }} tickLine={false} axisLine={false} interval={1} />
              <YAxis tick={{ fill: '#64748b', fontSize: 11 }} tickLine={false} axisLine={false} allowDecimals={false} />
              <Tooltip contentStyle={tooltipStyle} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
              <Bar dataKey="count" fill="#9b5cb0" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </section>
      </div>

      <section className="panel">
        <div className="panel-title">Damage severity field</div>
        <SeverityField
          detections={detections}
          durationSec={duration}
          className="h-[320px] w-full overflow-hidden rounded-xl"
        />
        <p className="mt-3 text-xs text-slate-500">
          Each column is a time slice; each row is a damage class. Bar height combines
          detection count and average confidence. Drag to orbit.
        </p>
      </section>
    </div>
  );
}
