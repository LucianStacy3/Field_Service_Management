/**
 * sync.js
 *
 * Drains the IndexedDB mutation outbox against the Frappe REST API
 * whenever the browser is online. Triggered immediately after each
 * mutation is enqueued (see offlineStore.js's enqueueMutation), and as
 * a fallback on `online` events, on app foreground (visibilitychange),
 * on initial load, and via a manual tap on the header sync pill.
 *
 * NOTE: there is no Workbox periodic background sync registered in
 * sw.js (checked -- it isn't there), so this module's only triggers
 * are the ones listed above. Don't rely on background sync firing
 * while the PWA isn't open.
 */

import * as api from '../api/client.js';
import {
  getQueuedMutations,
  removeMutation,
  bumpMutationAttempts,
  getDB,
  markPhotoSynced,
} from './offlineStore.js';

const MAX_ATTEMPTS = 8;

// Now that enqueueMutation() (offlineStore.js) triggers a syncNow() attempt
// on every write, syncNow() can legitimately be invoked several times in
// close succession -- e.g. two actions queued back-to-back, or an
// 'online'/visibilitychange event firing while an enqueue-triggered run is
// still in flight. Without a guard, overlapping runs would each read the
// same queue snapshot and could both apply (and double-submit) the same
// mutation before either removes it. inFlight coalesces concurrent callers
// onto a single pass and immediately schedules one more pass afterward if
// anything was enqueued during that pass, so nothing queued mid-flight gets
// silently skipped.
let inFlight = null;
let rerunRequested = false;

export async function syncNow(opts = {}) {
  if (inFlight) {
    rerunRequested = true;
    return inFlight;
  }
  inFlight = runSyncPass(opts).finally(() => {
    inFlight = null;
    if (rerunRequested) {
      rerunRequested = false;
      syncNow(opts);
    }
  });
  return inFlight;
}

async function runSyncPass({ onProgress } = {}) {
  if (!navigator.onLine) return { synced: 0, failed: 0 };

  const mutations = await getQueuedMutations();
  let synced = 0;
  let failed = 0;

  for (const mutation of mutations) {
    try {
      await applyMutation(mutation);
      await removeMutation(mutation.id);
      synced += 1;
    } catch (err) {
      failed += 1;
      await bumpMutationAttempts(mutation.id);
      // Give up after MAX_ATTEMPTS and leave it queued but flagged for
      // manual review from the Settings > Sync Status screen.
      if (mutation.attempts + 1 >= MAX_ATTEMPTS) {
        console.error(`Mutation ${mutation.id} exceeded retry limit`, err);
      }
    }
    onProgress?.({ total: mutations.length, synced, failed });
  }

  return { synced, failed };
}

async function applyMutation(mutation) {
  switch (mutation.type) {
    case 'TIME_ACTION':
      return api.submitTimeAction(mutation.payload);

    case 'UPDATE_NOTES':
      return api.updateNotes(mutation.payload);

    case 'UPLOAD_PHOTO': {
      const db = await getDB();
      const photo = await db.get('photos', mutation.payload.localId);
      if (!photo || photo.synced) return; // already handled
      const result = await api.uploadPhoto({
        appointmentName: photo.appointmentName,
        blob: photo.blob,
        caption: photo.caption,
      });
      await markPhotoSynced(mutation.payload.localId, result?.message?.file_url);
      return result;
    }

    default:
      throw new Error(`Unknown mutation type: ${mutation.type}`);
  }
}

export function registerSyncListeners() {
  window.addEventListener('online', () => syncNow());
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible' && navigator.onLine) syncNow();
  });
  // Fires once at load in case mutations queued while the PWA was closed.
  if (navigator.onLine) syncNow();
}
