import {useEffect, useState} from 'react';
import {Filter, RotateCcw} from 'lucide-react';
import type {WorkspaceFilters as WorkspaceFilterValues} from '@/entities/workspace/types';
import {promptRadarApi} from '@/shared/api/promptRadarApi';
import {useApiResource} from '@/shared/api/useApiResource';

interface WorkspaceFiltersProps {
  filters: WorkspaceFilterValues;
  onChange: (filters: WorkspaceFilterValues) => void;
  refreshKey: number;
}

export function WorkspaceFilters({filters, onChange, refreshKey}: WorkspaceFiltersProps) {
  const [draft, setDraft] = useState(filters);
  const [validationError, setValidationError] = useState<string | null>(null);
  const sourcesState = useApiResource(() => promptRadarApi.getSources(), [refreshKey]);

  useEffect(() => setDraft(filters), [filters]);

  const apply = () => {
    if (draft.from && draft.to && draft.from > draft.to) {
      setValidationError('Start date must not be after end date');
      return;
    }
    setValidationError(null);
    onChange(cleanFilters(draft));
  };

  const clear = () => {
    setDraft({});
    setValidationError(null);
    onChange({});
  };

  return (
    <div className="border-b border-divider bg-surface px-4 py-3 md:px-8">
      <div className="mx-auto flex max-w-7xl flex-col gap-3 xl:flex-row xl:items-end">
        <div className="flex items-center gap-2 pb-1 text-sm font-semibold text-primary xl:mr-2">
          <Filter className="h-4 w-4 text-accent" />
          Filters
        </div>

        <label className="flex min-w-0 flex-1 flex-col gap-1 text-xs font-medium text-secondary">
          Source
          <select
            className="h-9 rounded-md border border-divider bg-background px-3 text-sm text-primary outline-none focus:border-accent"
            value={draft.source_id ?? ''}
            onChange={(event) => setDraft((current) => ({...current, source_id: event.target.value || undefined}))}
          >
            <option value="">All sources</option>
            {(sourcesState.data?.items ?? []).map((source) => (
              <option key={source.source_id} value={source.source_id}>
                {source.name} · {source.origin}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1 text-xs font-medium text-secondary">
          From
          <input
            className="h-9 rounded-md border border-divider bg-background px-3 text-sm text-primary outline-none focus:border-accent"
            type="date"
            value={draft.from ?? ''}
            onChange={(event) => setDraft((current) => ({...current, from: event.target.value || undefined}))}
          />
        </label>

        <label className="flex flex-col gap-1 text-xs font-medium text-secondary">
          To
          <input
            className="h-9 rounded-md border border-divider bg-background px-3 text-sm text-primary outline-none focus:border-accent"
            type="date"
            value={draft.to ?? ''}
            onChange={(event) => setDraft((current) => ({...current, to: event.target.value || undefined}))}
          />
        </label>

        <div className="flex items-center gap-2">
          <button className="h-9 rounded-md bg-accent px-4 text-sm font-semibold text-white hover:opacity-90" onClick={apply} type="button">
            Apply
          </button>
          <button
            aria-label="Clear filters"
            className="inline-flex h-9 items-center gap-2 rounded-md border border-divider px-3 text-sm font-medium text-secondary hover:bg-surface-hover hover:text-primary"
            onClick={clear}
            type="button"
          >
            <RotateCcw className="h-4 w-4" />
            Clear
          </button>
        </div>
      </div>
      {validationError && <p className="mx-auto mt-2 max-w-7xl text-xs text-red-500">{validationError}</p>}
    </div>
  );
}

function cleanFilters(filters: WorkspaceFilterValues): WorkspaceFilterValues {
  return Object.fromEntries(Object.entries(filters).filter(([, value]) => Boolean(value)));
}

