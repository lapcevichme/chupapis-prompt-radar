import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  SESSION_EXPIRED_EVENT,
  buildFilterQuery,
  exportUrl,
  fetchDashboard,
  fetchLogs,
  login,
} from './api';

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('filter serialization', () => {
  it('omits empty filters instead of sending blank params', () => {
    expect(buildFilterQuery({})).toBe('');
    expect(buildFilterQuery({ source_id: '', from: undefined })).toBe('');
  });

  it('carries every global filter', () => {
    const q = buildFilterQuery({ source_id: 'src-1', from: '2026-07-01', to: '2026-07-31' });
    expect(q).toContain('source_id=src-1');
    expect(q).toContain('from=2026-07-01');
    expect(q).toContain('to=2026-07-31');
  });

  it('applies the same filters to the export link', () => {
    const url = exportUrl('xlsx', { source_id: 'src-1', from: '2026-07-01' });
    expect(url).toContain('format=xlsx');
    expect(url).toContain('source_id=src-1');
    expect(url).toContain('from=2026-07-01');
  });

  it('passes filters through to /logs', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ items: [], total: 0 }));
    vi.stubGlobal('fetch', fetchMock);

    await fetchLogs({ source_id: 'src-1' }, 25);

    expect(fetchMock.mock.calls[0][0]).toContain('source_id=src-1');
    expect(fetchMock.mock.calls[0][0]).toContain('limit=25');
  });
});

describe('session handling', () => {
  it('refreshes once and replays the request on 401', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response('', { status: 401 })) // /dashboard
      .mockResolvedValueOnce(new Response('', { status: 200 })) // /auth/refresh
      .mockResolvedValueOnce(jsonResponse({ totals: { records_processed: 7 } }));
    vi.stubGlobal('fetch', fetchMock);

    const data = await fetchDashboard();

    expect(data.total_logs).toBe(7);
    expect(fetchMock.mock.calls[1][0]).toContain('/auth/refresh');
  });

  it('announces an expired session when the refresh also fails', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response('', { status: 401 }))
      .mockResolvedValueOnce(new Response('', { status: 401 }));
    vi.stubGlobal('fetch', fetchMock);

    const onExpired = vi.fn();
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired);

    await expect(fetchDashboard()).rejects.toThrow();
    expect(onExpired).toHaveBeenCalled();

    window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired);
  });

  it('does not try to refresh a failed login', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('', { status: 401 }));
    vi.stubGlobal('fetch', fetchMock);

    await expect(login('a@b.c', 'nope')).rejects.toThrow();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe('dashboard mapping', () => {
  it('derives success rate from the failure signal share', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse({
          totals: { records_processed: 100 },
          failure_analysis: { failure_signal_percentage: 21.6 },
        }),
      ),
    );

    const data = await fetchDashboard();

    expect(data.success_rate_percent).toBeCloseTo(78.4, 5);
  });
});
