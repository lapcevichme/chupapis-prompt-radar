import React, { useState, useEffect } from 'react';
import { fetchProcessingStatus } from '../api';
import type { ProcessingStatus } from '../types';
import { Loader2, CheckCircle2, ChevronDown, ChevronUp, Sparkles } from 'lucide-react';
import { cn } from '../lib/utils';

interface ProcessingBannerProps {
  refreshTrigger?: number;
}

const POLL_MS = 3000;

/**
 * App-wide indexing progress. Visible on every tab so the analysis stage is
 * obvious without opening Sources. Hides itself once everything is indexed and
 * no recompute is running.
 */
export default function ProcessingBanner({ refreshTrigger }: ProcessingBannerProps) {
  const [status, setStatus] = useState<ProcessingStatus | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [justFinished, setJustFinished] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    const poll = async () => {
      try {
        const data = await fetchProcessingStatus();
        if (cancelled) return;
        setStatus((prev) => {
          // Surface a short "done" confirmation on the active→idle edge.
          if (prev && (prev.indexing || prev.recompute_pending) && !data.indexing && !data.recompute_pending) {
            setJustFinished(true);
            setTimeout(() => !cancelled && setJustFinished(false), 6000);
          }
          return data;
        });
        // Poll fast while work is in flight, slowly when idle.
        timer = setTimeout(poll, data.indexing || data.recompute_pending ? POLL_MS : POLL_MS * 5);
      } catch {
        if (!cancelled) timer = setTimeout(poll, POLL_MS * 5);
      }
    };

    poll();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [refreshTrigger]);

  if (!status) return null;

  const active = status.indexing || status.recompute_pending;
  if (!active && !justFinished) return null;

  const pending = status.sources.filter((s) => !s.done);

  return (
    <div
      className={cn(
        'shrink-0 border-b transition-colors',
        active
          ? 'bg-accent/5 border-accent/20'
          : 'bg-emerald-500/5 border-emerald-500/20'
      )}
    >
      <div className="max-w-7xl mx-auto px-4 md:px-8 py-3">
        <div className="flex items-center gap-3">
          {active ? (
            <Loader2 className="w-4 h-4 text-accent animate-spin shrink-0" />
          ) : (
            <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
          )}

          <div className="flex-1 min-w-0">
            <div className="flex items-baseline gap-2 flex-wrap">
              <span className="text-sm font-semibold text-primary">
                {status.recompute_pending
                  ? 'Building scenarios'
                  : status.indexing
                    ? 'Indexing dataset'
                    : 'Analysis complete'}
              </span>
              {active && (
                <span className="text-xs font-mono text-secondary tabular-nums">
                  {status.total_classified.toLocaleString()} / {status.total_valid.toLocaleString()} records
                  {status.indexing ? ` · ${status.percent}%` : ''}
                </span>
              )}
              {!active && justFinished && (
                <span className="text-xs text-secondary">
                  {status.total_classified.toLocaleString()} records classified
                  {status.scenarios_named > 0 ? ` · ${status.scenarios_named} scenarios named` : ''}
                </span>
              )}
            </div>

            {status.indexing && (
              <div className="mt-2 w-full h-1.5 bg-surface-hover rounded-full overflow-hidden">
                <div
                  className="h-full bg-accent transition-all duration-700 ease-out"
                  style={{ width: `${Math.min(100, status.percent)}%` }}
                />
              </div>
            )}

            {status.recompute_pending && !status.indexing && (
              <p className="text-xs text-secondary mt-1 flex items-center gap-1.5">
                <Sparkles className="w-3 h-3" />
                Clustering and naming scenarios — this can take a few minutes
              </p>
            )}
          </div>

          {pending.length > 0 && (
            <button
              onClick={() => setExpanded((v) => !v)}
              className="shrink-0 flex items-center gap-1 text-xs font-medium text-secondary hover:text-primary transition-colors"
            >
              {pending.length} source{pending.length > 1 ? 's' : ''}
              {expanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            </button>
          )}
        </div>

        {expanded && pending.length > 0 && (
          <ul className="mt-3 space-y-2 pl-7">
            {pending.map((s) => (
              <li key={s.source_id} className="flex items-center gap-3 text-xs">
                <span className="text-primary font-medium truncate max-w-[200px]">{s.name}</span>
                <div className="flex-1 h-1 bg-surface-hover rounded-full overflow-hidden max-w-[240px]">
                  <div
                    className="h-full bg-accent transition-all duration-700"
                    style={{ width: `${Math.min(100, s.percent)}%` }}
                  />
                </div>
                <span className="font-mono text-secondary tabular-nums shrink-0">
                  {s.classified.toLocaleString()}/{s.records_valid.toLocaleString()}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
