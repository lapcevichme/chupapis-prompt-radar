import {useEffect, useState} from 'react';
import {Activity, AlertTriangle, Loader2} from 'lucide-react';
import {promptRadarApi} from '@/shared/api/promptRadarApi';
import {cn} from '@/shared/lib/cn';

type HealthStatus = 'loading' | 'ok' | 'degraded' | 'unavailable';

export function SystemHealth() {
  const [status, setStatus] = useState<HealthStatus>('loading');

  useEffect(() => {
    let active = true;

    const load = async () => {
      if (document.visibilityState === 'hidden') {
        return;
      }
      try {
        const health = await promptRadarApi.getHealth();
        if (active) {
          setStatus(health.status === 'ok' ? 'ok' : 'degraded');
        }
      } catch {
        if (active) {
          setStatus('unavailable');
        }
      }
    };

    void load();
    const intervalId = window.setInterval(() => void load(), 30_000);
    return () => {
      active = false;
      window.clearInterval(intervalId);
    };
  }, []);

  const label = status === 'loading' ? 'Checking' : status === 'ok' ? 'Healthy' : status === 'degraded' ? 'Degraded' : 'Unavailable';
  const Icon = status === 'loading' ? Loader2 : status === 'ok' ? Activity : AlertTriangle;

  return (
    <span
      className={cn(
        'inline-flex h-9 items-center gap-2 rounded-md border px-3 text-xs font-semibold',
        status === 'ok' && 'border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
        status === 'degraded' && 'border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400',
        status === 'unavailable' && 'border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-400',
        status === 'loading' && 'border-divider text-secondary',
      )}
      title="Backend and dependency health"
    >
      <Icon className={cn('h-4 w-4', status === 'loading' && 'animate-spin')} />
      {label}
    </span>
  );
}

