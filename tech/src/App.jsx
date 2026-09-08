import React, { useEffect, useState, useCallback } from 'react';
import JobList from './components/JobList.jsx';
import JobDetail from './components/JobDetail.jsx';
import TimeTracker from './components/TimeTracker.jsx';
import { syncNow } from './db/sync.js';
import { getQueuedMutations } from './db/offlineStore.js';
import * as api from './api/client.js';
import { useTheme } from './hooks/useTheme.js';

export default function App() {
  const [screen, setScreen] = useState('jobs'); // 'jobs' | 'jobDetail' | 'day'
  const [selectedJob, setSelectedJob] = useState(null);
  const [employee, setEmployee] = useState(null);
  const [capacity, setCapacity] = useState('light'); // resolved from employee/vehicle assignment server-side
  const [online, setOnline] = useState(navigator.onLine);
  const [pendingCount, setPendingCount] = useState(0);
  const [theme, toggleTheme] = useTheme();

  const refreshPending = useCallback(async () => {
    const q = await getQueuedMutations();
    setPendingCount(q.length);
  }, []);

  useEffect(() => {
    const goOnline = () => setOnline(true);
    const goOffline = () => setOnline(false);
    window.addEventListener('online', goOnline);
    window.addEventListener('offline', goOffline);
    return () => {
      window.removeEventListener('online', goOnline);
      window.removeEventListener('offline', goOffline);
    };
  }, []);

  useEffect(() => {
    refreshPending();
    const interval = setInterval(refreshPending, 5000);
    return () => clearInterval(interval);
  }, [refreshPending]);

  useEffect(() => {
    (async () => {
      try {
        // Was previously api.whoAmI() (frappe.auth.get_logged_user), which
        // returns the session USERNAME (e.g. "lstacy@leftcoastscales.com"),
        // not the Employee record ID. Since LCS Tech Day Log.employee is a
        // Link field to Employee, every submit_time_action sync was
        // silently failing Link validation server-side — this is very
        // likely why no day log or Attendance record was ever appearing.
        const res = await api.getCurrentTechnician();
        setEmployee(res.message.employee);
      } catch {
        // Session cookie will still be present when back online; the
        // app works fully offline off the last known identity/cache.
      }
    })();
  }, []);

  const syncPillClass = !online ? 'offline' : pendingCount > 0 ? 'pending' : 'synced';
  const syncPillLabel = !online ? 'Offline' : pendingCount > 0 ? `${pendingCount} syncing…` : 'Synced';

  return (
    <div className="app-shell">
      <header className="app-header">
        <h1>LCS Field Tech</h1>
        <div className="header-actions">
          <button
            type="button"
            className="theme-toggle"
            onClick={toggleTheme}
            aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
            title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
          >
            {theme === 'dark' ? '☀' : '☾'}
          </button>
          <span
            className={`sync-pill ${syncPillClass}`}
            onClick={() => online && syncNow().then(refreshPending)}
          >
            ● {syncPillLabel}
          </span>
        </div>
      </header>

      <main className="app-main">
        {screen === 'jobs' && (
          <JobList
            onSelectJob={(name) => {
              setSelectedJob(name);
              setScreen('jobDetail');
            }}
          />
        )}

        {screen === 'jobDetail' && selectedJob && (
          <JobDetail
            appointmentName={selectedJob}
            employee={employee}
            capacity={capacity}
            onBack={() => setScreen('jobs')}
          />
        )}

        {screen === 'day' && (
          <div>
            <h2 style={{ fontSize: 18, margin: '4px 0 12px' }}>My Day</h2>
            <TimeTracker employee={employee} capacity={capacity} />

            <div className="section-label" style={{ marginTop: 20 }}>Truck Check</div>
            <div className="card">
              <p style={{ fontSize: 13, color: 'var(--lcs-text-muted)', marginTop: 0, marginBottom: 10 }}>
                Opens the full vehicle inspection form in a new tab — pick whichever applies to what you're driving today.
              </p>
              <div className="action-row two-col">
                <a
                  href="/vehicle-inspection/dot"
                  target="_blank"
                  rel="noreferrer"
                  className="btn btn-outline btn-full"
                >
                  DOT Inspection
                </a>
                <a
                  href="/vehicle-inspection/light"
                  target="_blank"
                  rel="noreferrer"
                  className="btn btn-outline btn-full"
                >
                  Light Vehicle
                </a>
              </div>
            </div>
          </div>
        )}
      </main>

      <nav className="bottom-tabbar">
        <button className={screen === 'jobs' || screen === 'jobDetail' ? 'active' : ''} onClick={() => setScreen('jobs')}>
          <span className="tab-icon">🗂</span>
          Jobs
        </button>
        <button className={screen === 'day' ? 'active' : ''} onClick={() => setScreen('day')}>
          <span className="tab-icon">🕐</span>
          My Day
        </button>
        <a href="/shortcuts" target="_blank" rel="noreferrer">
          <span className="tab-icon">⚡</span>
          Quick Access
        </a>
      </nav>
    </div>
  );
}
