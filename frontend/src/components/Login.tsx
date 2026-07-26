import React, { useState } from 'react';
import { Radar, Loader2 } from 'lucide-react';
import { login, type CurrentUser } from '../api';

interface LoginProps {
  onSuccess: (user: CurrentUser) => void;
}

export default function Login({ onSuccess }: LoginProps) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      onSuccess(await login(email.trim(), password));
    } catch {
      // The API deliberately does not say which field was wrong.
      setError('Неверный email или пароль');
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm bg-surface border border-divider rounded-xl p-8 space-y-6"
      >
        <div className="flex items-center gap-2 text-primary font-bold text-xl tracking-tight">
          <Radar className="w-6 h-6 text-accent" />
          <span>PromptRadar</span>
        </div>

        <div className="space-y-4">
          <label className="block space-y-1.5">
            <span className="text-sm font-medium text-secondary">Email</span>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoFocus
              autoComplete="username"
              className="w-full px-3 py-2 bg-background border border-divider rounded-md text-primary text-sm focus:outline-none focus:border-accent"
            />
          </label>

          <label className="block space-y-1.5">
            <span className="text-sm font-medium text-secondary">Пароль</span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
              className="w-full px-3 py-2 bg-background border border-divider rounded-md text-primary text-sm focus:outline-none focus:border-accent"
            />
          </label>
        </div>

        {error && (
          <p role="alert" className="text-sm text-amber-400">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={busy}
          className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-accent text-white text-sm font-medium rounded-md hover:opacity-90 disabled:opacity-60 transition-opacity"
        >
          {busy && <Loader2 className="w-4 h-4 animate-spin" />}
          Войти
        </button>
      </form>
    </div>
  );
}
