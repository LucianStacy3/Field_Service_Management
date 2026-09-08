import React, { useEffect, useState } from 'react';
import * as api from '../api/client.js';
import { extractErrorMessage } from '../api/client.js';

const METHODS = ['Cash', 'Check', 'Card'];

/**
 * Collect Payment — Phase 5 (Section 8.4). Online-only, same scope
 * limitation as Add Part and Service Report (no offline queue yet): a
 * Payment Entry is a real accounting record, not something safe to queue
 * and replay blind once a signal comes back. Stays hidden/disabled until
 * the server confirms there's a submitted invoice with a balance due —
 * never lets a tech attempt a payment against a draft invoice.
 */
export default function CollectPayment({ appointmentName }) {
  const [info, setInfo] = useState(null); // { can_collect, status, invoice, outstanding_amount, currency, methods }
  const [loading, setLoading] = useState(true);
  const [amount, setAmount] = useState('');
  const [method, setMethod] = useState('Cash');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null); // { payment_entry, amount_paid, outstanding_amount, receipt_emailed_to }

  useEffect(() => {
    (async () => {
      try {
        const res = await api.getPaymentInfo(appointmentName);
        setInfo(res.message);
        if (res.message?.outstanding_amount) {
          setAmount(String(res.message.outstanding_amount));
        }
      } catch (err) {
        setError(extractErrorMessage(err, 'Could not check invoice status.'));
      } finally {
        setLoading(false);
      }
    })();
  }, [appointmentName]);

  const handleCollect = async () => {
    const numericAmount = parseFloat(amount);
    if (!numericAmount || numericAmount <= 0) {
      setError('Enter an amount greater than zero.');
      return;
    }
    if (info?.outstanding_amount && numericAmount > info.outstanding_amount + 0.005) {
      setError(`That's more than the outstanding balance of ${formatMoney(info.outstanding_amount, info.currency)}.`);
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const res = await api.collectPayment({ appointmentName, amount: numericAmount, method });
      setResult(res.message);
    } catch (err) {
      setError(
        !navigator.onLine
          ? "Collecting payment needs a connection — try again once you're back online."
          : extractErrorMessage(err, 'Could not record that payment — try again.')
      );
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) return <div className="card"><p style={{ color: 'var(--lcs-text-muted)', margin: 0 }}>Checking invoice status…</p></div>;

  if (result) {
    return (
      <div className="card" style={{ borderColor: 'var(--lcs-success)', background: 'var(--lcs-success-tint)' }}>
        <div style={{ fontWeight: 700, color: 'var(--lcs-success)', marginBottom: 6 }}>Payment recorded</div>
        <div style={{ fontSize: 13.5, marginBottom: 4 }}>
          {formatMoney(result.amount_paid, info?.currency)} — {method}
        </div>
        <div style={{ fontSize: 12.5, color: 'var(--lcs-text-muted)' }}>
          {result.outstanding_amount > 0
            ? `Remaining balance: ${formatMoney(result.outstanding_amount, info?.currency)}`
            : 'Invoice paid in full.'}
        </div>
        <div style={{ fontSize: 12.5, color: 'var(--lcs-text-muted)', marginTop: 4 }}>
          {result.receipt_emailed_to
            ? `Receipt emailed to ${result.receipt_emailed_to}.`
            : 'No customer email on file — receipt not sent.'}
        </div>
      </div>
    );
  }

  if (!info?.can_collect) {
    const message =
      info?.status === 'paid_in_full'
        ? 'This job is already paid in full.'
        : "Not invoiced yet — Collect Payment opens once the office creates the invoice.";
    return (
      <div className="card">
        <p style={{ color: 'var(--lcs-text-muted)', fontSize: 13.5, margin: 0 }}>{message}</p>
      </div>
    );
  }

  return (
    <div className="card">
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13.5, marginBottom: 12 }}>
        <span style={{ color: 'var(--lcs-text-muted)' }}>Balance due</span>
        <strong>{formatMoney(info.outstanding_amount, info.currency)}</strong>
      </div>

      {error && <p style={{ fontSize: 12.5, color: 'var(--lcs-crimson)', marginTop: 0 }}>{error}</p>}

      <label style={{ fontSize: 12, color: 'var(--lcs-text-muted)', display: 'block', marginBottom: 4 }}>Amount</label>
      <input
        type="number"
        min="0.01"
        step="0.01"
        value={amount}
        onChange={(e) => setAmount(e.target.value)}
        disabled={submitting}
        style={{
          width: '100%',
          minHeight: 40,
          padding: '8px 10px',
          fontSize: 15,
          borderRadius: 8,
          border: '1px solid var(--lcs-border)',
          background: 'var(--lcs-bg)',
          color: 'var(--lcs-text)',
          boxSizing: 'border-box',
          marginBottom: 12,
        }}
      />

      <label style={{ fontSize: 12, color: 'var(--lcs-text-muted)', display: 'block', marginBottom: 4 }}>Method</label>
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        {METHODS.map((m) => (
          <button
            key={m}
            type="button"
            disabled={submitting}
            onClick={() => setMethod(m)}
            className={method === m ? 'btn btn-primary' : 'btn btn-outline'}
            style={{ flex: 1, minHeight: 40, fontSize: 13.5 }}
          >
            {m}
          </button>
        ))}
      </div>

      <button className="btn btn-primary btn-full" style={{ minHeight: 44 }} onClick={handleCollect} disabled={submitting}>
        {submitting ? 'Recording…' : `Collect ${formatMoney(parseFloat(amount) || 0, info.currency)}`}
      </button>
    </div>
  );
}

function formatMoney(value, currency) {
  const n = Number(value) || 0;
  try {
    return n.toLocaleString(undefined, { style: 'currency', currency: currency || 'USD' });
  } catch {
    return `$${n.toFixed(2)}`;
  }
}
