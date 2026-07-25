import {render, screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {expect, test, vi} from 'vitest';
import LoginPage from './LoginPage';

test('submits manual credentials', async () => {
  const user = userEvent.setup();
  const onLogin = vi.fn().mockResolvedValue(undefined);
  render(<LoginPage error={null} isPending={false} onLogin={onLogin} />);

  await user.type(screen.getByLabelText('Email'), 'cto@example.com');
  await user.type(screen.getByLabelText('Password'), 'secret');
  await user.click(screen.getByRole('button', {name: 'Sign in'}));

  expect(onLogin).toHaveBeenCalledWith('cto@example.com', 'secret');
});

