import React, { useState } from 'react';

/**
 * Surfaces the "Point-of-Action Override" and "Sequential Clock-In Lock"
 * exceptions from the time tracking proposal (Section 1.2). The technician
 * must enter their actual arrival time before they can continue; the
 * record gets flagged for administrative review automatically.
 */
export default function ClockCorrectionModal({ pendingCorrection, onSubmit, onCancel }) {
  const nowLocal = new Date();
  nowLocal.setSeconds(0, 0);
  const [value, setValue] = useState(toLocalInputValue(nowLocal));

  if (!pendingCorrection) return null;

  const handleSubmit = () => {
    // `value` is already the technician's local wall-clock entry (that's
    // what a datetime-local input gives you) — reformat directly rather
    // than round-tripping through new Date(value).toISOString(), which
    // would convert to UTC and reintroduce the same bug fixed in
    // TimeTracker.jsx's dispatch(): the server stores Datetime values
    // naively, so a UTC string gets treated as if it were already local.
    const local = value.length === 16 ? `${value}:00` : value; // add seconds if the input omitted them
    onSubmit(local);
  };

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <div className="modal-sheet">
        <p className="modal-title">Time correction needed</p>
        <p className="modal-body">{pendingCorrection.message}</p>
        <label style={{ fontSize: 12, fontWeight: 700, display: 'block', marginBottom: 6 }}>
          Actual arrival time
        </label>
        <input
          type="datetime-local"
          className="time-input"
          value={value}
          max={toLocalInputValue(new Date())}
          onChange={(e) => setValue(e.target.value)}
        />
        <p style={{ fontSize: 12, color: 'var(--lcs-text-muted)', marginTop: -8, marginBottom: 14 }}>
          This entry will be flagged for administrative review. It won't end the job by itself —
          you'll need to tap the button again once this is corrected.
        </p>
        <div className="action-row two-col">
          <button className="btn btn-outline" onClick={onCancel}>Cancel</button>
          <button className="btn btn-primary" onClick={handleSubmit}>Confirm time</button>
        </div>
      </div>
    </div>
  );
}

function toLocalInputValue(date) {
  const pad = (n) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}
