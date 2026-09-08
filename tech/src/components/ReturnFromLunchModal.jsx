import React from 'react';

/**
 * Shown when returning from lunch (LUNCH_IN) while the job is ALSO still
 * job-paused for another reason (parts, customer, etc.) -- lunch and a
 * job pause can now both be open on the same segment at once (see
 * LUNCH_OUT in timeTrackingMachine.js), so ending lunch alone is
 * ambiguous in that state: is the technician back to actively working
 * the job, or just back from lunch and still waiting on whatever paused
 * it? Asks explicitly rather than guessing either way.
 */
export default function ReturnFromLunchModal({ open, pauseReason, onResumeJob, onStillPaused, onCancel }) {
  if (!open) return null;

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <div className="modal-sheet">
        <p className="modal-title">Back from lunch</p>
        <p className="modal-body">
          This job is still marked paused{pauseReason ? ` (${pauseReason})` : ''}. Are you resuming
          the job now, or is it still on pause?
        </p>

        <div className="action-row two-col" style={{ marginTop: 12 }}>
          <button className="btn btn-outline" onClick={onStillPaused}>Still Paused</button>
          <button className="btn btn-primary" onClick={onResumeJob}>Resume Job</button>
        </div>
        <button className="btn btn-outline btn-full" style={{ marginTop: 8 }} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  );
}
