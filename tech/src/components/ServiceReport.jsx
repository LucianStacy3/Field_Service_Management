import React, { useEffect, useState, useCallback } from 'react';
import * as api from '../api/client.js';
import { extractErrorMessage } from '../api/client.js';

const RESPONSES = ['Pass', 'Fail', 'N/A'];

const RESPONSE_COLOR = {
  Pass: 'var(--lcs-success)',
  Fail: 'var(--lcs-crimson)',
  'N/A': 'var(--lcs-text-muted)',
};

/**
 * The Tech PWA's digital checklist screen — this is what folds the earlier
 * standalone CSR/Service Report concept into the PWA, scoped to Service
 * Appointment instead of Service Order. Checklist items are pre-populated
 * server-side from the LCS Service Report Checklist Template matching this
 * job's Service Type, if a template exists for it (see service_report.py).
 *
 * Deliberately online-only for now: unlike NotesEditor/PhotoUpload, this
 * doesn't queue into the offline mutation outbox. A Service Report is a
 * submit-once audit record, and building full offline support for a new
 * entity type (queueing, conflict handling on reconnect) is a larger,
 * separate piece of work — flagged, not silently skipped.
 */
export default function ServiceReport({ appointmentName }) {
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getServiceReport(appointmentName);
      setReport(res.message);
    } catch (err) {
      setError(
        !navigator.onLine
          ? 'Service Report needs a connection — try again once you\u2019re back online.'
          : extractErrorMessage(err, 'Could not load the Service Report — try again.')
      );
    } finally {
      setLoading(false);
    }
  }, [appointmentName]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) return <p style={{ color: 'var(--lcs-text-muted)' }}>Loading service report…</p>;
  if (error) {
    return (
      <div className="card" style={{ borderColor: 'var(--lcs-gold)' }}>
        <p style={{ margin: 0, fontSize: 13.5 }}>{error}</p>
        <button className="btn btn-outline btn-full" style={{ marginTop: 10 }} onClick={load}>
          Retry
        </button>
      </div>
    );
  }
  if (!report) return null;

  const submitted = report.docstatus === 1;

  const setItemField = (index, field, value) => {
    setReport((prev) => {
      const checklist = prev.checklist.map((row, i) => (i === index ? { ...row, [field]: value } : row));
      return { ...prev, checklist };
    });
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await api.saveServiceReport({
        appointmentName,
        checklist: report.checklist,
        technicianNotes: report.technician_notes,
      });
      setReport(res.message);
    } catch (err) {
      setError(extractErrorMessage(err, 'Could not save — try again.'));
    } finally {
      setSaving(false);
    }
  };

  const handleSubmit = async () => {
    const incomplete = report.checklist.some((row) => !row.response);
    if (incomplete) {
      window.alert('Every checklist item needs a response before you can submit.');
      return;
    }
    if (!window.confirm('Submit this Service Report? It can\u2019t be edited after submitting.')) return;

    setSaving(true);
    try {
      const res = await api.submitServiceReport({
        appointmentName,
        checklist: report.checklist,
        technicianNotes: report.technician_notes,
      });
      setReport(res.message);
    } catch (err) {
      setError(extractErrorMessage(err, 'Could not submit — try again.'));
    } finally {
      setSaving(false);
    }
  };

  if (report.checklist.length === 0) {
    return (
      <div className="card">
        <p style={{ margin: 0, fontSize: 13.5, color: 'var(--lcs-text-muted)' }}>
          No checklist template is set up for this job's service type yet — nothing to fill out here.
        </p>
      </div>
    );
  }

  return (
    <div className="card">
      {submitted && (
        <p style={{ fontSize: 11.5, fontWeight: 700, color: 'var(--lcs-success)', margin: '0 0 10px' }}>
          Submitted {report.submitted_at ? new Date(report.submitted_at).toLocaleString() : ''} — read-only
        </p>
      )}

      {report.checklist.map((row, i) => (
        <div
          key={row.checklist_item + i}
          style={{
            padding: '10px 0',
            borderBottom: i < report.checklist.length - 1 ? '1px solid var(--lcs-border)' : 'none',
          }}
        >
          <div style={{ fontSize: 14, marginBottom: 8 }}>{row.checklist_item}</div>
          <div style={{ display: 'flex', gap: 6, marginBottom: submitted ? 0 : 6 }}>
            {RESPONSES.map((option) => {
              const active = row.response === option;
              return (
                <button
                  key={option}
                  type="button"
                  disabled={submitted}
                  onClick={() => setItemField(i, 'response', option)}
                  style={{
                    flex: 1,
                    minHeight: 36,
                    borderRadius: 8,
                    border: `1.5px solid ${RESPONSE_COLOR[option]}`,
                    background: active ? RESPONSE_COLOR[option] : 'transparent',
                    color: active ? 'var(--lcs-surface)' : RESPONSE_COLOR[option],
                    fontWeight: 700,
                    fontSize: 13,
                    opacity: submitted && !active ? 0.4 : 1,
                  }}
                >
                  {option}
                </button>
              );
            })}
          </div>
          {!submitted && (
            <input
              type="text"
              placeholder="Note for this item (optional)"
              value={row.notes || ''}
              onChange={(e) => setItemField(i, 'notes', e.target.value)}
              style={{
                width: '100%',
                marginTop: 8,
                padding: '8px 10px',
                fontSize: 13,
                borderRadius: 8,
                border: '1px solid var(--lcs-border)',
                background: 'var(--lcs-bg)',
                color: 'var(--lcs-text)',
                boxSizing: 'border-box',
              }}
            />
          )}
          {submitted && row.notes && (
            <p style={{ fontSize: 12.5, color: 'var(--lcs-text-muted)', marginTop: 6, marginBottom: 0 }}>{row.notes}</p>
          )}
        </div>
      ))}

      <div className="notes-label" style={{ marginTop: 14 }}>
        Technician Notes
      </div>
      {submitted ? (
        <p style={{ fontSize: 13.5, whiteSpace: 'pre-wrap', margin: 0 }}>{report.technician_notes || '—'}</p>
      ) : (
        <textarea
          className="notes-field"
          placeholder="Overall summary of the visit for this Service Report…"
          value={report.technician_notes || ''}
          onChange={(e) => setReport((prev) => ({ ...prev, technician_notes: e.target.value }))}
        />
      )}

      {!submitted && (
        <div className="action-row two-col" style={{ marginTop: 12 }}>
          <button className="btn btn-outline btn-full" onClick={handleSave} disabled={saving}>
            {saving ? 'Saving…' : 'Save Draft'}
          </button>
          <button className="btn btn-primary btn-full" onClick={handleSubmit} disabled={saving}>
            Submit Report
          </button>
        </div>
      )}
    </div>
  );
}
