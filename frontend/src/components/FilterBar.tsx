import React, { useState, useEffect } from 'react';
import { Filter, X } from 'lucide-react';
import type { DashboardFilters, Source } from '../types';
import { fetchSources, exportUrl } from '../api';

interface FilterBarProps {
  filters: DashboardFilters;
  onChange: (next: DashboardFilters) => void;
}

/**
 * Global filter bar (D3): one `source_id` + date range applied to every read
 * screen and to the export, so what the CTO sees and what they download match.
 */
export default function FilterBar({ filters, onChange }: FilterBarProps) {
  const [sources, setSources] = useState<Source[]>([]);

  useEffect(() => {
    fetchSources()
      .then(setSources)
      .catch(() => setSources([]));
  }, []);

  const set = (patch: Partial<DashboardFilters>) => onChange({ ...filters, ...patch });
  const isActive = Boolean(filters.source_id || filters.from || filters.to);

  const activeSource = sources.find((s) => s.source_id === filters.source_id);
  const scopeLabel = activeSource ? activeSource.name : 'Все источники';

  return (
    <div className="flex flex-col lg:flex-row lg:items-center gap-3 p-3 bg-surface border border-divider rounded-xl">
      <div className="flex items-center gap-2 text-secondary shrink-0">
        <Filter className="w-4 h-4 text-accent" />
        <span className="text-xs font-semibold uppercase tracking-wider">Фильтры</span>
      </div>

      <div className="flex flex-col sm:flex-row gap-3 flex-1 min-w-0">
        <label className="flex items-center gap-2 text-sm min-w-0">
          <span className="text-secondary shrink-0">Источник</span>
          <select
            value={filters.source_id ?? ''}
            onChange={(e) => set({ source_id: e.target.value || undefined })}
            className="min-w-0 flex-1 px-2 py-1.5 bg-background border border-divider rounded-md text-primary text-sm focus:outline-none focus:border-accent"
          >
            <option value="">Все источники</option>
            {sources.map((s) => (
              <option key={s.source_id} value={s.source_id}>
                {s.name} ({s.records_valid})
              </option>
            ))}
          </select>
        </label>

        <label className="flex items-center gap-2 text-sm">
          <span className="text-secondary shrink-0">С</span>
          <input
            type="date"
            value={filters.from ?? ''}
            onChange={(e) => set({ from: e.target.value || undefined })}
            className="px-2 py-1.5 bg-background border border-divider rounded-md text-primary text-sm focus:outline-none focus:border-accent"
          />
        </label>

        <label className="flex items-center gap-2 text-sm">
          <span className="text-secondary shrink-0">По</span>
          <input
            type="date"
            value={filters.to ?? ''}
            onChange={(e) => set({ to: e.target.value || undefined })}
            className="px-2 py-1.5 bg-background border border-divider rounded-md text-primary text-sm focus:outline-none focus:border-accent"
          />
        </label>
      </div>

      <div className="flex items-center gap-2 shrink-0">
        {isActive && (
          <button
            onClick={() => onChange({})}
            className="flex items-center gap-1 px-2 py-1.5 text-xs text-secondary hover:text-primary hover:bg-surface-hover rounded-md transition-colors"
            title="Сбросить фильтры"
          >
            <X className="w-3.5 h-3.5" />
            Сбросить
          </button>
        )}
        <a
          href={exportUrl('xlsx', filters)}
          className="px-3 py-1.5 text-xs font-medium bg-accent/15 text-accent hover:bg-accent/25 rounded-md transition-colors"
          title={`Выгрузить ROI в Excel: ${scopeLabel}`}
        >
          Excel
        </a>
        <a
          href={exportUrl('csv', filters)}
          className="px-3 py-1.5 text-xs font-medium text-secondary hover:text-primary hover:bg-surface-hover border border-divider rounded-md transition-colors"
          title={`Выгрузить ROI в CSV: ${scopeLabel}`}
        >
          CSV
        </a>
      </div>
    </div>
  );
}
