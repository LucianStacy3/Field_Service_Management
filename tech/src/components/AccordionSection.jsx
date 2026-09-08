import React, { useState } from 'react';

/**
 * Collapsible section wrapper for Job Detail. Job Instructions is
 * deliberately NOT wrapped in one of these — office/dispatch instructions
 * need to be visible before the tech starts anything, not hidden behind a
 * tap. Everything else (Time Tracking, Notes, Photos, Service Report,
 * Parts) collapses to keep the screen scannable now that it's grown.
 */
export default function AccordionSection({ title, defaultOpen = false, badge, children }) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className="accordion-section">
      <button
        type="button"
        className="accordion-header"
        onClick={() => setOpen((prev) => !prev)}
        aria-expanded={open}
      >
        <span>
          {title}
          {badge != null && badge !== '' && <span className="accordion-badge">{badge}</span>}
        </span>
        <span className={`accordion-chevron${open ? ' open' : ''}`}>›</span>
      </button>
      {open && <div className="accordion-body">{children}</div>}
    </div>
  );
}
