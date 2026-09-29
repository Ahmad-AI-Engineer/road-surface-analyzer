import { useCallback, useState } from 'react';
import { useDropzone } from 'react-dropzone';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { errorMessage, uploadVideo } from '../api/client';
import type { Health } from '../api/types';
import { useToast } from '../components/Toast';
import RoadScene from '../three/RoadScene';

const ACCEPT = {
  'video/mp4': ['.mp4', '.m4v'],
  'video/quicktime': ['.mov'],
  'video/x-msvideo': ['.avi'],
  'video/x-matroska': ['.mkv'],
  'video/webm': ['.webm'],
};

const CLASSES = [
  { name: 'Pothole', color: 'bg-hazard-pothole' },
  { name: 'Crack', color: 'bg-hazard-crack' },
  { name: 'Alligator cracking', color: 'bg-hazard-alligator' },
];

export default function UploadPage({ health }: { health: Health | null }) {
  const navigate = useNavigate();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [uploadPct, setUploadPct] = useState(0);

  const submit = useCallback(
    async (file: File) => {
      setBusy(true);
      setUploadPct(0);
      try {
        const created = await uploadVideo(file, setUploadPct);
        toast.push(`Queued "${created.filename}"`, 'success');
        navigate(`/jobs/${created.job_id}`);
      } catch (err) {
        toast.push(errorMessage(err), 'error');
        setBusy(false);
      }
    },
    [navigate, toast],
  );

  const onDrop = useCallback(
    (accepted: File[], rejected: unknown[]) => {
      if (rejected.length > 0) {
        toast.push('That file type is not supported.', 'error');
        return;
      }
      const file = accepted[0];
      if (file) void submit(file);
    },
    [submit, toast],
  );

  const { getRootProps, getInputProps, isDragActive, open } = useDropzone({
    onDrop,
    accept: ACCEPT,
    maxFiles: 1,
    multiple: false,
    noClick: true,
    disabled: busy,
  });

  const notConfigured = health && !health.roboflow_configured && !health.mock_detector;

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
      <section
        {...getRootProps()}
        className={`relative overflow-hidden rounded-2xl border transition ${
          isDragActive
            ? 'border-accent/70 shadow-glow'
            : 'border-white/5 hover:border-white/10'
        }`}
      >
        <RoadScene className="h-[440px] w-full" />
        <input {...getInputProps()} />

        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center bg-gradient-to-b from-ink-900/20 via-ink-900/40 to-ink-900/85 px-8 text-center">
          <motion.h1
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="text-2xl font-semibold text-slate-100 sm:text-3xl"
          >
            Drop a road video to analyze
          </motion.h1>
          <p className="mt-2 max-w-md text-sm text-slate-400">
            Frames are sampled locally and sent to the Roboflow Hosted Inference API.
            Potholes, cracks and alligator cracking are boxed on the returned video.
          </p>

          <div className="pointer-events-auto mt-6 flex flex-wrap items-center justify-center gap-3">
            <button
              type="button"
              onClick={open}
              disabled={busy}
              className="btn-primary"
            >
              {busy ? `Uploading ${uploadPct}%` : 'Choose video'}
            </button>
            <span className="text-xs text-slate-500">
              MP4 · MOV · AVI · MKV · WEBM
            </span>
          </div>

          {busy && (
            <div className="pointer-events-none mt-5 h-1 w-64 overflow-hidden rounded-full bg-white/10">
              <motion.div
                className="h-full bg-accent"
                initial={{ width: 0 }}
                animate={{ width: `${uploadPct}%` }}
                transition={{ ease: 'easeOut', duration: 0.2 }}
              />
            </div>
          )}
        </div>
      </section>

      <div className="flex flex-col gap-6">
        {notConfigured && (
          <div className="rounded-2xl border border-amber-500/40 bg-amber-950/40 p-4 text-sm text-amber-100">
            <div className="font-medium">Roboflow is not configured</div>
            <p className="mt-1 text-amber-200/80">
              Set <code className="font-mono">ROBOFLOW_API_KEY</code> in{' '}
              <code className="font-mono">.env</code>, or run with{' '}
              <code className="font-mono">MOCK_DETECTOR=1</code> to demo offline.
            </p>
          </div>
        )}

        <div className="panel">
          <div className="panel-title">Detected classes</div>
          <ul className="space-y-2">
            {CLASSES.map((c) => (
              <li key={c.name} className="flex items-center gap-3 text-sm text-slate-300">
                <span className={`h-2.5 w-2.5 rounded-sm ${c.color}`} />
                {c.name}
              </li>
            ))}
          </ul>
        </div>

        <div className="panel">
          <div className="panel-title">Pipeline</div>
          <ol className="space-y-3 text-sm text-slate-400">
            {[
              'Upload video',
              'Extract frames with OpenCV',
              `Send every ${health?.frame_stride ?? 5}th frame to Roboflow`,
              'Draw boxes, hold across skipped frames',
              'Rebuild H.264 video with ffmpeg',
            ].map((step, i) => (
              <li key={step} className="flex gap-3">
                <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full bg-white/5 font-mono text-[11px] text-accent">
                  {i + 1}
                </span>
                {step}
              </li>
            ))}
          </ol>
        </div>

        <div className="panel">
          <div className="panel-title">Current settings</div>
          <dl className="grid grid-cols-2 gap-4">
            <div>
              <dt className="stat-label">Model</dt>
              <dd className="mt-1 break-all font-mono text-xs text-slate-300">
                {health?.model_id ?? '—'}
              </dd>
            </div>
            <div>
              <dt className="stat-label">Confidence</dt>
              <dd className="stat-value">
                {health ? health.conf_threshold.toFixed(2) : '—'}
              </dd>
            </div>
            <div>
              <dt className="stat-label">Frame stride</dt>
              <dd className="stat-value">{health?.frame_stride ?? '—'}</dd>
            </div>
            <div>
              <dt className="stat-label">Mode</dt>
              <dd className="mt-1 text-sm text-slate-300">
                {health?.mock_detector ? 'Mock detector' : 'Hosted inference'}
              </dd>
            </div>
          </dl>
        </div>
      </div>
    </div>
  );
}
