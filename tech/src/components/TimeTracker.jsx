import React, { useEffect, useState, useCallback, useRef } from 'react';
import {
  ACTIONS,
  DAY_STATES,
  SEGMENT_TYPES,
  applyAction,
  createDayLog,
  currentContext,
  summarizeDay,
  toLocalDatetimeString,
} from '../state/timeTrackingMachine.js';
import { loadDayLog, saveDayLog, enqueueMutation } from '../db/offlineStore.js';
import * as api from '../api/client.js';
import { extractErrorMessage } from '../api/client.js';
import ClockCorrectionModal from './ClockCorrectionModal.jsx';
import PauseJobModal from './PauseJobModal.jsx';
import SendReportModal from './SendReportModal.jsx';
import ConfirmModal from './ConfirmModal.jsx';
import ReturnFromLunchModal from './ReturnFromLunchModal.jsx';

// Local calendar date, NOT UTC — new Date().toISOString() would return the
// UTC date, which drifts from the technician's actual workday for hours
// at a time in any timezone behind UTC (all of them, for LCS). This is
// what "day" means for a day log: the technician's own calendar day, not
// a UTC one that flips over at an arbitrary time relative to their shift.
const todayISO = () => {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
};

const BANNER_LABEL = {
  [SEGMENT_TYPES.TRAVEL]: 'Traveling',
  [SEGMENT_TYPES.PREP]: 'Truck inspection',
  [SEGMENT_TYPES.ONSITE]: 'On site',
  [SEGMENT_TYPES.SHOP]: 'At shop',
};

/**
 * TimeTracker is context-aware: if `jobRef` is set (rendered inside a Job
 * Detail screen), Arrive/Leave actions tie to that appointment. If not
 * (rendered on the Today's Jobs / global screen), Arrive/Leave apply to
 * the shop, and Start of Day / End of Day controls are shown instead.
 */
