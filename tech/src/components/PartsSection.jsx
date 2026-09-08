import React, { useEffect, useState } from 'react';
import * as api from '../api/client.js';
import { extractErrorMessage } from '../api/client.js';

/**
 * Parts on Order. Existing rows come from whatever the office already
 * added to the Service Order/Appointment. The Add Part control lets a
 * technician add something from the field — online-only for now, same
 * scope limitation as Service Report (no offline queue yet).
 */
export default function PartsSection({ appointmentName, initialParts }) {
  const [parts, setParts] = useState(initialParts || []);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [selected, setSelected] = useState(null); // { item_code, item_name, is_service }
  const [qty, setQty] = useState(1);
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    setParts(initialParts || []);
  }, [initialParts]);

  useEffect(() => {
    if (query.trim().length < 2) {
      setResults([]);
      return undefined;
    }
    setSearching(true);
    const handle = setTimeout(async () => {
      try {
        const res = await api.searchItems(query.trim());
        setResults(res.message || []);
        setError(null);
      } catch (err) {
        setResults([]);
        setError(extractErrorMessage(err, 'Search failed — try again.'));
      } finally {
        setSearching(false);
      }
    }, 300); // debounce — avoid a request per keystroke
    return () => clearTimeout(handle);
  }, [query]);

  const pickResult = (item) => {
    setSelected(item);
    setResults([]);
    setQuery('');
    setQty(1);
  };

  const handleAdd = async () => {
    if (!selected) return;
    setAdding(true);
    setError(null);
    try {
      const res = await api.addPartToAppointment({
        appointmentName,
        itemCode: selected.item_code,
        qty,
      });
      setParts(res.message.parts);
      setSelected(null);
      setQty(1);
    } catch (err) {
      setError(
        !navigator.onLine
          ? "Adding parts needs a connection — try again once you're back online."
          : extractErrorMessage(err, 'Could not add that part — try again.')
      );
    } finally {
      setAdding(false);
    }
  };

  return (
    <div className="card">
      {parts.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          {parts.map((p, i) => (
            <div
              key={i}
              style={{
                fontSize: 13.5,
                padding: '6px 0',
                borderBottom: i < parts.length - 1 ? '1px solid var(--lcs-border)' : 'none',
                display: 'flex',
                justifyContent: 'space-between',
              }}
            >
              <span>{p.item_name}</span>
              <span style={{ color: 'var(--lcs-text-muted)' }}>× {p.qty}</span>
            </div>
          ))}
        </div>
      )}

      {error && <p style={{ fontSize: 12.5, color: 'var(--lcs-crimson)', marginTop: 0 }}>{error}</p>}

      {!selected ? (
        <>
          <input
            type="text"
            placeholder="Search parts or services to add…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            style={{
              width: '100%',
              minHeight: 40,
              padding: '8px 10px',
              fontSize: 13.5,
              borderRadius: 8,
              border: '1px solid var(--lcs-border)',
              background: 'var(--lcs-bg)',
              color: 'var(--lcs-text)',
              boxSizing: 'border-box',
            }}
          />
          {searching && <p style={{ fontSize: 12.5, color: 'var(--lcs-text-muted)', margin: '6px 0 0' }}>Searching…</p>}
          {results.map((item) => (
            <button
              key={item.item_code}
              type="button"
              onClick={() => pickResult(item)}
              style={{
                width: '100%',
                textAlign: 'left',
                marginTop: 6,
                padding: '8px 10px',
                fontSize: 13.5,
                borderRadius: 8,
                border: '1px solid var(--lcs-border)',
                background: 'var(--lcs-surface)',
                color: 'var(--lcs-text)',
              }}
            >
              {item.item_name}
              <span style={{ display: 'block', fontSize: 11.5, color: 'var(--lcs-text-muted)' }}>
                {item.item_code} {item.is_service ? '· Service' : ''}
              </span>
            </button>
          ))}
        </>
      ) : (
        <div>
          <div style={{ fontSize: 13.5, marginBottom: 8 }}>
            Adding: <strong>{selected.item_name}</strong>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input
              type="number"
              min="0.01"
              step="1"
              value={qty}
              onChange={(e) => setQty(e.target.value)}
              style={{
                width: 70,
                minHeight: 40,
                padding: '8px 10px',
                fontSize: 13.5,
                borderRadius: 8,
                border: '1px solid var(--lcs-border)',
                background: 'var(--lcs-bg)',
                color: 'var(--lcs-text)',
                boxSizing: 'border-box',
              }}
            />
            <button className="btn btn-outline" style={{ flex: 1, minHeight: 40 }} onClick={() => setSelected(null)} disabled={adding}>
              Cancel
            </button>
            <button className="btn btn-primary" style={{ flex: 1, minHeight: 40 }} onClick={handleAdd} disabled={adding}>
              {adding ? 'Adding…' : 'Add'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
