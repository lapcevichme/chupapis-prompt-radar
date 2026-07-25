import type {WorkspaceFilters} from '@/entities/workspace/types';
import {promptRadarApi} from '@/shared/api/promptRadarApi';
import {useApiResource} from '@/shared/api/useApiResource';

interface DatasetSwitcherProps {
  filters: WorkspaceFilters;
  onChange: (filters: WorkspaceFilters) => void;
  refreshKey: number;
}

export function DatasetSwitcher({filters, onChange, refreshKey}: DatasetSwitcherProps) {
  const sourcesState = useApiResource(() => promptRadarApi.getSources(), [refreshKey]);
  const sources = sourcesState.data?.items ?? [];

  return (
    <label className="flex h-10 items-center gap-2 rounded-md border border-divider bg-surface px-3 text-xs font-semibold text-secondary">
      Dataset
      <select
        aria-label="Dataset"
        className="max-w-56 bg-transparent text-sm font-medium text-primary outline-none"
        disabled={sourcesState.isLoading && !sourcesState.data}
        value={filters.source_id ?? ''}
        onChange={(event) =>
          onChange({
            ...filters,
            source_id: event.target.value || undefined,
          })
        }
      >
        <option value="">All datasets</option>
        {sources.map((source) => (
          <option key={source.source_id} value={source.source_id}>
            {source.name} · {source.origin}
          </option>
        ))}
      </select>
    </label>
  );
}
