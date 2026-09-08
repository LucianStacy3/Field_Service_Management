import React, { useState } from 'react';

const COMMON_REASONS = [
  'Waiting on parts',
  'Waiting on customer',
  'Customer not home',
  'Waiting on approval',
];

/**
 * Collects a mandatory reason before pausing an in-progress job. Unlike
 * lunch (no reason needed, just a break), a job pause always needs one —
 * this is what the office sees when reviewing why a job took longer than
 * the onsite work itself did.
 */
export default function PauseJobModal({ open, onConfirm, onCancel }) {
  const [reason, setReason] = useState('');

  if (!open) return null;

  const trimmed = reason.trim();

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <div className="modal-sheet">
        <p className="modal-title">Pause this job</p>
        <p className="modal-body">A reason is required — this shows up on the job record for the office.</p>

        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 10 }}>
          {COMMON_REASONS.map((r) => (
            <button
              key={r}
              type="button"
              className={reason === r ? 'btn btn-primary' : 'btn btn-outline'}
              style={{ minHeight: 34, padding: '0 10px', fontSize: 12.5 }}
              onClick={() => setReason(r)}
            >
              {r}
            </button>
          ))}
        </div>

        <label style={{ fontSize: 12, fontWeight: 700, display: 'block', marginBottom: 6 }}>
          Reason
        </label>
        <textarea
          className="notes-field"
          style={{ minHeight: 70 }}
          placeholder="Or type your own reason…"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />

        <div className="action-row two-col" style={{ marginTop: 12 }}>
          <button className="btn btn-outline" onClick={onCancel}>Cancel</button>
          <button
            className="btn btn-primary"
            disabled={!trimmed}
            onClick={() => onConfirm(trimmed)}
          >
            Pause Job
          </button>
        </div>
      </div>
    </div>
  );
}
