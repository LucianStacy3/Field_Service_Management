import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.jsx';
import './styles/global.css';
import { registerSyncListeners } from './db/sync.js';

registerSyncListeners();

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    // Served from www/tech/sw.js (a literal file, not the /assets/ bundle)
    // so its default scope covers /tech/ — see vite.config.js for why.
    navigator.serviceWorker.register('/tech/sw.js', { scope: '/tech/' }).catch((err) => {
      console.error('Service worker registration failed', err);
    });
  });
}

createRoot(document.getElementById('root')).render(<App />);
