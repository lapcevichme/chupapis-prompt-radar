import {render, screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {expect, test, vi} from 'vitest';
import {DatasetSwitcher} from './DatasetSwitcher';

vi.mock('@/shared/api/promptRadarApi', () => ({
  promptRadarApi: {
    getSources: vi.fn().mockResolvedValue({
      items: [
        {
          source_id: 'engineering',
          name: 'Engineering & Data',
          origin: 'preloaded',
        },
      ],
      total: 1,
    }),
  },
}));

test('switches dataset without dropping date filters', async () => {
  const user = userEvent.setup();
  const onChange = vi.fn();
  render(
    <DatasetSwitcher
      filters={{from: '2026-07-01'}}
      onChange={onChange}
      refreshKey={0}
    />,
  );

  await user.selectOptions(await screen.findByLabelText('Dataset'), 'engineering');
  expect(onChange).toHaveBeenCalledWith({
    source_id: 'engineering',
    from: '2026-07-01',
  });
});
