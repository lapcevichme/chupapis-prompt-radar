import {render, screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {expect, test, vi} from 'vitest';
import {WorkspaceFilters} from './WorkspaceFilters';

vi.mock('@/shared/api/promptRadarApi', () => ({
  promptRadarApi: {
    getSources: vi.fn().mockResolvedValue({
      items: [{source_id: 'source-1', name: 'Demo', origin: 'demo'}],
      total: 1,
    }),
  },
}));

test('validates dates and applies a normalized filter set', async () => {
  const user = userEvent.setup();
  const onChange = vi.fn();
  render(<WorkspaceFilters filters={{}} onChange={onChange} refreshKey={0} />);

  await user.selectOptions(await screen.findByLabelText('Source'), 'source-1');
  await user.type(screen.getByLabelText('From'), '2026-07-20');
  await user.type(screen.getByLabelText('To'), '2026-07-10');
  await user.click(screen.getByRole('button', {name: 'Apply'}));
  expect(screen.getByText('Start date must not be after end date')).toBeInTheDocument();
  expect(onChange).not.toHaveBeenCalled();

  await user.clear(screen.getByLabelText('To'));
  await user.type(screen.getByLabelText('To'), '2026-07-25');
  await user.click(screen.getByRole('button', {name: 'Apply'}));
  expect(onChange).toHaveBeenCalledWith({source_id: 'source-1', from: '2026-07-20', to: '2026-07-25'});
});

