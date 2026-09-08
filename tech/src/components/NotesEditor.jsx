import React, { useEffect, useState, useRef } from 'react';
import { getNoteDraft, saveNoteDraft } from '../db/offlineStore.js';

const SAVE_DEBOUNCE_MS = 800;

/**
 * Two distinct note fields per job:
 *  - Customer notes: appear on the service report / can be shared with the customer.
 *  - Internal notes: office/dispatch only, never printed on customer-facing documents.
 *
 * Saves are debounced and queued offline via saveNoteDraft, which pushes
 * an UPDATE_NOTES mutation into the outbox for sync.js to send.
 */
export default function NotesEditor({ appointmentName, initialCustomerNotes = '', initialInternalNotes = '' }) {
  const [customerNotes, setCustomerNotes] = useState(initialCustomerNotes);
  const [internalNotes, setInternalNotes] = useState(initialInternalNotes);
  const [savedAt, setSavedAt] = useState(null);
  const timer = useRef(null);

  useEffect(() => {
    (async () => {
      const draft = await getNoteDraft(appointmentName);
      if (draft) {
        setCustomerNotes(draft.customerNotes ?? initialCustomerNotes);
        setInternalNotes(draft.internalNotes ?? initialInternalNotes);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [appointmentName]);

  const scheduleSave = (next) => {
    clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      const record = await saveNoteDraft(appointmentName, next);
      setSavedAt(record.updatedAt);
    }, SAVE_DEBOUNCE_MS);
  };

  return (
    <div className="card">
      <div className="notes-label">
        Customer Notes <span className="tag customer-visible">Visible on service report</span>
      </div>
      <textarea
        className="notes-field"
        placeholder="What did you do? What should the customer know — findings, recommendations, follow-up needed…"
        value={customerNotes}
        onChange={(e) => {
          setCustomerNotes(e.target.value);
          scheduleSave({ customerNotes: e.target.value, internalNotes });
        }}
      />

      <div className="notes-label" style={{ marginTop: 16 }}>
        Internal Notes <span className="tag internal-only">Office only — never printed</span>
      </div>
      <textarea
        className="notes-field internal"
        placeholder="Anything dispatch or the office should know — access issues, parts to order, billing flags, safety concerns…"
        value={internalNotes}
        onChange={(e) => {
          setInternalNotes(e.target.value);
          scheduleSave({ customerNotes, internalNotes: e.target.value });
        }}
      />

      <p style={{ fontSize: 11.5, color: 'var(--lcs-text-muted)', marginTop: 8, marginBottom: 0 }}>
        {savedAt ? `Saved locally ${new Date(savedAt).toLocaleTimeString()} — syncs automatically` : 'Autosaves as you type'}
      </p>
    </div>
  );
}
