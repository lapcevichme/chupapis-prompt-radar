import {RefreshCcw} from 'lucide-react';
import {SystemHealth} from '@/features/system-health/SystemHealth';

interface WorkspaceActionsProps {
  onRefresh: () => void;
}

export function WorkspaceActions({onRefresh}: WorkspaceActionsProps) {
  return (
    <div className="flex flex-wrap items-center justify-end gap-2">
      <SystemHealth />
      <button
        className="inline-flex h-9 items-center gap-2 rounded-md border border-divider bg-surface px-3 text-sm font-medium text-primary hover:bg-surface-hover disabled:opacity-60"
        onClick={() => onRefresh()}
      >
        <RefreshCcw className="h-4 w-4" />
        Refresh
      </button>
    </div>
  );
}
