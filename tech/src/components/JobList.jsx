import React, { useEffect, useState, useCallback, useMemo } from 'react';
import * as api from '../api/client.js';
import { cacheJobs, getCachedJobList } from '../db/offlineStore.js';

const PERIODS = [
  { key: 'day', label: 'Day', lookaheadDays: 0 },
  { key: 'week', label: 'Week', lookaheadDays: 6 },
  { key: 'month', label: 'Month', lookaheadDays: 29 },
  { key: 'quarter', label: 'Quarter', lookaheadDays: 89 },
];

function toDateInputValue(date) {
  const pad = (n) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/** Rolling look-ahead window starting today — e.g. "Week" = today + 6 more days. */
function rangeForPeriod(periodKey) {
  const period = PERIODS.find((p) => p.key === periodKey) || PERIODS[0];
  const from = new Date();
  const to = new Date();
  to.setDate(to.getDate() + period.lookaheadDays);
  return { from: toDateInputValue(from), to: toDateInputValue(to) };
}

function formatTime(iso) {
  if (!iso) return '--:--';
  return new Date(iso).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
}

function formatDateHeading(iso) {
  if (!iso) return 'Unscheduled';
  const date = new Date(iso);
  const today = new Date();
  const isToday = date.toDateString() === today.toDateString();
  const tomorrow = new Date(today);
  tomorrow.setDate(tomorrow.getDate() + 1);
  const isTomorrow = date.toDateString() === tomorrow.toDateString();
  if (isToday) return 'Today';
  if (isTomorrow) return 'Tomorrow';
  return date.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' });
}

function statusClass(status) {
  if (status === 'Completed') return 'completed';
  if (status === 'In Progress') return 'in-progress';
  return '';
}

export default function JobList({ onSelectJob }) {
  const [period, setPeriod] = useState('day');
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const range = useMemo(() => rangeForPeriod(period), [period]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      if (navigator.onLine) {
        const res = await api.getMyJobs({ from: range.from, to: range.to });
        const jobList = res.message || [];
        setJobs(jobList);
        await cacheJobs(period, jobList);
      } else {
        setJobs(await getCachedJobList(period));
      }
      setError(null);
    } catch (err) {
      // Fall back to whatever we last cached for this exact period.
      setJobs(await getCachedJobList(period));
      setError('Showing your last synced jobs — could not reach the server.');
    } finally {
      setLoading(false);
    }
  }, [period, range.from, range.to]);

  useEffect(() => {
    load();
  }, [load]);

  const sorted = [...jobs].sort((a, b) => (a.scheduled_start || '').localeCompare(b.scheduled_start || ''));

  // Group into date sections for anything wider than a single day, so a
  // month/quarter view reads as a schedule rather than one long list.
  const groups = useMemo(() => {
    if (period === 'day') return [{ heading: null, jobs: sorted }];
    const byDay = new Map();
    for (const job of sorted) {
      const dayKey = job.scheduled_start ? job.scheduled_start.slice(0, 10) : 'unscheduled';
      if (!byDay.has(dayKey)) byDay.set(dayKey, []);
      byDay.get(dayKey).push(job);
    }
    return [...byDay.entries()].map(([dayKey, dayJobs]) => ({
      heading: dayJobs[0]?.scheduled_start ? formatDateHeading(dayJobs[0].scheduled_start) : 'Unscheduled',
      jobs: dayJobs,
    }));
  }, [sorted, period]);

  const emptyLabel = {
    day: 'No jobs assigned for today',
    week: 'No jobs assigned this week',
    month: 'No jobs assigned this month',
    quarter: 'No jobs assigned this quarter',
  }[period];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 style={{ fontSize: 18, margin: '4px 0 12px' }}>Your Jobs</h2>
        <button className="btn btn-outline" style={{ minHeight: 36, padding: '0 12px', fontSize: 13 }} onClick={load}>
          Refresh
        </button>
      </div>

      <div className="action-row" style={{ gridTemplateColumns: `repeat(${PERIODS.length}, 1fr)`, marginBottom: 14 }}>
        {PERIODS.map((p) => (
          <button
            key={p.key}
            className={p.key === period ? 'btn btn-primary' : 'btn btn-outline'}
            style={{ minHeight: 38, fontSize: 13, padding: '0 8px' }}
            onClick={() => setPeriod(p.key)}
          >
            {p.label}
          </button>
        ))}
      </div>

      {error && (
        <div className="card" style={{ borderColor: 'var(--lcs-gold)', fontSize: 13 }}>{error}</div>
      )}

      {loading && jobs.length === 0 && <p style={{ color: 'var(--lcs-text-muted)' }}>Loading your jobs…</p>}

      {!loading && sorted.length === 0 && (
        <div className="empty-state">
          <p style={{ fontSize: 15, fontWeight: 700 }}>{emptyLabel}</p>
          <p style={{ fontSize: 13 }}>Pull to refresh, or check with dispatch if this looks wrong.</p>
        </div>
      )}

      {groups.map((group, i) => (
        <div key={group.heading || i}>
          {group.heading && <div className="section-label">{group.heading}</div>}
          {group.jobs.map((job) => (
            <button key={job.name} className="card job-card" onClick={() => onSelectJob(job.name)}>
              <div className="job-card-top">
                <span className="job-time">{formatTime(job.scheduled_start)}</span>
                <span className={`job-status ${statusClass(job.status)}`}>{job.status}</span>
              </div>
              <div className="job-customer">{job.customer_name}</div>
              <div className="job-address">{job.site_address}</div>
              <div style={{ fontSize: 11, color: 'var(--lcs-text-muted)', marginTop: 4 }}>{job.name}</div>
              {job.is_crew_leader ? (
                <div style={{ marginTop: 6, fontSize: 11, fontWeight: 700, color: 'var(--lcs-crimson)' }}>CREW LEADER</div>
              ) : null}
            </button>
          ))}
        </div>
      ))}
    </div>
  );
}
