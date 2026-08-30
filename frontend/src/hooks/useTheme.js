import { useCallback, useEffect, useState } from 'react';

// El tema vive en <html data-theme>. El valor arranca del que dejó el bootstrap
// de index.html (o 'dark' por defecto) y se persiste en localStorage.
const leer = () => {
  if (typeof document === 'undefined') return 'dark';
  return (
    document.documentElement.getAttribute('data-theme') ||
    localStorage.getItem('theme') ||
    'dark'
  );
};

export default function useTheme() {
  const [theme, setTheme] = useState(leer);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
  }, [theme]);

  const toggle = useCallback(() => {
    setTheme((t) => (t === 'dark' ? 'light' : 'dark'));
  }, []);

  return { theme, toggle, isDark: theme === 'dark' };
}
