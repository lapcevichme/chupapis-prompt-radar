export const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '') ??
  '/api/v1';

export const API_HEALTH_URL =
  (import.meta.env.VITE_API_HEALTH_URL as string | undefined)?.replace(/\/$/, '') ??
  '/api/health';

export const DEMO_EMAIL =
  (import.meta.env.VITE_DEMO_EMAIL as string | undefined) ?? 'demo@prompt-radar.local';

export const DEMO_PASSWORD =
  (import.meta.env.VITE_DEMO_PASSWORD as string | undefined) ?? 'DemoPass123!';

export const FALLBACK_DEMO_EMAIL =
  (import.meta.env.VITE_FALLBACK_DEMO_EMAIL as string | undefined) ?? 'test@gmail.com';

export const FALLBACK_DEMO_PASSWORD =
  (import.meta.env.VITE_FALLBACK_DEMO_PASSWORD as string | undefined) ?? 'test123';