export default function TimeTracker({ employee, jobRef = null, capacity = 'light', onChanged, onJobCompleted }) {
  const [dayLog, setDayLog] = useState(null);
  // Mirrors `dayLog` but updated synchronously (not via React's batched
  // setState) so that two dispatch() calls awaited back-to-back in the
  // same handler -- e.g. LUNCH_IN then RESUME_JOB from the "back from
  // lunch, resume the job" choice below -- each see the other's result
  // instead of both operating on the same stale pre-first-call state.
  const dayLogRef = useRef(null);
  const [pauseModalOpen, setPauseModalOpen] = useState(false);
  const [lunchReturnOpen, setLunchReturnOpen] = useState(false);
  const [completing, setCompleting] = useState(false);
  const [completeError, setCompleteError] = useState(null);
  const [sendReportOpen, setSendReportOpen] = useState(false);
  // Which native-confirm replacement is open, if any: 'complete' | 'reopen' | null.
  // Was window.confirm() for both — replaced so these two match the rest of
  // the app's modal pattern and are reachable by automated testing tools,
  // which can't interact with native browser-chrome dialogs.
  const [confirmOpen, setConfirmOpen] = useState(null);

  useEffect(() => {
    (async () => {
      const existing = await loadDayLog(todayISO());
      const initial = existing || createDayLog(employee, todayISO());
      dayLogRef.current = initial;
      setDayLog(initial);
    })();
  }, [employee]);

  const persist = useCallback(async (log) => {
    dayLogRef.current = log;
    setDayLog(log);
    await saveDayLog(log);
    onChanged?.(log);
  }, [onChanged]);

  const dispatch = useCallback(async (type, extra = {}) => {
    const current = dayLogRef.current;
    if (!current) return;
    const now = new Date();
    const { dayLog: next, result } = applyAction(current, { type, at: now.toISOString(), jobRef, ...extra });
    await persist(next);
    if (result.ok) {
      const payload = {
        action_type: type,
        // Local wall-clock time, NOT UTC — see toLocalDatetimeString for
        // why. This is what becomes the segment's stored start_time/
        // end_time in Frappe.
        at: toLocalDatetimeString(now),
        job_ref: jobRef,
        employee,
        log_date: todayISO(),
      };

      if (type === ACTIONS.CORRECT_ARRIVAL) {
        // Previously this action was never synced at all — a flagged
        // segment could only be resolved by someone editing the record
        // directly in Desk. Distinct field names from the payload
        // above, since these describe a manually-entered correction,
        // not a normal action's own timestamp/job.
        payload.corrected_arrival_at = extra.correctedArrivalAt;
        payload.correction_reason = extra.correctionReason;
        payload.correction_job_ref = extra.correctionJobRef || null;
      } else {
        Object.assign(payload, extra);
      }

      // RESUME_JOB/LUNCH_IN close out a break — compute its exact duration
      // here (the device has precise start/end) so the server doesn't
      // have to reconstruct timing from two separate PAUSE/RESUME calls.
      if (type === ACTIONS.RESUME_JOB || type === ACTIONS.LUNCH_IN) {
        const openSeg = next.segments[next.segments.length - 1];
        const list = type === ACTIONS.RESUME_JOB ? (openSeg.pauses || []) : openSeg.lunchBreaks;
        const last = list[list.length - 1];
        if (last?.end) {
          payload.duration_minutes = Math.round((new Date(last.end) - new Date(last.start)) / 60000);
        }
      }

      // ARRIVE from a paused job closes out that job's dangling pause
      // (and lunch break, if concurrent) as a side effect — see the
      // ARRIVE case in timeTrackingMachine.js. Forward those durations
      // so the server applies them to the segment being closed rather
      // than losing them (no separate RESUME_JOB/LUNCH_IN call precedes
      // this one to carry them).
      if (type === ACTIONS.ARRIVE) {
        if (result.closedPauseMinutes != null) payload.pause_duration_minutes = result.closedPauseMinutes;
        if (result.closedLunchMinutes != null) payload.lunch_duration_minutes = result.closedLunchMinutes;
      }

      await enqueueMutation({ type: 'TIME_ACTION', payload });
    }
    return result;
  }, [jobRef, persist, employee]);

  if (!dayLog) return null;

  const ctx = currentContext(dayLog);
  const summary = summarizeDay(dayLog);

  const bannerClass = ctx.pendingCorrection
    ? 'not-started'
    : ctx.dayState === DAY_STATES.ENDED
      ? 'ended'
      : ctx.onJobPause
        ? 'paused'
        : ctx.onLunch
          ? 'lunch'
          : (ctx.openSegmentType || 'not-started').toLowerCase();

  const bannerLabel = ctx.pendingCorrection
    ? 'Correction needed'
    : ctx.dayState === DAY_STATES.NOT_STARTED
      ? 'Not clocked in'
      : ctx.dayState === DAY_STATES.ENDED
        ? 'Day ended'
        : ctx.onJobPause
          ? `Paused — ${ctx.currentPauseReason}`
          : ctx.onLunch
            ? 'On lunch'
            : BANNER_LABEL[ctx.openSegmentType] || '—';

  const handleCorrection = async (correctedArrivalAt) => {
    const corr = dayLog.pendingCorrection;
    await dispatch(ACTIONS.CORRECT_ARRIVAL, {
      correctedArrivalAt,
      correctionReason: corr?.reason,
      correctionJobRef: corr?.requestedJobRef || null,
    });
  };

  const handleMarkComplete = async () => {
    setConfirmOpen(null);
    setCompleting(true);
    setCompleteError(null);
    try {
      if (ctx.activeJobRef === jobRef) {
        // Still clocked in here — close out the onsite segment first so
        // the office doesn't see a job marked Completed while the
        // technician's own time log shows them still on site.
        const leaveResult = await dispatch(ACTIONS.LEAVE);
        if (!leaveResult?.ok) {
          throw new Error(leaveResult?.message || 'Could not clock out before completing.');
        }
      }
      await api.completeAppointment(jobRef);
      setSendReportOpen(true); // ask about emailing the Service Report before navigating away
    } catch (err) {
      setCompleteError(extractErrorMessage(err, 'Could not mark this job complete — try again.'));
    } finally {
      setCompleting(false);
    }
  };

  // Tapping "Clock In from Lunch" while the job is ALSO still job-paused
  // is ambiguous (see ReturnFromLunchModal) -- ask instead of guessing.
  // Otherwise (plain lunch, no job pause) just end lunch directly, same
  // as before.
  const handleLunchIn = () => {
    if (ctx.onJobPause) {
      setLunchReturnOpen(true);
    } else {
      dispatch(ACTIONS.LUNCH_IN);
    }
  };

  const handleLunchInStillPaused = async () => {
    setLunchReturnOpen(false);
    await dispatch(ACTIONS.LUNCH_IN);
  };

  const handleLunchInThenResume = async () => {
    setLunchReturnOpen(false);
    const lunchResult = await dispatch(ACTIONS.LUNCH_IN);
    if (lunchResult?.ok) {
      await dispatch(ACTIONS.RESUME_JOB);
    }
  };

  const atThisJob = jobRef && ctx.activeJobRef === jobRef;
  const openElsewhere = ctx.openSegmentType === SEGMENT_TYPES.ONSITE && ctx.activeJobRef && ctx.activeJobRef !== jobRef;

  return (
    <div>
      <div className={`tracker-banner ${bannerClass}`}>
        <div className="state-label">Time status</div>
        <div className="state-value">{bannerLabel}</div>
        {ctx.dayState !== DAY_STATES.NOT_STARTED && (
          <div style={{ fontSize: 12, opacity: 0.85, marginTop: 4 }}>
            {Math.round(summary.paid / 60 * 10) / 10}h paid so far
            {summary.flagged > 0 ? ` · ${summary.flagged} flagged for review` : ''}
          </div>
        )}
      </div>

      {jobRef ? (
        // --- Job Detail context: Arrive / Leave tied to this appointment ---
        <div className="action-row">
          {!atThisJob && (
            <button
              className="btn btn-primary btn-full"
              disabled={ctx.dayState === DAY_STATES.NOT_STARTED || ctx.dayState === DAY_STATES.ENDED}
              onClick={() => dispatch(ACTIONS.ARRIVE)}
            >
              Clock In (Arrive at Job)
            </button>
          )}
          {atThisJob && !ctx.onJobPause && (
            <button className="btn btn-danger btn-full" onClick={() => dispatch(ACTIONS.LEAVE)}>
              Clock Out
            </button>
          )}
          {atThisJob && !ctx.onLunch && (
            <button className="btn btn-outline btn-full" onClick={() => dispatch(ACTIONS.LUNCH_OUT)}>
              Clock Out for Lunch
            </button>
          )}
          {atThisJob && ctx.onLunch && (
            <button className="btn btn-gold btn-full" onClick={() => handleLunchIn()}>
              Clock In from Lunch
            </button>
          )}
          {atThisJob && !ctx.onLunch && !ctx.onJobPause && (
            <button className="btn btn-outline btn-full" onClick={() => setPauseModalOpen(true)}>
              Pause Job
            </button>
          )}
          {atThisJob && ctx.onJobPause && (
            <button className="btn btn-gold btn-full" onClick={() => dispatch(ACTIONS.RESUME_JOB)}>
              Resume Job
            </button>
          )}
          {!ctx.onJobPause && !ctx.onLunch && (
            <button className="btn btn-primary btn-full" onClick={() => setConfirmOpen('complete')} disabled={completing}>
              {completing ? 'Completing…' : 'Mark Complete'}
            </button>
          )}
          {completeError && (
            <p style={{ fontSize: 12.5, color: 'var(--lcs-crimson)' }}>{completeError}</p>
          )}
          {openElsewhere && !ctx.onJobPause && (
            <p style={{ fontSize: 12.5, color: 'var(--lcs-crimson)' }}>
              You're still clocked in elsewhere. Clock out there before arriving here.
            </p>
          )}
        </div>
      ) : (
        // --- Global context: Start/End of day, Shop clock in/out ---
        <div className="action-row">
          {ctx.dayState === DAY_STATES.NOT_STARTED && capacity === 'light' && (
            <button className="btn btn-primary btn-full" onClick={() => dispatch(ACTIONS.CLOCK_IN_LIGHT)}>
              Clock In — Start of Day
            </button>
          )}
          {ctx.dayState === DAY_STATES.NOT_STARTED && capacity === 'heavy' && (
            <button className="btn btn-primary btn-full" onClick={() => dispatch(ACTIONS.START_INSPECTION)}>
              Start Truck Inspection
            </button>
          )}
          {ctx.openSegmentType === SEGMENT_TYPES.PREP && (
            <button className="btn btn-gold btn-full" onClick={() => dispatch(ACTIONS.SUBMIT_INSPECTION)}>
              Submit Truck Inspection
            </button>
          )}
          {capacity === 'heavy' && ctx.dayState === DAY_STATES.ACTIVE && ctx.openSegmentType !== SEGMENT_TYPES.PREP && (
            <button className="btn btn-outline btn-full" onClick={() => dispatch(ACTIONS.START_INSPECTION)}>
              Log Truck Inspection
            </button>
          )}
          {ctx.openSegmentType === SEGMENT_TYPES.TRAVEL && !ctx.onLunch && (
            <button className="btn btn-primary btn-full" onClick={() => dispatch(ACTIONS.ARRIVE)}>
              Clock In at Shop
            </button>
          )}
          {ctx.openSegmentType === SEGMENT_TYPES.SHOP && !ctx.onLunch && (
            <button className="btn btn-danger btn-full" onClick={() => dispatch(ACTIONS.LEAVE)}>
              Clock Out of Shop
            </button>
          )}
          {(ctx.openSegmentType === SEGMENT_TYPES.TRAVEL || ctx.openSegmentType === SEGMENT_TYPES.SHOP) && !ctx.onLunch && (
            <button className="btn btn-outline btn-full" onClick={() => dispatch(ACTIONS.LUNCH_OUT)}>
              Clock Out for Lunch
            </button>
          )}
          {ctx.onLunch && (
            <button className="btn btn-gold btn-full" onClick={() => handleLunchIn()}>
              Clock In from Lunch
            </button>
          )}
          {(ctx.openSegmentType === SEGMENT_TYPES.TRAVEL || ctx.openSegmentType === SEGMENT_TYPES.SHOP) &&
            !ctx.onLunch && ctx.dayState === DAY_STATES.ACTIVE && (
            <button className="btn btn-outline btn-full" onClick={() => dispatch(ACTIONS.END_DAY)}>
              End of Day
            </button>
          )}
          {ctx.dayState === DAY_STATES.ENDED && (
            <button
              className="btn btn-outline btn-full"
              onClick={() => setConfirmOpen('reopen')}
            >
              Reopen Day
            </button>
          )}
        </div>
      )}

      <ClockCorrectionModal
        pendingCorrection={ctx.pendingCorrection}
        onSubmit={handleCorrection}
        onCancel={async () => {
          // Dismiss without resolving — the technician can reopen it by
          // repeating the same Arrive/Leave tap. Nothing is written yet,
          // so it's safe to just clear the local flag.
          const next = structuredClone(dayLog);
          next.pendingCorrection = null;
          await persist(next);
        }}
      />

      <PauseJobModal
        open={pauseModalOpen}
        onConfirm={async (reason) => {
          setPauseModalOpen(false);
          await dispatch(ACTIONS.PAUSE_JOB, { reason });
        }}
        onCancel={() => setPauseModalOpen(false)}
      />

      <ReturnFromLunchModal
        open={lunchReturnOpen}
        pauseReason={ctx.currentPauseReason}
        onResumeJob={handleLunchInThenResume}
        onStillPaused={handleLunchInStillPaused}
        onCancel={() => setLunchReturnOpen(false)}
      />

      <SendReportModal
        open={sendReportOpen}
        appointmentName={jobRef}
        onDone={() => {
          setSendReportOpen(false);
          onJobCompleted?.();
        }}
      />

      <ConfirmModal
        open={confirmOpen === 'complete'}
        title="Mark this job complete?"
        body="It will be removed from your job list."
        confirmLabel="Mark Complete"
        onConfirm={handleMarkComplete}
        onCancel={() => setConfirmOpen(null)}
      />

      <ConfirmModal
        open={confirmOpen === 'reopen'}
        title="Reopen today?"
        body="Use this if End of Day was tapped by mistake."
        confirmLabel="Reopen Day"
        onConfirm={() => {
          setConfirmOpen(null);
          dispatch(ACTIONS.REOPEN_DAY);
        }}
        onCancel={() => setConfirmOpen(null)}
      />
    </div>
  );
}
