import React, { useEffect, useRef, useState, useCallback } from 'react';
import { addPhoto, getPhotosForAppointment } from '../db/offlineStore.js';

const MAX_PHOTOS = 10; // matches "Service Report Form — photo capture (up to 10)" in the roadmap

export default function PhotoUpload({ appointmentName }) {
  const [photos, setPhotos] = useState([]);
  const [objectUrls, setObjectUrls] = useState({});
  const fileInputRef = useRef(null);

  const refresh = useCallback(async () => {
    const list = await getPhotosForAppointment(appointmentName);
    setPhotos(list);
  }, [appointmentName]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Build/revoke object URLs for locally-stored blobs so <img> can render them.
  useEffect(() => {
    const urls = {};
    for (const p of photos) {
      urls[p.localId] = p.remoteFileUrl || URL.createObjectURL(p.blob);
    }
    setObjectUrls(urls);
    return () => {
      Object.values(urls).forEach((u) => {
        if (u.startsWith('blob:')) URL.revokeObjectURL(u);
      });
    };
  }, [photos]);

  const handleFiles = async (fileList) => {
    const remaining = MAX_PHOTOS - photos.length;
    const files = Array.from(fileList).slice(0, Math.max(0, remaining));
    for (const file of files) {
      await addPhoto(appointmentName, file, { caption: '' });
    }
    await refresh();
  };

  return (
    <div className="card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span className="notes-label" style={{ marginBottom: 0 }}>Job Photos</span>
        <span style={{ fontSize: 12, color: 'var(--lcs-text-muted)' }}>{photos.length}/{MAX_PHOTOS}</span>
      </div>

      <div className="photo-grid">
        {photos.map((p) => (
          <div className="photo-thumb" key={p.localId}>
            <img src={objectUrls[p.localId]} alt="Job site" />
            {!p.synced && <span className="pending-badge">SYNCING</span>}
          </div>
        ))}

        {photos.length < MAX_PHOTOS && (
          <button
            type="button"
            className="photo-add-tile"
            onClick={() => fileInputRef.current?.click()}
            aria-label="Add photo"
          >
            +
          </button>
        )}
      </div>

      {/* capture="environment" opens the rear camera directly on mobile;
          it still falls back to the normal file/gallery picker on desktop. */}
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        capture="environment"
        multiple
        style={{ display: 'none' }}
        onChange={(e) => {
          if (e.target.files?.length) handleFiles(e.target.files);
          e.target.value = '';
        }}
      />

      <p style={{ fontSize: 11.5, color: 'var(--lcs-text-muted)', marginTop: 10, marginBottom: 0 }}>
        Photos are saved on this device immediately and upload automatically once you're back online.
      </p>
    </div>
  );
}
