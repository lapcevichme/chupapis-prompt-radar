import {useState, type FormEvent} from 'react';
import {Loader2, Radar} from 'lucide-react';

interface LoginPageProps {
  error: string | null;
  initialEmail?: string;
  initialPassword?: string;
  isPending: boolean;
  onLogin: (email: string, password: string) => Promise<void>;
}

export default function LoginPage({
  error,
  initialEmail = '',
  initialPassword = '',
  isPending,
  onLogin,
}: LoginPageProps) {
  const [email, setEmail] = useState(initialEmail);
  const [password, setPassword] = useState(initialPassword);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void onLogin(email.trim(), password);
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-6">
      <div className="w-full max-w-md rounded-xl border border-divider bg-surface p-8 shadow-xl">
        <div className="mb-8 flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-accent-muted text-accent">
            <Radar className="h-6 w-6" />
          </div>
          <div>
            <h1 className="text-xl font-semibold text-primary">PromptRadar</h1>
            <p className="text-sm text-secondary">Sign in to the analytics workspace</p>
          </div>
        </div>

        <form className="space-y-5" onSubmit={handleSubmit}>
          <label className="block space-y-2 text-sm font-medium text-primary">
            Email
            <input
              autoComplete="email"
              className="h-11 w-full rounded-md border border-divider bg-background px-3 text-primary outline-none transition-colors focus:border-accent"
              name="email"
              required
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>

          <label className="block space-y-2 text-sm font-medium text-primary">
            Password
            <input
              autoComplete="current-password"
              className="h-11 w-full rounded-md border border-divider bg-background px-3 text-primary outline-none transition-colors focus:border-accent"
              minLength={1}
              name="password"
              required
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>

          {error && (
            <div className="rounded-md border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-500">
              {error}
            </div>
          )}

          <button
            className="inline-flex h-11 w-full items-center justify-center gap-2 rounded-md bg-accent px-4 text-sm font-semibold text-white hover:opacity-90 disabled:cursor-wait disabled:opacity-60"
            disabled={isPending || !email.trim() || !password}
            type="submit"
          >
            {isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            Sign in
          </button>
        </form>
      </div>
    </div>
  );
}

