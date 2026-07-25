import {afterEach, expect, test, vi} from 'vitest';
import {promptRadarApi} from './promptRadarApi';

afterEach(() => vi.unstubAllGlobals());

test('passes filters and ROI overrides to export', async () => {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response('xlsx', {
      status: 200,
      headers: {'Content-Disposition': 'attachment; filename="custom.xlsx"'},
    }),
  );
  vi.stubGlobal('fetch', fetchMock);

  const result = await promptRadarApi.exportResults('xlsx', {
    source_id: 'source-1',
    from: '2026-07-01',
    fte_hourly_rate_rub: 1500,
  });

  const requestedUrl = new URL(String(fetchMock.mock.calls[0][0]));
  expect(requestedUrl.pathname).toBe('/api/v1/export');
  expect(requestedUrl.searchParams.get('format')).toBe('xlsx');
  expect(requestedUrl.searchParams.get('source_id')).toBe('source-1');
  expect(requestedUrl.searchParams.get('from')).toBe('2026-07-01');
  expect(requestedUrl.searchParams.get('fte_hourly_rate_rub')).toBe('1500');
  expect(result.filename).toBe('custom.xlsx');
});

