import { useCallback, useEffect, useState } from 'react';

const STORAGE_KEY = 'lcs-theme'; // 'light' | 'dark' — absence means "follow system"

// Meta theme-color per mode, kept in sync with global.css --lcs-bg so the
// browser/PWA chrome (status bar, task switcher card) matches the app.
const META_THEME_COLOR = {
  light: '#002957', // --lcs-navy (light)
  dark: '#0f1620',  // --lcs-bg (dark)
};

function systemPrefersDark() {
  return typeof window !== 'undefined'
    && window.matchMedia
    && window.matchMedia('(prefers-color-scheme: dark)').matches;
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute('content', META_THEME_COLOR[theme]);
}

/**
 * Resolves the active theme ('light' | 'dark'), applies it to
 * <html data-theme="..."> (matching global.css's [data-theme="dark"]
 * block), and keeps an explicit user choice in localStorage. If the
 * person hasn't chosen explicitly, the app follows the system
 * prefers-color-scheme setting live.
 */
export function useTheme() {
  const [theme, setTheme] = useState(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored === 'light' || stored === 'dark' ? stored : (systemPrefersDark() ? 'dark' : 'light');
  });

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  useEffect(() => {
    if (localStorage.getItem(STORAGE_KEY)) return undefined; // explicit choice wins — don't override it
    const mql = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = (e) => setTheme(e.matches ? 'dark' : 'light');
    mql.addEventListener('change', onChange);
    return () => mql.removeEventListener('change', onChange);
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme((prev) => {
      const next = prev === 'dark' ? 'light' : 'dark';
      localStorage.setItem(STORAGE_KEY, next);
      return next;
    });
  }, []);

  return [theme, toggleTheme];
}
