import { useEffect, useState } from 'react';
import { NavLink, Route, Routes, useLocation } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { getHealth } from './api/client';
import type { Health } from './api/types';
import UploadPage from './pages/Upload';
import ProcessingPage from './pages/Processing';
import DashboardPage from './pages/Dashboard';
import HistoryPage from './pages/History';

const NAV = [
  { to: '/', label: 'Analyze', end: true },
  { to: '/history', label: 'History', end: false },
];

function HealthBadge({ health }: { health: Health | null }) {
  if (!health) {
    return <span className="skeleton h-6 w-40" />;
  }
  const mock = health.mock_detector;
  const ok = health.roboflow_configured || mock;
  const label = mock
    ? 'Mock detector'
    : health.roboflow_configured
      ? 'Roboflow connected'
      : 'Roboflow not configured';
  return (
    <div className="flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs">
      <span
        className={`h-2 w-2 rounded-full ${
          mock ? 'bg-amber-400' : ok ? 'bg-emerald-400' : 'bg-red-500'
        }`}
      />
      <span className="text-slate-300">{label}</span>
      <span className="font-mono text-slate-500">stride {health.frame_stride}</span>
    </div>
  );
}

export default function App() {
  const location = useLocation();
  const [health, setHealth] = useState<Health | null>(null);

  useEffect(() => {
    let active = true;
    getHealth()
      .then((h) => active && setHealth(h))
      .catch(() => active && setHealth(null));
    return () => {
      active = false;
    };
  }, []);

  return (
    <div className="flex min-h-full flex-col">
      <header className="sticky top-0 z-30 border-b border-white/5 bg-ink-900/80 backdrop-blur">
        <div className="mx-auto flex h-16 w-full max-w-[1400px] items-center gap-6 px-6">
          <div className="flex items-center gap-3">
            <div className="grid h-9 w-9 place-items-center rounded-lg bg-accent/15 text-accent">
              <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8">
                <path d="M4 20 9 4h6l5 16" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M12 7v3M12 13v3" strokeLinecap="round" />
              </svg>
            </div>
            <div className="leading-tight">
              <div className="text-sm font-semibold text-slate-100">
                Road Surface Conditions Analyzer
              </div>
              <div className="text-[11px] text-slate-500">
                Roboflow Hosted Inference · pothole / crack / alligator cracking
              </div>
            </div>
          </div>

          <nav className="ml-6 flex items-center gap-1">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `rounded-lg px-3 py-1.5 text-sm transition ${
                    isActive
                      ? 'bg-white/10 text-slate-100'
                      : 'text-slate-400 hover:bg-white/5 hover:text-slate-200'
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="ml-auto">
            <HealthBadge health={health} />
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-[1400px] flex-1 px-6 py-6">
        <AnimatePresence mode="wait">
          <motion.div
            key={location.pathname}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.25, ease: 'easeOut' }}
          >
            <Routes location={location}>
              <Route path="/" element={<UploadPage health={health} />} />
              <Route path="/jobs/:jobId" element={<ProcessingPage />} />
              <Route path="/jobs/:jobId/dashboard" element={<DashboardPage />} />
              <Route path="/history" element={<HistoryPage />} />
              <Route
                path="*"
                element={
                  <div className="panel text-center text-slate-400">
                    Page not found.
                  </div>
                }
              />
            </Routes>
          </motion.div>
        </AnimatePresence>
      </main>

      <footer className="border-t border-white/5 px-6 py-4 text-center text-[11px] text-slate-600">
        Demo build · detection quality and latency are bounded by the Roboflow Hosted
        Inference API
      </footer>
    </div>
  );
}
