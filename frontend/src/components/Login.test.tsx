import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import Login from './Login';
import * as api from '../api';

afterEach(() => vi.restoreAllMocks());

describe('Login', () => {
  it('hands the signed-in user back to the shell', async () => {
    const user = { id: '1', email: 'a@b.c' };
    vi.spyOn(api, 'login').mockResolvedValue(user);
    const onSuccess = vi.fn();

    render(<Login onSuccess={onSuccess} />);
    await userEvent.type(screen.getByLabelText('Email'), 'a@b.c');
    await userEvent.type(screen.getByLabelText('Пароль'), 'secret');
    await userEvent.click(screen.getByRole('button', { name: 'Войти' }));

    expect(api.login).toHaveBeenCalledWith('a@b.c', 'secret');
    expect(onSuccess).toHaveBeenCalledWith(user);
  });

  it('reports bad credentials without leaking which field was wrong', async () => {
    vi.spyOn(api, 'login').mockRejectedValue(new Error('401'));

    render(<Login onSuccess={vi.fn()} />);
    await userEvent.type(screen.getByLabelText('Email'), 'a@b.c');
    await userEvent.type(screen.getByLabelText('Пароль'), 'wrong');
    await userEvent.click(screen.getByRole('button', { name: 'Войти' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Неверный email или пароль');
  });
});
