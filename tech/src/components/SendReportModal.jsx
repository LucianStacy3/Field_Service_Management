import React, { useEffect, useState } from 'react';
import * as api from '../api/client.js';
import { extractErrorMessage } from '../api/client.js';

/**
 * Shown right after a job is marked complete. Checks whether there's a
 * Service Report worth sending and whether a client email is already on
 * file (Service Order's customer_contact). If there's no Service Report
 * at all, this skips straight through via onDone — nothing to send.
 */
export default function SendReportModal({ open, appointmentName, onDone }) {
  const [loading, setLoading] = useState(true);
  const [info, setInfo] = useState(null);
  const [manualEmails, setManualEmails] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(null);
  const [sent, setSent] = useState(false);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const res = await api.getCompletionEmailInfo(appointmentName);
        if (cancelled) return;
        if (!res.message.has_service_report) {
          onDone(); // nothing to send — skip the prompt entirely
          return;
        }
        setInfo(res.message);
      } catch {
        if (!cancelled) onDone(); // don't block completion over this check failing
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, appointmentName]);

  if (!open || loading || !info) return null;

  const emailsToSend = info.email
    ? [info.email]
    : manualEmails.split(',').map((e) => e.trim()).filter(Boolean);

  const handleSend = async () => {
    setSending(true);
    setError(null);
    try {
      await api.sendServiceReportPdf({ appointmentName, emails: emailsToSend });
      setSent(true);
      setTimeout(onDone, 1200);
    } catch (err) {
      setError(extractErrorMessage(err, 'Could not send the report — try again.'));
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <div className="modal-sheet">
        {sent ? (
          <>
            <p className="modal-title">Sent</p>
            <p className="modal-body">Service Report emailed to {emailsToSend.join(', ')}.</p>
          </>
        ) : (
          <>
            <p className="modal-title">Send Service Report to client?</p>
            {info.email ? (
              <p className="modal-body">Send a copy of the Service Report to {info.email}?</p>
            ) : (
              <>
                <p className="modal-body">
                  No email is on file for this customer. Enter an email address (or a
                  comma-separated list) to send the Service Report to:
                </p>
                <input
                  type="email"
                  multiple
                  placeholder="customer@example.com"
                  value={manualEmails}
                  onChange={(e) => setManualEmails(e.target.value)}
                  style={{
                    width: '100%',
                    minHeight: 44,
                    padding: '8px 10px',
                    fontSize: 14,
                    borderRadius: 8,
                    border: '1px solid var(--lcs-border)',
                    background: 'var(--lcs-bg)',
                    color: 'var(--lcs-text)',
                    boxSizing: 'border-box',
                    marginBottom: 10,
                  }}
                />
              </>
            )}

            {error && <p style={{ fontSize: 12.5, color: 'var(--lcs-crimson)' }}>{error}</p>}

            <div className="action-row two-col" style={{ marginTop: 12 }}>
              <button className="btn btn-outline" onClick={onDone} disabled={sending}>
                Skip
              </button>
              <button
                className="btn btn-primary"
                onClick={handleSend}
                disabled={sending || emailsToSend.length === 0}
              >
                {sending ? 'Sending…' : 'Send'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
