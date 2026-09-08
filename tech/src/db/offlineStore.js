/**
 * offlineStore.js
 *
 * IndexedDB (via idb) wrapper providing:
 *  - jobs: cached individual job records for the logged-in technician
 *  - jobLists: cached job list per selected period (Day/Week/Month/Quarter)
 *  - dayLog: the current chained-logic time tracking day log
 *  - notes: queued customer/internal note edits per appointment
 *  - photos: queued photo blobs per appointment, pending upload
 *  - mutationQueue: generic outbox for anything that needs to sync
 *
 * Everything here works with zero network connectivity. sync.js drains
 * mutationQueue against the Frappe REST API when the browser comes back online.
 */

import { openDB } from 'idb';

const DB_NAME = 'lcs-tech-pwa';
const DB_VERSION = 2;

export async function getDB() {
  return openDB(DB_NAME, DB_VERSION, {
    upgrade(db, oldVersion) {
      if (!db.objectStoreNames.contains('jobs')) {
        db.createObjectStore('jobs', { keyPath: 'name' }); // Service Appointment name
      }
      if (!db.objectStoreNames.contains('jobLists')) {
        // Caches the exact list returned for a given period selection
        // (Day/Week/Month/Quarter) so switching periods while offline
        // shows the right last-known view instead of whatever period
        // happened to be fetched most recently.
        db.createObjectStore('jobLists', { keyPath: 'periodKey' });
      }
      if (!db.objectStoreNames.contains('dayLog')) {
        db.createObjectStore('dayLog', { keyPath: 'date' }); // one per calendar date
      }
      if (!db.objectStoreNames.contains('notes')) {
        db.createObjectStore('notes', { keyPath: 'appointmentName' });
      }
      if (!db.objectStoreNames.contains('photos')) {
        const store = db.createObjectStore('photos', { keyPath: 'localId', autoIncrement: true });
        store.createIndex('byAppointment', 'appointmentName');
        store.createIndex('bySynced', 'synced');
      }
      if (!db.objectStoreNames.contains('mutationQueue')) {
        const store = db.createObjectStore('mutationQueue', { keyPath: 'id', autoIncrement: true });
        store.createIndex('byCreatedAt', 'createdAt');
      }
    },
  });
}

// ---- Jobs cache -----------------------------------------------------------

/**
 * Caches a fetched job list both individually (for job-detail offline
 * fallback, keyed by appointment name) and as a whole (for the list
 * screen's offline fallback, keyed by the selected period).
 */
export async function cacheJobs(periodKey, jobs) {
  const db = await getDB();
  const tx = db.transaction(['jobs', 'jobLists'], 'readwrite');
  for (const job of jobs) await tx.objectStore('jobs').put(job);
  await tx.objectStore('jobLists').put({ periodKey, jobs, cachedAt: new Date().toISOString() });
  await tx.done;
}

export async function getCachedJobList(periodKey) {
  const db = await getDB();
  const record = await db.get('jobLists', periodKey);
  return record?.jobs || [];
}

export async function getCachedJobs() {
  const db = await getDB();
  return db.getAll('jobs');
}

export async function getCachedJob(name) {
  const db = await getDB();
  return db.get('jobs', name);
}

// ---- Day log ----------------------------------------------------------

export async function saveDayLog(dayLog) {
  const db = await getDB();
  await db.put('dayLog', dayLog);
}

export async function loadDayLog(dateISO) {
  const db = await getDB();
  return db.get('dayLog', dateISO);
}

// ---- Notes --------------------------------------------------------------

export async function saveNoteDraft(appointmentName, { customerNotes, internalNotes }) {
  const db = await getDB();
  const existing = (await db.get('notes', appointmentName)) || { appointmentName };
  const record = {
    ...existing,
    customerNotes: customerNotes ?? existing.customerNotes ?? '',
    internalNotes: internalNotes ?? existing.internalNotes ?? '',
    updatedAt: new Date().toISOString(),
    synced: false,
  };
  await db.put('notes', record);
  await enqueueMutation({
    type: 'UPDATE_NOTES',
    payload: { appointmentName, customerNotes: record.customerNotes, internalNotes: record.internalNotes },
  });
  return record;
}

export async function getNoteDraft(appointmentName) {
  const db = await getDB();
  return db.get('notes', appointmentName);
}

// ---- Photos ---------------------------------------------------------------

/** Stores a photo blob locally and queues it for upload. Returns the local record. */
export async function addPhoto(appointmentName, blob, { caption = '' } = {}) {
  const db = await getDB();
  const record = {
    appointmentName,
    blob,
    caption,
    takenAt: new Date().toISOString(),
    synced: false,
  };
  const localId = await db.add('photos', record);
  await enqueueMutation({ type: 'UPLOAD_PHOTO', payload: { localId } });
  return { ...record, localId };
}

export async function getPhotosForAppointment(appointmentName) {
  const db = await getDB();
  return db.getAllFromIndex('photos', 'byAppointment', appointmentName);
}

export async function markPhotoSynced(localId, remoteFileUrl) {
  const db = await getDB();
  const record = await db.get('photos', localId);
  if (!record) return;
  record.synced = true;
  record.remoteFileUrl = remoteFileUrl;
  await db.put('photos', record);
}

// ---- Generic mutation outbox ------------------------------------------

export async function enqueueMutation(mutation) {
  const db = await getDB();
  await db.add('mutationQueue', { ...mutation, createdAt: new Date().toISOString(), attempts: 0 });

  // Try to flush the outbox right away so an online, foregrounded session
  // doesn't sit on unsynced actions until the next 'online'/visibilitychange
  // event or a full app reload -- previously the *only* triggers for
  // syncNow(), which left same-session, back-to-back actions (e.g. arrive,
  // pause, arrive next job) queued with zero sync attempts for as long as
  // the tab stayed open, online, and foregrounded. Dynamic import avoids a
  // circular dependency (sync.js already imports this module). Must never
  // throw or block the caller's optimistic UI update -- failures just fall
  // back to the existing triggers and the manual sync-pill tap.
  if (typeof navigator !== 'undefined' && navigator.onLine) {
    import('./sync.js').then(({ syncNow }) => syncNow()).catch(() => {});
  }
}

export async function getQueuedMutations() {
  const db = await getDB();
  return db.getAllFromIndex('mutationQueue', 'byCreatedAt');
}

export async function removeMutation(id) {
  const db = await getDB();
  await db.delete('mutationQueue', id);
}

export async function bumpMutationAttempts(id) {
  const db = await getDB();
  const record = await db.get('mutationQueue', id);
  if (!record) return;
  record.attempts += 1;
  record.lastAttemptAt = new Date().toISOString();
  await db.put('mutationQueue', record);
}
