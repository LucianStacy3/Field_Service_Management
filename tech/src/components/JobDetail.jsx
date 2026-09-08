import React, { useEffect, useState } from 'react';
import * as api from '../api/client.js';
import { getCachedJob } from '../db/offlineStore.js';
import TimeTracker from './TimeTracker.jsx';
import NotesEditor from './NotesEditor.jsx';
import PhotoUpload from './PhotoUpload.jsx';
import ServiceReport from './ServiceReport.jsx';
import PartsSection from './PartsSection.jsx';
import CollectPayment from './CollectPayment.jsx';
import AccordionSection from './AccordionSection.jsx';

export default function JobDetail({ appointmentName, employee, capacity, onBack }) {
  const [job, setJob] = useState(null);

  useEffect(() => {
    (async () => {
      // Try live detail first (parts list, full customer record), fall
      // back to the cached summary from Today's Jobs if offline.
      try {
        if (navigator.onLine) {
          const res = await api.getJobDetail(appointmentName);
          setJob(res.message);
          return;
        }
        throw new Error('offline');
      } catch {
        setJob(await getCachedJob(appointmentName));
      }
    })();
  }, [appointmentName]);

  if (!job) return <p style={{ color: 'var(--lcs-text-muted)' }}>Loading job…</p>;

  const mapsUrl = job.site_address
    ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(job.site_address)}`
    : null;

  return (
    <div>
      <button className="btn btn-outline" style={{ minHeight: 36, padding: '0 12px', fontSize: 13, marginBottom: 12 }} onClick={onBack}>
        ← Today's Jobs
      </button>

      <div className="card">
        <div className="job-status" style={{ marginBottom: 8, display: 'inline-block' }}>{job.status}</div>
        <div className="job-customer" style={{ fontSize: 19 }}>{job.customer_name}</div>
        <div className="job-address">{job.site_address}</div>
        {job.reference_numbers && (
          <div style={{ marginTop: 10, paddingTop: 10, borderTop: '1px solid var(--lcs-border)' }}>
            {[
              ['Service Call #', job.reference_numbers.service_call],
              ['Service Quote #', job.reference_numbers.service_quotation],
              ['Service Order #', job.reference_numbers.service_order],
              ['Service Appointment #', job.reference_numbers.service_appointment],
            ]
              .filter(([, value]) => value)
              .map(([label, value]) => (
                <div key={label} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginTop: 3 }}>
                  <span style={{ color: 'var(--lcs-text-muted)' }}>{label}</span>
                  <span>{value}</span>
                </div>
              ))}
          </div>
        )}
        {mapsUrl && (
          <a href={mapsUrl} target="_blank" rel="noreferrer" className="btn btn-outline btn-full" style={{ marginTop: 10 }}>
            Open in Maps
          </a>
        )}
        {job.equipment_summary && (
          <p style={{ fontSize: 13.5, marginTop: 10, marginBottom: 0 }}>{job.equipment_summary}</p>
        )}
      </div>

      {job.instructions && (
        <div className="card" style={{ borderColor: 'var(--lcs-gold)', background: 'var(--lcs-gold-tint)' }}>
          <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.4px', color: 'var(--lcs-gold)', marginBottom: 6 }}>
            Job Instructions — from office/sales
          </div>
          <p style={{ fontSize: 14, margin: 0, whiteSpace: 'pre-wrap', color: 'var(--lcs-text)' }}>{job.instructions}</p>
        </div>
      )}

      <AccordionSection title="Time Tracking" defaultOpen>
        <TimeTracker employee={employee} jobRef={appointmentName} capacity={capacity} onJobCompleted={onBack} />
      </AccordionSection>

      <AccordionSection title="Job Notes">
        <NotesEditor
          appointmentName={appointmentName}
          initialCustomerNotes={job.customer_notes}
          initialInternalNotes={job.internal_notes}
        />
      </AccordionSection>

      <AccordionSection title="Photos">
        <PhotoUpload appointmentName={appointmentName} />
      </AccordionSection>

      <AccordionSection title="Service Report">
        <ServiceReport appointmentName={appointmentName} />
      </AccordionSection>

      <AccordionSection title="Parts on Order" badge={job.parts?.length || null}>
        <PartsSection appointmentName={appointmentName} initialParts={job.parts} />
      </AccordionSection>

      <AccordionSection title="Collect Payment">
        <CollectPayment appointmentName={appointmentName} />
      </AccordionSection>
    </div>
  );
}
