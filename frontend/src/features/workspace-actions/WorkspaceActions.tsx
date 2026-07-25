import {useState} from 'react';
import {DatabaseZap, RefreshCcw} from 'lucide-react';
import {promptRadarApi} from '@/shared/api/promptRadarApi';
import {cn} from '@/shared/lib/cn';
import {SystemHealth} from '@/features/system-health/SystemHealth';

interface WorkspaceActionsProps {
  onRefresh: () => void;
}

export function WorkspaceActions({onRefresh}: WorkspaceActionsProps) {
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const runAction = async (name: string, action: () => Promise<unknown>) => {
    setPendingAction(name);
    setMessage(null);

    try {
      await action();
      setMessage('Demo ingest started');
      onRefresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Action failed');
    } finally {
      setPendingAction(null);
    }
  };

  return (
    <div className="flex flex-wrap items-center justify-end gap-2">
      <SystemHealth />
      {message && <span className="max-w-[220px] truncate text-xs text-secondary">{message}</span>}
      <button
        className="inline-flex h-9 items-center gap-2 rounded-md border border-divider bg-surface px-3 text-sm font-medium text-primary hover:bg-surface-hover disabled:opacity-60"
        disabled={pendingAction !== null}
        onClick={() => onRefresh()}
      >
        <RefreshCcw className="h-4 w-4" />
        Refresh
      </button>
      <button
        className={cn(
          'inline-flex h-9 items-center gap-2 rounded-md border border-divider bg-surface px-3 text-sm font-medium text-primary hover:bg-surface-hover disabled:opacity-60',
          pendingAction === 'ingest' && 'text-accent',
        )}
        disabled={pendingAction !== null}
        onClick={() => void runAction('ingest', promptRadarApi.ingestDemo)}
      >
        <DatabaseZap className="h-4 w-4" />
        Demo ingest
      </button>
    </div>
  );
}
