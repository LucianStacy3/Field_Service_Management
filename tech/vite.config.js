import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';

// Served from Frappe Cloud at https://lcscales.v.frappe.cloud/tech —
// same pattern as the existing /schedule dispatch board SPA. The JS/CSS
// bundle is committed into beveren_fsm/beveren_fsm/public/tech/ (Frappe
// serves anything under an app's public/ folder at /assets/<app>/...).
// The HTML shell, service worker, and manifest are instead served as
// literal www/ files — see www/tech.py, www/tech/sw.js, www/tech/manifest.json
// in this project's server/ folder — because a service worker's default
// scope is the directory it's served from, and /assets/... won't cover
// the /tech/ scope the manifest's start_url needs.
export default defineConfig({
  base: '/assets/beveren_fsm/tech/',
  plugins: [
    react(),
    VitePWA({
      strategies: 'injectManifest',
      srcDir: 'src',
      filename: 'sw.js',
      // injectRegister must stay null: without it, Vite auto-generates
      // registerSW.js and adds it to the service worker's precache list
      // even though it's unused here (registration happens in main.jsx
      // instead). If registerSW.js then isn't deployed alongside the
      // rest of the built assets, every SW install fails silently with
      // bad-precaching-response and nothing works right until someone
      // notices the Console error. Cost a multi-day debugging session
      // once already — don't remove this.
      injectRegister: null,
      injectManifest: {
        globPatterns: ['**/*.{js,css}'],
      },
      manifest: false, // manifest.json is hand-maintained in public/ and served from www/tech/
      devOptions: { enabled: true },
    }),
  ],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    // Hashed filenames + Vite's build manifest — NOT fixed names. Frappe
    // serves /assets/... with long-lived cache headers on the assumption
    // that a filename change means the content changed; hashed filenames
    // are what make that assumption true. tech.py reads this manifest
    // (copied to www/tech/asset-manifest.json at deploy time) to resolve
    // the current filenames, and tech.html renders them via Jinja
    // ({{ tech_js }} / {% for css_file in tech_css %}) — so nothing here
    // needs to be hardcoded anywhere else after a rebuild.
    manifest: 'asset-manifest.json',
  },
  server: {
    proxy: {
      // Local dev against a real Frappe Cloud site — set LCS_DEV_SITE
      // before running `yarn dev`, e.g. https://lcscales.v.frappe.cloud
      '/api': process.env.LCS_DEV_SITE || 'http://dev.localhost:8000',
    },
  },
});
