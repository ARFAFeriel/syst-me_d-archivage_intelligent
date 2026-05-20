// hooks/useApi.js
// Centralise tous les appels vers FastAPI — remplace apiFetch() du vanilla JS

// URL de base depuis variable d'environnement Vite, ou fallback localhost
const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

/**
 * Appel générique vers l'API FastAPI.
 * Retourne null si l'API est indisponible (ne plante pas l'UI).
 *
 * Si options.body est un FormData, Content-Type n'est PAS forcé
 * (le navigateur le définit automatiquement avec le boundary multipart).
 */
export async function apiFetch(path, options = {}) {
  try {
    const headers = {};
    const token = localStorage.getItem('auth_token');
    if (token) headers['Authorization'] = 'Bearer ' + token;

    // Ne pas forcer Content-Type pour FormData — le navigateur gère le boundary
    if (!(options.body instanceof FormData)) {
      headers['Content-Type'] = 'application/json';
    }

    const response = await fetch(API_BASE + path, {
      ...options,
      headers: { ...headers, ...(options.headers || {}) },
    });

    if (response.status === 401) {
      localStorage.removeItem('auth_token');
      window.location.hash = '#/login';
      return null;
    }
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  } catch (e) {
    console.warn('API indisponible:', e.message);
    return null;
  }
}

/**
 * Hook React pour les appels GET avec état loading/error.
 * Usage : const { data, loading, error, refetch } = useApi('/analytics/kpis');
 */
import { useState, useEffect, useCallback } from 'react';

export function useApi(path, deps = []) {
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);

  const fetch_ = useCallback(async () => {
    if (!path) return;
    setLoading(true);
    setError(null);
    const result = await apiFetch(path);
    if (result === null) setError('Backend non disponible');
    else setData(result);
    setLoading(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, ...deps]);

  useEffect(() => { fetch_(); }, [fetch_]);

  return { data, loading, error, refetch: fetch_ };
}

/** Helpers partagés */
export function timeAgo(iso) {
  if (!iso) return '—';
  const d = (Date.now() - new Date(iso)) / 1000;
  if (d < 60)    return 'Il y a quelques secondes';
  if (d < 3600)  return `Il y a ${Math.round(d / 60)} min`;
  if (d < 86400) return `Il y a ${Math.round(d / 3600)} h`;
  return `Il y a ${Math.round(d / 86400)} j`;
}

export function confBadge(v) {
  const n = parseFloat(v) || 0;
  const cls = n >= 90 ? 'h' : n >= 75 ? 'm' : 'l';
  const sym = n >= 90 ? '●' : n >= 75 ? '◑' : '○';
  return <span className={`conf ${cls}`}>{sym} {n.toFixed(1)}%</span>;
}

export function escapeHtml(text) {
  return (text || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}