import {useEffect, useState} from 'react';
import {Filter, RotateCcw, X} from 'lucide-react';
import type {WorkspaceFilters as WorkspaceFilterValues} from '@/entities/workspace/types';

interface WorkspaceFiltersProps {
  filters: WorkspaceFilterValues;
  onChange: (filters: WorkspaceFilterValues) => void;
}

export function WorkspaceFilters({filters, onChange}: WorkspaceFiltersProps) {
  const [draft, setDraft] = useState(filters);
  const [isOpen, setIsOpen] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const activeCount = [filters.from, filters.to].filter(Boolean).length;

  useEffect(() => setDraft(filters), [filters]);

  const apply = () => {
    if (draft.from && draft.to && draft.from > draft.to) {
      setValidationError('Start date must not be after end date');
      return;
    }
    setValidationError(null);
    onChange(cleanFilters(draft));
    setIsOpen(false);
  };

  const clear = () => {
    const cleared = filters.source_id ? {source_id: filters.source_id} : {};
    setDraft(cleared);
    setValidationError(null);
    onChange(cleared);
  };

  return (
    <>
      <button
        type="button"
        className="inline-flex h-10 items-center gap-2 rounded-md border border-divider bg-surface px-3 text-sm font-semibold text-primary hover:bg-surface-hover"
        onClick={() => setIsOpen(true)}
      >
        <Filter className="h-4 w-4 text-accent" />
        Filters
        {activeCount > 0 && (
          <span className="ml-1 inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-accent px-1.5 text-xs text-white">
            {activeCount}
          </span>
        )}
      </button>

      {isOpen && <div className="fixed inset-0 z-[70] bg-black/60" onClick={() => setIsOpen(false)} />}

      <aside
        className={`fixed inset-y-0 right-0 z-[80] flex w-full max-w-[420px] flex-col border-l border-divider bg-surface shadow-2xl transition-transform duration-200 ${
          isOpen ? 'translate-x-0' : 'translate-x-full'
        }`}
        aria-hidden={!isOpen}
      >
        <div className="flex items-center justify-between border-b border-divider px-5 py-4">
          <div className="flex items-center gap-2">
            <Filter className="h-4 w-4 text-accent" />
            <h2 className="text-base font-semibold text-primary">Filters</h2>
          </div>
          <button
            type="button"
            aria-label="Close filters"
            className="rounded-md p-2 text-secondary hover:bg-surface-hover hover:text-primary"
            onClick={() => setIsOpen(false)}
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto px-5 py-5">
          <label className="flex flex-col gap-2 text-xs font-medium text-secondary">
            From
            <input
              className="h-10 rounded-md border border-divider bg-background px-3 text-sm text-primary outline-none focus:border-accent"
              type="date"
              value={draft.from ?? ''}
              onChange={(event) => setDraft((current) => ({...current, from: event.target.value || undefined}))}
            />
          </label>

          <label className="flex flex-col gap-2 text-xs font-medium text-secondary">
            To
            <input
              className="h-10 rounded-md border border-divider bg-background px-3 text-sm text-primary outline-none focus:border-accent"
              type="date"
              value={draft.to ?? ''}
              onChange={(event) => setDraft((current) => ({...current, to: event.target.value || undefined}))}
            />
          </label>

          {validationError && <p className="text-xs text-red-500">{validationError}</p>}
        </div>

        <div className="flex items-center gap-2 border-t border-divider p-5">
          <button className="h-10 flex-1 rounded-md bg-accent px-4 text-sm font-semibold text-white hover:opacity-90" onClick={apply} type="button">
            Apply
          </button>
          <button
            aria-label="Clear filters"
            className="inline-flex h-10 items-center gap-2 rounded-md border border-divider px-3 text-sm font-medium text-secondary hover:bg-surface-hover hover:text-primary"
            onClick={clear}
            type="button"
          >
            <RotateCcw className="h-4 w-4" />
            Clear
          </button>
        </div>
      </aside>
    </>
  );
}

function cleanFilters(filters: WorkspaceFilterValues): WorkspaceFilterValues {
  return Object.fromEntries(Object.entries(filters).filter(([, value]) => Boolean(value)));
}
