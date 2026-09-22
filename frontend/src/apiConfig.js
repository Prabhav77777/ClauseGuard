// Centralized API Base URL helper
// Uses VITE_API_BASE_URL env var if defined (e.g. https://clauseguard-api.onrender.com),
// or falls back to relative path '/api' (for Vite dev proxy or Vercel rewrites).
const envBase = import.meta.env.VITE_API_BASE_URL || ''
export const API_BASE = envBase.replace(/\/+$/, '')
