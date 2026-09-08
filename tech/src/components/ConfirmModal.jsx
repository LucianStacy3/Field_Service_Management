import React from 'react';

/**
 * Small reusable yes/no confirmation, styled to match PauseJobModal /
 * ClockCorrectionModal. Exists specifically to replace window.confirm()
 * on Mark Complete and Reopen Day: those two were the only spots in the
 * app using a native browser dialog instead of this app's own modal
 * pattern, which made them behave inconsistently with everything else
 * (no themeing, no way to style the copy) and unreachable by any
 * automated testing tool that can't drive native browser-chrome dialogs.
 */
export default function ConfirmModal({ open, title, body, confirmLabel = 'Confirm', danger = false, onConfirm, onCancel }) {
  if (!open) return null;

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <div className="modal-sheet">
        <p className="modal-title">{title}</p>
        {body && <p className="modal-body">{body}</p>}

        <div className="action-row two-col" style={{ marginTop: 12 }}>
          <button className="btn btn-outline" onClick={onCancel}>Cancel</button>
          <button className={danger ? 'btn btn-danger' : 'btn btn-primary'} onClick={onConfirm}>
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
